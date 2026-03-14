"""
Emerald AI - Autonomous Pokemon Emerald Player

Main game loop that connects all components:
- BizHawk bridge (emulator communication)
- State detection (what's happening in-game)
- Battle AI (strategic combat decisions)
- Completion tracking (progress monitoring)

Usage:
    python -m src.main [--strategy aggressive|safe|speedrun|grind]
"""

import argparse
import json
import logging
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # dotenv not required

from src.emulator.mgba_client import mGBAClient
from src.input_controller import InputController
from src.games.pokemon_gen3.state_detector import (
    PokemonGen3StateDetector, PokemonGen3State
)
from src.games.pokemon_gen3.battle_handler import (
    PokemonGen3BattleHandler, BattleAction, BattleDecision
)
from src.ai.battle_ai import BattleAI, BattleContext, BattleStrategy
from src.tracking.completion_tracker import CompletionTracker
from src.games.pokemon_gen3.intro_handler import IntroHandler
from src.games.pokemon_gen3.progression_handler import ProgressionHandler, GamePhase
from src.brain import GameBrain
from src.brain.config import BrainConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class EmeraldAI:
    """
    Autonomous Pokemon Emerald player.
    
    Integrates state detection, battle AI, and completion tracking
    into a coherent game loop.
    """

    def __init__(self, strategy: str = "aggressive"):
        # Core components
        self.client = mGBAClient(host="127.0.0.1", port=8787)
        self.input = InputController(self.client)
        self.state_detector = PokemonGen3StateDetector(self.client)
        
        # Battle system
        self.battle_handler = PokemonGen3BattleHandler(self.client)
        self.battle_ai = BattleAI(self.battle_handler)
        self._set_strategy(strategy)
        
        # Tracking
        self.tracker = CompletionTracker(self.state_detector)
        self.tracker.set_save_path(
            Path(__file__).parent.parent / "data" / "progress.json"
        )
        
        # Game loop state
        self.tick_interval = 0.5
        self.running = False
        self._battle_context = None
        self._ticks_in_state = 0
        self._last_state = PokemonGen3State.UNKNOWN
        self._stuck_counter = 0
        
        # Overworld navigation state
        self._current_direction = None
        self._direction_persist_ticks = 0
        self._direction_persist_target = 0
        self._last_position = (0, 0)
        self._position_stuck_counter = 0
        
        # Stats
        self._battles_won = 0
        self._battles_fled = 0
        self._ticks_total = 0
        
        # Settings configuration (one-time setup)
        self._settings_configured = False
        
        # New game flow state tracking
        self._in_new_game_flow = False
        self._new_game_step = 0
        self._new_game_input_delay = 0
        
        # LLM brain (decision layer — uses OpenRouter, not Anthropic API)
        self.brain = GameBrain(game_key="emerald")

        # Intro and progression handlers
        self.intro_handler = IntroHandler(self.state_detector, self.input)
        self.progression = ProgressionHandler(self.state_detector, self.input)
        self._intro_complete = False

    def _set_strategy(self, strategy: str):
        strategy_map = {
            "aggressive": BattleStrategy.AGGRESSIVE,
            "safe": BattleStrategy.SAFE,
            "speedrun": BattleStrategy.SPEEDRUN,
            "grind": BattleStrategy.GRIND,
            "catch": BattleStrategy.CATCH,
        }
        self.battle_ai.set_strategy(
            strategy_map.get(strategy, BattleStrategy.AGGRESSIVE)
        )

    def connect(self) -> bool:
        """Connect to BizHawk emulator."""
        logger.info("Connecting to BizHawk...")
        if self.client.connect():
            title = self.client.get_game_title()
            code = self.client.get_game_code()
            logger.info(f"Connected! Game: {title} ({code})")
            
            if code != "BPEE":
                logger.warning(f"Expected Emerald (BPEE), got {code}")
            
            return True
        else:
            logger.error("Failed to connect. Is BizHawk running with the Lua script?")
            return False

    def run(self):
        """Main game loop."""
        if not self.connect():
            return

        logger.info("=" * 50)
        logger.info("Emerald AI starting autonomous play")
        logger.info("=" * 50)
        self.running = True

        try:
            while self.running:
                self.tick()
                time.sleep(self.tick_interval)
        except KeyboardInterrupt:
            logger.info("Stopping (Ctrl+C)...")
        finally:
            self._print_stats()
            self.client.close()

    def tick(self):
        """Execute one game tick."""
        self._ticks_total += 1
        
        # Detect current state
        state = self.state_detector.detect()
        
        # Track state changes
        if state != self._last_state:
            logger.info(f"State transition: {self._last_state.name} → {state.name}")
            self._ticks_in_state = 0
            self._stuck_counter = 0
            
            # On entering battle, create context
            if self.state_detector.in_battle and not self._is_battle_state(self._last_state):
                self._on_battle_start()
            
            # On leaving battle
            if self._is_battle_state(self._last_state) and not self.state_detector.in_battle:
                self._on_battle_end()
            
            self._last_state = state
        else:
            self._ticks_in_state += 1
        
        # Stuck detection (skip in OVERWORLD, during new game flow, and during intro)
        in_intro = not self._intro_complete and not self.intro_handler.is_complete
        if self._ticks_in_state > 60 and state != PokemonGen3State.OVERWORLD and not self._in_new_game_flow and not in_intro:
            self._handle_stuck()
        
        # Dispatch to handler
        if state == PokemonGen3State.TITLE_SCREEN:
            self._handle_title_screen()
        elif self.state_detector.in_battle:
            self._handle_battle()
        elif state == PokemonGen3State.DIALOGUE:
            self._handle_dialogue()
        elif state == PokemonGen3State.OVERWORLD:
            self._handle_overworld()
        elif state == PokemonGen3State.TRANSITION:
            pass  # Wait for transition to complete
        elif state == PokemonGen3State.UNKNOWN:
            self._handle_unknown()
        
        # Push OBS overlay update (every 5 ticks ≈ 2.5s)
        if self._ticks_total % 5 == 0:
            self._push_obs_update()

        # Periodic progress update (every 30 ticks)
        if self._ticks_total % 30 == 0:
            progress = self.tracker.update()
            if self._ticks_total % 300 == 0:  # Log every ~90 seconds
                logger.info(f"Progress: {progress.completion_percentage:.1f}% | "
                           f"Badges: {progress.badges.count}/8 | "
                           f"Playtime: {progress.playtime}")

    def _is_battle_state(self, state: PokemonGen3State) -> bool:
        """Check if a state is a battle state."""
        return state in (
            PokemonGen3State.BATTLE_WILD,
            PokemonGen3State.BATTLE_TRAINER,
            PokemonGen3State.BATTLE_DOUBLE_WILD,
            PokemonGen3State.BATTLE_DOUBLE_TRAINER,
            PokemonGen3State.BATTLE_SAFARI,
            PokemonGen3State.BATTLE_TOWER,
            PokemonGen3State.BATTLE_FRONTIER,
            PokemonGen3State.BATTLE_LEGENDARY,
        )

    def _handle_title_screen(self):
        """
        Handle title screen and new game initialization using state-driven approach.
        
        Instead of numbered steps, reads actual game state and reacts:
        - game_state at 0x0300500C: 0xFF = title/intro screens
        - party_count at 0x02024284: > 0 means we have a starter
        - map location at 0x02036E12 (group), 0x02036E13 (num): detect Route 101
        
        Strategy: spam A/Start until game progresses, detect starter selection, exit when party exists.
        """
        # Initialize new game flow on first entry
        if not self._in_new_game_flow:
            logger.info("=" * 50)
            logger.info("TITLE SCREEN DETECTED - Starting state-driven new game flow")
            logger.info("=" * 50)
            self._in_new_game_flow = True
            self._new_game_step = 0  # Repurpose as general counter for starter selection
        
        # Read game state
        try:
            game_state = self.client.read8(0x0300500C)
            party_count = self.client.read8(0x02024284)
            map_group = self.client.read8(0x02036E12)
            map_num = self.client.read8(0x02036E13)
        except Exception as e:
            logger.warning(f"Failed to read game state: {e}, pressing A")
            self.input.tap("A")
            return
        
        # Check if new game is complete
        if party_count > 0 and game_state != 0xFF:
            logger.info("=" * 50)
            logger.info("✓ NEW GAME COMPLETE - Starter obtained!")
            logger.info(f"  Party count: {party_count}")
            logger.info(f"  Game state: 0x{game_state:02X}")
            logger.info(f"  Map: group={map_group}, num={map_num}")
            logger.info("  Transitioning to normal gameplay")
            logger.info("=" * 50)
            self._in_new_game_flow = False
            self._new_game_step = 0
            return
        
        # Starter selection logic: detect Route 101 (group=0, num=16) with no party
        # This is where Prof Birch throws the bags
        if map_group == 0 and map_num == 16 and party_count == 0:
            # We're on Route 101 for the starter selection
            if self._new_game_step == 0:
                logger.info("🎒 STARTER SELECTION DETECTED (Route 101)")
                logger.info("   Pressing Left 3x to select Mudkip (leftmost bag)")
                # Press Left multiple times to ensure we're on Mudkip
                self.input.tap("Left")
                self._new_game_step = 1
            elif self._new_game_step == 1:
                self.input.tap("Left")
                self._new_game_step = 2
            elif self._new_game_step == 2:
                self.input.tap("Left")
                self._new_game_step = 3
            elif self._new_game_step == 3:
                logger.info("   Confirming Mudkip selection with A")
                self.input.tap("A")
                self._new_game_step = 4
            else:
                # After selecting, spam A to continue through dialogue
                self.input.tap("A")
        else:
            # Not on Route 101 yet or still in intro - spam A and Start to advance
            # Alternate between A and Start for maximum advancement
            if self._ticks_in_state % 2 == 0:
                self.input.tap("A")
            else:
                self.input.tap("Start")
            
        # Log state periodically
        if self._ticks_in_state % 10 == 0:
            logger.debug(f"New game state: game_state=0x{game_state:02X}, "
                        f"party_count={party_count}, map={map_group}/{map_num}")

    def _on_battle_start(self):
        """Called when entering a battle."""
        logger.info("Battle started!")
        
        # Read battle state
        battle_state = self.battle_handler.read_battle_state()
        
        # Read party for switching decisions
        party = self.state_detector.read_party()
        
        self._battle_context = BattleContext(
            state=battle_state,
            party=party,
        )
        
        if battle_state.is_wild:
            enemy = battle_state.enemy_lead
            if enemy:
                name = enemy.species_name or f"species#{enemy.species_id}"
                logger.info(f"Wild battle: Lv.{enemy.level} {name}")
                if enemy.moves:
                    move_names = [m.name or f"#{m.id}" for m in enemy.moves]
                    logger.info(f"  Enemy moves: {', '.join(move_names)}")
        else:
            logger.info("Trainer battle!")

    def _on_battle_end(self):
        """Called when leaving a battle."""
        logger.info("Battle ended")
        self._battle_context = None

    def _get_brain_battle_decision(self, battle_state) -> dict | None:
        """Ask brain for a battle decision. Returns None on failure."""
        try:
            player = battle_state.player_lead if battle_state else None
            enemy = battle_state.enemy_lead if battle_state else None
            if not player or not enemy:
                return None

            player_dict = {
                "species": getattr(player, "species_name", "?"),
                "level": getattr(player, "level", 0),
                "hp": getattr(player, "hp", 0),
                "max_hp": getattr(player, "max_hp", 1),
                "types": [t.name for t in getattr(player, "types", []) if t],
                "moves": [
                    {
                        "name": getattr(m, "name", "?"),
                        "power": getattr(m, "power", 0),
                        "type": getattr(m, "type", None) and m.type.name or "?",
                        "pp": getattr(m, "pp", 0),
                        "max_pp": getattr(m, "max_pp", 0),
                    }
                    for m in getattr(player, "moves", [])
                    if m
                ],
                "status": getattr(player, "status", 0),
            }
            enemy_dict = {
                "species": getattr(enemy, "species_name", "?"),
                "level": getattr(enemy, "level", 0),
                "hp": getattr(enemy, "hp", 0),
                "max_hp": getattr(enemy, "max_hp", 1),
                "types": [t.name for t in getattr(enemy, "types", []) if t],
                "moves": [
                    {
                        "name": getattr(m, "name", "?"),
                        "power": getattr(m, "power", 0),
                        "type": getattr(m, "type", None) and m.type.name or "?",
                    }
                    for m in getattr(enemy, "moves", [])
                    if m
                ],
                "status": getattr(enemy, "status", 0),
            }

            return self.brain.get_battle_action(
                player_pokemon=player_dict,
                enemy_pokemon=enemy_dict,
                is_trainer=not battle_state.is_wild,
                badges=self.tracker.progress.badges.count if self.tracker.progress else 0,
            )
        except Exception as e:
            logger.debug(f"Brain battle decision failed: {e}")
            return None

    def _handle_battle(self):
        """Handle battle state using Brain (trainer) or Battle AI (wild)."""
        if not self._battle_context:
            self._on_battle_start()
            return

        # Refresh battle state
        try:
            battle_state = self.battle_handler.read_battle_state()
            self._battle_context.state = battle_state
            self._battle_context.turns_in_battle += 1
        except Exception as e:
            logger.warning(f"Failed to read battle state: {e}")
            self.input.tap("A")
            return

        # Try brain for trainer battles, fall back to rule engine
        brain_decision = None
        if not battle_state.is_wild and self.brain.enabled:
            brain_decision = self._get_brain_battle_decision(battle_state)

        if brain_decision:
            action_str = brain_decision.get("action", "fight")
            reason = f"Brain: {brain_decision.get('reason', '')}"
            if action_str == "fight":
                decision = BattleDecision(
                    action=BattleAction.FIGHT,
                    move_index=brain_decision.get("move_index", 0),
                    reason=reason,
                )
            elif action_str == "switch":
                decision = BattleDecision(
                    action=BattleAction.SWITCH,
                    pokemon_index=brain_decision.get("pokemon_index", 1),
                    reason=reason,
                )
            elif action_str == "run":
                decision = BattleDecision(
                    action=BattleAction.RUN,
                    reason=reason,
                )
            else:
                decision = self.battle_ai.decide(self._battle_context)
        else:
            decision = self.battle_ai.decide(self._battle_context)

        # Execute decision
        self._execute_battle_decision(decision)

    def _execute_battle_decision(self, decision):
        """Translate AI decision into button inputs."""
        # Log decision details
        if decision.action == BattleAction.FIGHT and self._battle_context:
            player = self._battle_context.player
            if player and decision.move_index < len(player.moves):
                move = player.moves[decision.move_index]
                logger.info(f"  → Using {move.name or f'move#{move.id}'} "
                           f"(power={move.power}, type={move.type.name if move.type else '?'})")
        
        if decision.action == BattleAction.FIGHT:
            # Navigate to Fight menu
            self.input.tap("A")  # Select Fight
            time.sleep(0.2)
            
            # Navigate to correct move
            move_idx = decision.move_index
            if move_idx == 1:
                self.input.tap("Right")
            elif move_idx == 2:
                self.input.tap("Down")
            elif move_idx == 3:
                self.input.press_sequence(["Right", "Down"])
            
            time.sleep(0.1)
            self.input.tap("A")  # Confirm move
            
        elif decision.action == BattleAction.RUN:
            # Navigate to Run (Down twice from Fight, then Right)
            self.input.tap("Down")  # To Pokemon
            time.sleep(0.1)
            self.input.tap("Right")  # To Run
            time.sleep(0.1)
            self.input.tap("A")  # Confirm
            self._battles_fled += 1
            
        elif decision.action == BattleAction.SWITCH:
            # Navigate to Pokemon menu
            self.input.tap("Down")  # To Pokemon
            time.sleep(0.1)
            self.input.tap("A")  # Open Pokemon
            time.sleep(0.3)
            
            # Navigate to target Pokemon
            for _ in range(decision.pokemon_index):
                self.input.tap("Down")
                time.sleep(0.1)
            
            self.input.tap("A")  # Select
            time.sleep(0.1)
            self.input.tap("A")  # Confirm switch

    def _handle_dialogue(self):
        """Handle dialogue/text boxes - press A to advance.
        
        During intro phases, we also let the intro handler know
        so it can track dialogue-based progression.
        """
        # If intro handler is active, let it handle dialogue
        # (it knows about intro-specific dialogue flows)
        if not self._intro_complete and not self.intro_handler.is_complete:
            self.intro_handler.tick()
            return
        
        # Normal dialogue — turbo A to advance quickly
        self.input.turbo_a()

    def _configure_game_settings(self):
        """
        Configure game settings via direct memory write.
        
        Writes optimal settings to Save Block 2 options byte:
        - Text Speed: Fast (2)
        - Battle Scene: Off (1)
        - Battle Style: Set (1)
        
        Combined value: 0x4A (74 decimal)
        - Bits 0-2: Text speed = 2
        - Bits 3-5: Battle animations = 1 (Off), shifted << 3
        - Bits 6-7: Battle style = 1 (Set), shifted << 6
        
        Returns True on success, False on failure (game continues either way).
        """
        logger.info("=" * 50)
        logger.info("CONFIGURING GAME SETTINGS (Direct Memory Write)")
        logger.info("=" * 50)
        
        try:
            # Read Save Block 2 pointer
            sb2_address = self.client.read32(0x03005D90)
            if not sb2_address or not (0x02000000 <= sb2_address <= 0x0203FFFF):
                logger.error(f"Invalid Save Block 2 pointer: {sb2_address}")
                return False
            
            logger.info(f"Save Block 2 address: 0x{sb2_address:08X}")
            
            # Calculate options address (SB2 + 0x13)
            options_address = sb2_address + 0x13
            logger.info(f"Options address: 0x{options_address:08X}")
            
            # Read current value
            current = self.client.read8(options_address)
            logger.info(f"Current options byte: 0x{current:02X}")
            
            # Write optimal settings byte: 0x4A
            # Bits 0-2: Text speed = 2 (Fast)
            # Bits 3-5: Battle animations = 1 (Off), shifted << 3 = 0x08
            # Bits 6-7: Battle style = 1 (Set), shifted << 6 = 0x40
            # Total: 0x02 | 0x08 | 0x40 = 0x4A (74 decimal)
            optimal_value = 0x4A
            success = self.client.write8(options_address, optimal_value)
            
            if not success:
                logger.error("WRITE8 command failed")
                return False
            
            logger.info(f"Wrote optimal settings: 0x{optimal_value:02X}")
            
            # Allow game time to process the write
            time.sleep(0.5)
            
            # Verify the write
            verify = self.client.read8(options_address)
            
            if verify == optimal_value:
                logger.info(f"✓ Settings configured successfully! (verified: 0x{verify:02X})")
                logger.info("  Text Speed: Fast | Battle Scene: Off | Battle Style: Set")
                logger.info("=" * 50)
                return True
            else:
                logger.error(f"⚠ Verification failed: expected 0x{optimal_value:02X}, got 0x{verify:02X}")
                logger.error("  Continuing with current settings (game is still playable)")
                logger.info("=" * 50)
                return False
                
        except Exception as e:
            logger.error(f"Exception during settings configuration: {e}")
            logger.error("  Continuing with current settings (game is still playable)")
            logger.info("=" * 50)
            return False

    def _handle_overworld(self):
        """
        Handle overworld navigation using progression directives + random walk fallback.
        
        Strategy:
        1. If intro isn't complete, delegate to intro handler
        2. Detect current game phase from progression handler
        3. Follow phase-specific movement directives (walk north to Route 101, etc.)
        4. Fall back to random walk with direction persistence if no directive
        
        Uses walk() for movement (hold direction for multiple frames) instead
        of tap() which only registers a single frame of input.
        """
        import random
        
        # Check if we need to configure settings (only once per session, early in overworld)
        if not self._settings_configured:
            if not self.state_detector.verify_optimal_settings():
                # Settings not optimal - write directly to memory
                self._configure_game_settings()
            else:
                logger.info("✓ Settings already optimal!")
            self._settings_configured = True  # Mark as attempted regardless of result
            # Reconnect if settings config dropped the connection
            if not self.client.is_connected():
                logger.info('Reconnecting to mGBA after settings config...')
                import time as _time
                _time.sleep(1)
                self.client.connect()
        
        # Get current position
        pos = self.state_detector.get_player_position()
        map_loc = self.state_detector.get_map_location()
        
        # --- INTRO HANDLER ---
        # If intro isn't complete, let the intro handler manage navigation
        if not self._intro_complete:
            if not self.intro_handler.is_complete:
                self.intro_handler.tick()
                return
            else:
                logger.info("=" * 50)
                logger.info("INTRO HANDLER COMPLETE — switching to progression")
                logger.info("=" * 50)
                self._intro_complete = True
        
        # --- PROGRESSION HANDLER ---
        # Detect current game phase and get movement directive
        phase = self.progression.detect_phase()
        directive = self.progression.get_directive()
        
        # Log position periodically
        if self._ticks_in_state % 20 == 0:
            logger.debug(f"Overworld: pos={pos}, map={map_loc}, phase={phase.name}")
        
        # Check if position has changed since last tick
        if pos == self._last_position:
            self._position_stuck_counter += 1
        else:
            self._position_stuck_counter = 0
            self._last_position = pos
        
        # If we have a directive, follow it
        if directive is not None:
            if self._ticks_in_state % 30 == 0:
                logger.info(f"Directive: {directive.description} ({directive.direction})")
            
            # If stuck in same position for 5+ ticks with a directive, try alternate paths
            if self._position_stuck_counter >= 5:
                logger.debug(f"Stuck at {pos} while following directive, trying alternate")
                # Try perpendicular direction to get around obstacle
                perpendicular = {
                    "Up": ["Left", "Right"],
                    "Down": ["Left", "Right"],
                    "Left": ["Up", "Down"],
                    "Right": ["Up", "Down"],
                }
                alt_dir = random.choice(perpendicular.get(directive.direction, ["Up", "Down"]))
                self.input.walk(alt_dir)
                self._position_stuck_counter = 0
            else:
                self.input.walk(directive.direction)
            return
        
        # --- RANDOM WALK FALLBACK ---
        # No directive — explore randomly (for free roam or unknown phases)
        
        # If stuck in same position for 3+ ticks, we hit a wall - change direction
        if self._position_stuck_counter >= 3:
            logger.debug(f"Hit obstacle at {pos}, changing direction")
            self._current_direction = None
            self._direction_persist_ticks = 0
            self._position_stuck_counter = 0
        
        # Direction persistence logic
        if self._current_direction is None or self._direction_persist_ticks >= self._direction_persist_target:
            # Pick new direction and duration
            self._current_direction = random.choice(["Up", "Down", "Left", "Right"])
            self._direction_persist_target = random.randint(5, 15)
            self._direction_persist_ticks = 0
            logger.debug(f"Random walk: {self._current_direction} for {self._direction_persist_target} ticks")
        
        # Move in current direction using walk() (hold for multiple frames)
        self.input.walk(self._current_direction)
        self._direction_persist_ticks += 1

    def _handle_unknown(self):
        """Handle unknown state - try pressing A/Start."""
        if self._ticks_in_state % 5 == 0:
            self.input.tap("A")
        elif self._ticks_in_state % 7 == 0:
            self.input.tap("Start")

    def _handle_stuck(self):
        """Attempt to get unstuck."""
        self._stuck_counter += 1
        logger.warning(f"Possibly stuck (counter={self._stuck_counter})")
        
        if self._stuck_counter < 3:
            # Try pressing B to cancel menus
            self.input.tap("B")
        elif self._stuck_counter < 6:
            # Try pressing A
            self.input.tap("A")
        else:
            # Try random movement
            import random
            direction = random.choice(["Up", "Down", "Left", "Right"])
            self.input.tap(direction)
            self._stuck_counter = 0

    def _push_obs_update(self):
        """Push current state to the OBS overlay bridge (fire-and-forget)."""
        progress = self.tracker.progress
        if progress and progress.party.count > 0:
            progress_text = (
                f"Badges: {progress.badges.count}/8 | "
                f"Pokedex: {progress.pokedex.caught} caught | "
                f"Party Lv: {progress.party.highest_level} | "
                f"Time: {progress.playtime}"
            )
        else:
            progress_text = "Waiting for data..."

        payload = json.dumps({
            "objective": f"State: {self._last_state.name}",
            "thought": f"Ticks: {self._ticks_total} | Stuck: {self._stuck_counter}",
            "progress": progress_text,
            "script": f"Strategy: {self.battle_ai.strategy.name}",
        }).encode("utf-8")

        req = urllib.request.Request(
            "http://127.0.0.1:8765/update",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            pass  # Bridge may not be running; don't disrupt gameplay

    def _print_stats(self):
        """Print session statistics."""
        progress = self.tracker.update(force=True)
        logger.info("=" * 50)
        logger.info("Session Statistics:")
        logger.info(f"  Ticks: {self._ticks_total}")
        logger.info(f"  Battles fled: {self._battles_fled}")
        logger.info(f"  Badges: {progress.badges.count}/8")
        logger.info(f"  Pokedex: {progress.pokedex.caught} caught")
        logger.info(f"  Playtime: {progress.playtime}")
        logger.info("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="Emerald AI - Autonomous Pokemon Player")
    parser.add_argument(
        "--strategy", 
        choices=["aggressive", "safe", "speedrun", "grind", "catch"],
        default="aggressive",
        help="Battle strategy"
    )
    args = parser.parse_args()
    
    ai = EmeraldAI(strategy=args.strategy)
    ai.run()


if __name__ == "__main__":
    main()

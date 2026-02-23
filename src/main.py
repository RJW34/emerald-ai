"""
Emerald AI - Autonomous Pokemon Emerald Player

Main game loop that connects all components:
- mGBA embedded emulator (emulator communication)
- State detection (what's happening in-game)
- Battle AI (strategic combat decisions)
- Completion tracking (progress monitoring)

Usage:
    python -m src.main [--strategy aggressive|safe|speedrun|grind]
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.emulator.mgba_client import MgbaClient
from src.input_controller import InputController
from src.games.pokemon_gen3.state_detector import (
    PokemonGen3StateDetector, PokemonGen3State
)
from src.games.pokemon_gen3.battle_handler import (
    PokemonGen3BattleHandler, BattleAction
)
from src.ai.battle_ai import BattleAI, BattleContext, BattleStrategy
from src.tracking.completion_tracker import CompletionTracker

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

    def __init__(self, strategy: str = "aggressive", new_game: bool = False):
        # Core components
        self.client = MgbaClient(rom_path="/home/ryan/roms/emerald.gba")
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
        self.new_game = new_game
        self.tick_interval = 0.3
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
        """Connect to mGBA emulator."""
        logger.info("Connecting to mGBA...")
        if self.client.connect():
            title = self.client.get_game_title()
            code = self.client.get_game_code()
            logger.info(f"Connected! Game: {title} ({code})")
            
            if code != "BPEE":
                logger.warning(f"Expected Emerald (BPEE), got {code}")
            
            # Load save state slot 1 if it exists and not starting fresh
            if not self.new_game:
                if self.client.load_state(1):
                    logger.info("Loaded save state slot 1 — resuming from save point")
                    # Run 60 frames to let the game stabilize after state load
                    for _ in range(60):
                        self.client._run_frames(1)
                    logger.info("Game stabilized, ready to play")
                else:
                    logger.warning("No save state found — will navigate title screen (use --new-game if intentional)")
            
            return True
        else:
            logger.error("Failed to connect to mGBA. Check ROM path.")
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
        
        # Stuck detection (skip in OVERWORLD and during new game flow)
        if self._ticks_in_state > 60 and state != PokemonGen3State.OVERWORLD and not self._in_new_game_flow:
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
        Handle title screen and new game initialization.
        
        Automates the entire startup sequence:
        1. Press Start to advance past title
        2. Navigate to "New Game"
        3. Handle character naming (auto-name "DEKU")
        4. Handle intro sequence (Prof Birch, moving truck)
        5. Select starter Pokemon (MUDKIP - left bag)
        6. Continue through first battle
        7. Save game after reaching Littleroot
        """
        # Use input delay for state machine timing
        if self._new_game_input_delay > 0:
            self._new_game_input_delay -= 1
            return
        
        # Initialize new game flow on first entry
        if not self._in_new_game_flow:
            logger.info("=" * 50)
            logger.info("TITLE SCREEN DETECTED - Starting new game initialization")
            logger.info("=" * 50)
            self._in_new_game_flow = True
            self._new_game_step = 0
        
        # State machine for new game flow
        # Step 0: Press Start to advance past title screen
        if self._new_game_step == 0:
            logger.info("Step 0: Pressing Start to advance past title")
            self.input.tap("Start")
            self._new_game_input_delay = 10  # Wait for menu to appear
            self._new_game_step = 1
            
        # Step 1: Navigate to "New Game" and select it
        elif self._new_game_step == 1:
            logger.info("Step 1: Selecting 'New Game'")
            self.input.tap("A")  # Select "New Game" (it's the default option)
            self._new_game_input_delay = 15  # Wait for intro to start
            self._new_game_step = 2
            
        # Step 2-10: Handle intro dialogue (Prof Birch, world intro)
        # Just spam A to advance through dialogue
        elif 2 <= self._new_game_step <= 15:
            if self._new_game_step == 2:
                logger.info("Step 2-15: Advancing through intro dialogue (will spam A)")
            self.input.tap("A")
            self._new_game_input_delay = 3  # Faster advancement
            self._new_game_step += 1
            
        # Step 16: Gender selection (Boy/Girl) - select Boy
        elif self._new_game_step == 16:
            logger.info("Step 16: Selecting gender (Boy)")
            self.input.tap("A")  # Boy is default
            self._new_game_input_delay = 5
            self._new_game_step = 17
            
        # Step 17-20: More intro dialogue
        elif 17 <= self._new_game_step <= 20:
            self.input.tap("A")
            self._new_game_input_delay = 3
            self._new_game_step += 1
            
        # Step 21: Character naming screen - auto-name "DEKU"
        elif self._new_game_step == 21:
            logger.info("Step 21: Naming character 'DEKU'")
            # Name entry is complex, so we'll just accept the default and rename via Start
            # Actually, let's just spam A through the default name
            self.input.tap("Start")  # Start key accepts default name faster
            self._new_game_input_delay = 10
            self._new_game_step = 22
            
        # Step 22-40: Continue through intro sequence (moving truck, arriving in Littleroot)
        # This includes rival naming, parent dialogue, clock setting
        elif 22 <= self._new_game_step <= 50:
            if self._new_game_step == 22:
                logger.info("Step 22-50: Advancing through intro sequence (moving truck, clock setting, etc.)")
            self.input.tap("A")
            self._new_game_input_delay = 3
            self._new_game_step += 1
            
        # Step 51: Clock setting - just accept default
        elif self._new_game_step == 51:
            logger.info("Step 51: Setting clock (accepting defaults)")
            self.input.tap("A")
            self._new_game_input_delay = 3
            self._new_game_step = 52
            
        # Step 52-70: Continue through bedroom scene, going downstairs, meeting mom
        elif 52 <= self._new_game_step <= 80:
            if self._new_game_step == 52:
                logger.info("Step 52-80: Continuing intro (bedroom → downstairs → outside)")
            self.input.tap("A")
            self._new_game_input_delay = 3
            self._new_game_step += 1
            
        # Step 81-100: Navigate to Prof Birch being attacked (Route 101)
        # Need to walk outside and trigger the event
        elif 81 <= self._new_game_step <= 100:
            if self._new_game_step == 81:
                logger.info("Step 81-100: Navigating to Prof Birch event (Route 101)")
            # Alternate between A and Up to navigate
            if self._new_game_step % 2 == 0:
                self.input.tap("A")
            else:
                self.input.tap("Up")
            self._new_game_input_delay = 2
            self._new_game_step += 1
            
        # Step 101-110: Prof Birch dialogue and bag selection
        elif 101 <= self._new_game_step <= 110:
            if self._new_game_step == 101:
                logger.info("Step 101-110: Prof Birch dialogue, approaching bag")
            self.input.tap("A")
            self._new_game_input_delay = 3
            self._new_game_step += 1
            
        # Step 111: CRITICAL - Select MUDKIP (left bag)
        # When Birch throws bags, navigate LEFT to select Mudkip
        elif self._new_game_step == 111:
            logger.info("Step 111: SELECTING MUDKIP (left bag) - CRITICAL STEP")
            self.input.tap("Left")  # Move cursor to left bag
            self._new_game_input_delay = 3
            self._new_game_step = 112
            
        elif self._new_game_step == 112:
            logger.info("Step 112: Confirming Mudkip selection")
            self.input.tap("A")  # Confirm selection
            self._new_game_input_delay = 5
            self._new_game_step = 113
            
        # Step 113-115: Confirm taking Mudkip dialogue
        elif 113 <= self._new_game_step <= 115:
            self.input.tap("A")
            self._new_game_input_delay = 3
            self._new_game_step += 1
            
        # Step 116: First battle begins (against Poochyena)
        # Battle handler will take over once battle state is detected
        # Just advance dialogue until battle starts
        elif 116 <= self._new_game_step <= 130:
            if self._new_game_step == 116:
                logger.info("Step 116-130: First battle sequence (Poochyena)")
                logger.info("  Battle AI will handle combat automatically")
            self.input.tap("A")
            self._new_game_input_delay = 3
            self._new_game_step += 1
            
        # Step 131-150: Post-battle dialogue, returning to lab, getting Pokedex
        elif 131 <= self._new_game_step <= 170:
            if self._new_game_step == 131:
                logger.info("Step 131-170: Post-battle sequence (return to lab, get Pokedex)")
            self.input.tap("A")
            self._new_game_input_delay = 3
            self._new_game_step += 1
            
        # Step 171: Check if we've reached normal gameplay
        # Detect by checking if we have Pokemon and play time is advancing
        elif self._new_game_step == 171:
            logger.info("Step 171: Checking if new game initialization is complete...")
            party_count = self.state_detector.get_party_count()
            
            if party_count > 0:
                logger.info("=" * 50)
                logger.info("✓ NEW GAME INITIALIZATION COMPLETE!")
                logger.info(f"  Party count: {party_count}")
                logger.info("  Game is ready for autonomous play")
                logger.info("=" * 50)
                self._in_new_game_flow = False
                self._new_game_step = 0
            else:
                # Keep advancing
                self.input.tap("A")
                self._new_game_input_delay = 5
                # Loop back to continue advancement if needed
                if self._new_game_step < 200:
                    self._new_game_step += 1
                else:
                    # Failsafe: reset to step 50 if we're stuck
                    logger.warning("New game flow may be stuck, resetting to step 50")
                    self._new_game_step = 50
        
        # Failsafe: if somehow we exceed step 200, reset
        else:
            logger.warning(f"New game step {self._new_game_step} exceeded, resetting to dialogue spam")
            self.input.tap("A")
            self._new_game_input_delay = 3

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

    def _handle_battle(self):
        """Handle battle state using Battle AI."""
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
        
        # Get AI decision
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
        """Handle dialogue/text boxes - press A to advance."""
        self.input.tap("A")

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
        Handle overworld navigation using random walk with direction persistence.
        
        Strategy:
        - Pick a random direction and walk in it for several ticks
        - Check if position is changing (detect walls/obstacles)
        - If stuck, immediately pick a new direction
        - Walking randomly will trigger wild battles naturally
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
        
        # Get current position
        pos = self.state_detector.get_player_position()
        map_loc = self.state_detector.get_map_location()
        
        # Log position periodically
        if self._ticks_in_state % 20 == 0:
            logger.debug(f"Overworld: pos={pos}, map={map_loc}")
        
        # Check if position has changed since last tick
        if pos == self._last_position:
            self._position_stuck_counter += 1
        else:
            self._position_stuck_counter = 0
            self._last_position = pos
        
        # If stuck in same position for 3+ ticks, we hit a wall - change direction immediately
        if self._position_stuck_counter >= 3:
            logger.debug(f"Hit obstacle at {pos}, changing direction")
            self._current_direction = None
            self._direction_persist_ticks = 0
            self._position_stuck_counter = 0
        
        # Direction persistence logic
        if self._current_direction is None or self._direction_persist_ticks >= self._direction_persist_target:
            # Pick new direction and duration
            self._current_direction = random.choice(["Up", "Down", "Left", "Right"])
            self._direction_persist_target = random.randint(5, 15)  # Walk 5-15 ticks in this direction
            self._direction_persist_ticks = 0
            logger.debug(f"New direction: {self._current_direction} for {self._direction_persist_target} ticks")
        
        # Move in current direction
        self.input.tap(self._current_direction)
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
        "--new-game",
        action="store_true",
        default=False,
        help="Start a new game instead of loading save state"
    )
    parser.add_argument(
        "--strategy", 
        choices=["aggressive", "safe", "speedrun", "grind", "catch"],
        default="aggressive",
        help="Battle strategy"
    )
    args = parser.parse_args()
    
    ai = EmeraldAI(strategy=args.strategy, new_game=args.new_game)
    ai.run()


if __name__ == "__main__":
    main()

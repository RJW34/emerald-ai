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
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.emulator.bizhawk_client import BizHawkClient
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

    def __init__(self, strategy: str = "aggressive"):
        # Core components
        self.client = BizHawkClient()
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
        self.configuring_settings = False  # Flag to pause main loop during menu navigation

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
        
        # Skip all processing if settings configuration is in progress
        if self.configuring_settings:
            return
        
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
        
        # Stuck detection (skip in OVERWORLD - has its own position-based stuck handler)
        if self._ticks_in_state > 60 and state != PokemonGen3State.OVERWORLD:
            self._handle_stuck()
        
        # Dispatch to handler
        if self.state_detector.in_battle:
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

    def _configure_game_settings(self, retry_attempt: int = 0):
        """
        One-time configuration of game settings to optimal values.
        
        This executes a fixed sequence to:
        1. Open Start menu
        2. Navigate to Options
        3. Set Text Speed to Fast
        4. Set Battle Scene to Off
        5. Set Battle Style to Set
        6. Exit back to overworld
        
        Called once per session when settings are detected as non-optimal.
        Includes retry logic and extended delays for BizHawk IPC reliability.
        
        Args:
            retry_attempt: Current retry attempt number (0-indexed)
        """
        max_retries = 3
        
        # Pause main game loop to prevent IPC race conditions
        self.configuring_settings = True
        
        logger.info("=" * 50)
        logger.info(f"CONFIGURING GAME SETTINGS (Attempt {retry_attempt + 1}/{max_retries + 1})")
        logger.info("=" * 50)
        
        # Read initial settings
        initial = self.state_detector.read_options()
        logger.info(f"Initial: Text={initial['text_speed']}, "
                   f"Scene={initial['battle_scene']}, Style={initial['battle_style']} "
                   f"(raw=0x{initial['raw']:02X})")
        
        # Open Start menu
        logger.info("[1/6] Opening Start menu...")
        self.input.hold("Start", frames=8)  # Hold for ~8 frames for reliability
        time.sleep(2.0)  # Increased delay for menu to fully open
        
        # Navigate to Options (6 downs from top in Emerald start menu)
        logger.info("[2/6] Navigating to Options...")
        for i in range(6):
            self.input.tap("Down")
            time.sleep(0.2)  # Increased delay between menu navigations
        time.sleep(1.0)  # Extra delay before selecting
        
        # Select Options
        logger.info("[3/6] Opening Options menu...")
        self.input.hold("A", frames=8)
        time.sleep(2.5)  # Increased delay for Options menu to open
        
        # Now in Options menu - configure settings
        # Default cursor position is on first option (Text Speed)
        
        # 1. Set Text Speed to Fast (value 2)
        logger.info("[4/6] Setting Text Speed to Fast...")
        # Press Up a few times to ensure we're at Text Speed
        for i in range(3):
            self.input.tap("Up")
            time.sleep(0.15)
        time.sleep(0.5)
        
        # Press Right to cycle: Slow(0) -> Mid(1) -> Fast(2)
        # Press Right 3 times to guarantee Fast regardless of starting position
        for i in range(3):
            self.input.tap("Right")
            time.sleep(0.4)  # Increased delay to ensure game registers each press
        time.sleep(1.0)
        
        # 2. Set Battle Scene to Off (value 1)
        logger.info("[5/6] Setting Battle Scene to Off...")
        self.input.tap("Down")  # Move to Battle Scene
        time.sleep(0.5)
        
        # Read current value to determine toggle direction
        # For reliability, just press Right twice to cycle through both states
        for i in range(2):
            self.input.tap("Right")
            time.sleep(0.4)
        time.sleep(1.0)
        
        # 3. Set Battle Style to Set (value 1)
        logger.info("[6/6] Setting Battle Style to Set...")
        self.input.tap("Down")  # Move to Battle Style
        time.sleep(0.5)
        
        # Press Right twice to cycle through both states
        for i in range(2):
            self.input.tap("Right")
            time.sleep(0.4)
        time.sleep(1.0)
        
        # Exit Options menu
        logger.info("Exiting Options menu...")
        self.input.hold("B", frames=8)
        time.sleep(2.0)  # Wait for menu to close
        
        # Press B again to close Start menu if still open
        self.input.tap("B")
        time.sleep(1.5)
        
        # CRITICAL: Wait for game to commit settings to Save Block 2 in memory
        logger.info("Waiting for game to commit settings to memory...")
        time.sleep(4.0)  # Extended delay before verification
        
        # Verify settings were applied
        logger.info("Verifying settings...")
        final = self.state_detector.read_options()
        logger.info(f"Final: Text={final['text_speed']}, "
                   f"Scene={final['battle_scene']}, Style={final['battle_style']} "
                   f"(raw=0x{final['raw']:02X})")
        
        if self.state_detector.verify_optimal_settings():
            logger.info("✓ Settings configured successfully!")
            logger.info("=" * 50)
            self._settings_configured = True
            self.configuring_settings = False  # Resume main game loop
            return True
        else:
            logger.warning(f"⚠ Settings verification failed!")
            logger.warning(f"  Expected: Text=2, Scene=1, Style=1")
            logger.warning(f"  Got: Text={final['text_speed']}, "
                         f"Scene={final['battle_scene']}, Style={final['battle_style']}")
            
            # Retry logic
            if retry_attempt < max_retries:
                logger.warning(f"Retrying configuration (attempt {retry_attempt + 2}/{max_retries + 1})...")
                time.sleep(2.0)  # Brief pause before retry
                return self._configure_game_settings(retry_attempt + 1)
            else:
                logger.error(f"⚠ Settings configuration failed after {max_retries + 1} attempts!")
                logger.error("  Game may not respond properly to IPC timing.")
                logger.error("  Continuing with non-optimal settings...")
                logger.info("=" * 50)
                self._settings_configured = True  # Mark as attempted to avoid infinite loop
                self.configuring_settings = False  # Resume main game loop
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
                # Settings not optimal - run configuration sequence
                self._configure_game_settings()
                return  # Skip this tick, settings config took time
            else:
                logger.info("✓ Settings already optimal!")
                self._settings_configured = True
        
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

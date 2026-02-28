#!/usr/bin/env python3
"""
Emerald AI Decision Loop

Minimal autonomous decision loop for Pokemon Emerald running in mGBA.
Reads game state from the game_state_server (port 8776) and sends
inputs via xdotool through MGBAController.

Modes:
  - title_screen: Navigate through title/new game menus
  - overworld: Wander randomly (directional inputs + A)
  - in_battle: Spam A to attack (basic proof-of-concept)
"""

import json
import logging
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mgba_xdotool_controller import MGBAController

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_PATH = Path(__file__).parent / "ai_loop.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH, mode="a"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("emerald-ai-loop")

POLL_DELAY = 0.2  # 200ms between polls

# ---------------------------------------------------------------------------
# Title Screen / New Game Navigation
# ---------------------------------------------------------------------------

class TitleScreenNavigator:
    """
    Navigate from title screen through to gameplay.

    Pokemon Emerald title screen flow (no save):
      1. Intro animation plays → press Start/A to skip
      2. Main menu appears with "NEW GAME" highlighted → press A
      3. Professor Birch intro → press A through dialogue
      4. Boy/Girl selection → press A (default = Boy)
      5. Name entry → press A to confirm default name
      ... eventually drops into overworld

    Since we can't see exact menu state (game_state_server only sees
    memory-level flags), we use a timed sequence of presses.
    """

    def __init__(self, ctrl: MGBAController):
        self.ctrl = ctrl
        self.presses_sent = 0
        self.phase = "initial"  # initial, menu, intro
        self.started_at = time.monotonic()

    def step(self, state: dict) -> str:
        """
        Send one input toward getting past the title screen.
        Returns a description of what was done.
        """
        status = state.get("status", "unknown")

        if status != "title_screen":
            return f"status changed to {status}, stopping title nav"

        elapsed = time.monotonic() - self.started_at

        # For the first few seconds, just press A/Start to skip intros
        if self.presses_sent < 5:
            self.ctrl.press_a()
            self.presses_sent += 1
            return f"title: press A (skip intro, press #{self.presses_sent})"

        if self.presses_sent < 10:
            self.ctrl.press_start()
            self.presses_sent += 1
            return f"title: press Start (press #{self.presses_sent})"

        # Alternate A presses to get through menus/dialogue
        self.ctrl.press_a()
        self.presses_sent += 1
        return f"title: press A (dialogue/menu, press #{self.presses_sent})"


# ---------------------------------------------------------------------------
# Overworld Wandering
# ---------------------------------------------------------------------------

class OverworldWanderer:
    """
    Random wandering in the overworld.
    Presses directional keys and occasionally A to interact.
    """

    DIRECTIONS = ["up", "down", "left", "right"]

    def __init__(self, ctrl: MGBAController):
        self.ctrl = ctrl
        self.last_direction = None
        self.steps_in_direction = 0
        self.max_steps = random.randint(3, 8)

    def step(self, state: dict) -> str:
        """Take one wandering action. Returns description."""
        # 15% chance to press A (interact with NPCs, signs, etc.)
        if random.random() < 0.15:
            self.ctrl.press_a()
            return "overworld: press A (interact)"

        # 5% chance to press B (cancel dialogue boxes)
        if random.random() < 0.05:
            self.ctrl.press_b()
            return "overworld: press B (cancel)"

        # Walk in a direction — prefer continuing same direction for a bit
        if self.steps_in_direction >= self.max_steps or self.last_direction is None:
            self.last_direction = random.choice(self.DIRECTIONS)
            self.steps_in_direction = 0
            self.max_steps = random.randint(3, 8)

        self.ctrl.press_button(self.last_direction)
        self.steps_in_direction += 1

        location = state.get("location", {})
        map_name = location.get("map_name", "unknown") if isinstance(location, dict) else "unknown"

        return f"overworld: walk {self.last_direction} (step {self.steps_in_direction}/{self.max_steps}) at {map_name}"


# ---------------------------------------------------------------------------
# Battle Handler
# ---------------------------------------------------------------------------

class BattleHandler:
    """
    Minimal battle logic: spam A to select the first move.
    Just enough to prove the input loop works.
    """

    def __init__(self, ctrl: MGBAController):
        self.ctrl = ctrl
        self.turn_count = 0

    def step(self, state: dict) -> str:
        """Take one battle action. Returns description."""
        self.turn_count += 1

        # Every few presses, mix in B to dismiss result text
        if self.turn_count % 5 == 0:
            self.ctrl.press_b()
            return f"battle: press B (dismiss text, turn {self.turn_count})"

        # Press A to select Fight → first move
        self.ctrl.press_a()
        return f"battle: press A (attack, turn {self.turn_count})"


# ---------------------------------------------------------------------------
# Main Loop
# ---------------------------------------------------------------------------

def main():
    log.info("=" * 60)
    log.info("Emerald AI Loop starting")
    log.info("=" * 60)

    try:
        ctrl = MGBAController()
        log.info(f"Connected to mGBA window {ctrl.window_id}")
    except RuntimeError as e:
        log.error(f"Failed to connect to mGBA: {e}")
        sys.exit(1)

    # Initial state check
    state = ctrl.get_game_state()
    log.info(f"Initial state: {json.dumps(state)}")

    # Initialize handlers
    title_nav = TitleScreenNavigator(ctrl)
    wanderer = OverworldWanderer(ctrl)
    battle = BattleHandler(ctrl)

    last_status = None
    error_count = 0

    while True:
        try:
            state = ctrl.get_game_state()
            status = state.get("status", "unknown")

            # Log status changes
            if status != last_status:
                log.info(f"Status changed: {last_status} -> {status}")
                last_status = status
                # Reset handlers on status change
                if status == "title_screen":
                    title_nav = TitleScreenNavigator(ctrl)
                elif status == "in_battle":
                    battle = BattleHandler(ctrl)
                elif status in ("overworld", "in_game"):
                    wanderer = OverworldWanderer(ctrl)

            # Dispatch based on status
            if status == "error":
                error_count += 1
                if error_count > 10:
                    log.error("Too many consecutive errors, sleeping 5s")
                    time.sleep(5)
                    error_count = 0
                action = f"error: {state.get('error', 'unknown')}"

            elif status == "title_screen":
                error_count = 0
                action = title_nav.step(state)

            elif status == "in_battle":
                error_count = 0
                action = battle.step(state)

            elif status in ("overworld", "in_game"):
                error_count = 0
                action = wanderer.step(state)

            else:
                error_count = 0
                # Unknown status — press A as a safe default
                ctrl.press_a()
                action = f"unknown status '{status}': press A"

            log.info(f"[{status}] {action}")

        except KeyboardInterrupt:
            log.info("Shutting down (KeyboardInterrupt)")
            break
        except Exception as e:
            log.error(f"Unhandled exception: {e}", exc_info=True)
            time.sleep(1)

        time.sleep(POLL_DELAY)

    log.info("Emerald AI Loop stopped")


if __name__ == "__main__":
    main()

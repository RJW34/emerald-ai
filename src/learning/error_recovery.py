"""
Error Recovery System

Handles recovery from stuck states using:
1. Previously successful recovery actions (from database)
2. Vision API suggestions
3. Default recovery strategies
4. Escalating intervention levels
"""

import logging
import random
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..input_controller import InputController
    from ..games.pokemon_gen3.state_detector import PokemonGen3StateDetector

from .stuck_detector import StuckReason, StuckDetector
from .vision_analyzer import VisionAnalyzer
from .database import get_database, StuckRecord

logger = logging.getLogger(__name__)


class RecoveryLevel(Enum):
    """Escalating levels of recovery intervention."""
    MINIMAL = auto()     # Simple retry, press A/B
    MODERATE = auto()    # Try different direction, cancel menus
    AGGRESSIVE = auto()  # Random movement, reset position
    VISION = auto()      # Use Vision API
    SAVESTATE = auto()   # Load previous save state


@dataclass
class RecoveryAttempt:
    """Record of a recovery attempt."""
    level: RecoveryLevel
    action: str
    success: bool
    timestamp: str


class ErrorRecoverySystem:
    """
    Manages recovery from stuck states with escalating strategies.

    Usage:
        recovery = ErrorRecoverySystem(stuck_detector, input_controller,
                                        state_detector, vision_analyzer)

        # When stuck:
        if stuck_detector.is_stuck:
            recovery.attempt_recovery()
    """

    # Recovery attempt limits before escalation
    MAX_ATTEMPTS_PER_LEVEL = 3
    MAX_TOTAL_ATTEMPTS = 20  # Reset to MINIMAL after this many total attempts

    # Default recovery actions by stuck reason
    DEFAULT_RECOVERIES: dict[StuckReason, list[str]] = {
        StuckReason.POSITION_UNCHANGED: ["A", "B", "Up", "Down", "Left", "Right"],
        StuckReason.MOVEMENT_BLOCKED: ["B", "opposite_direction", "A"],
        StuckReason.OSCILLATING: ["stop", "wait", "B"],
        StuckReason.STATE_LOOP: ["B", "Start", "A"],
        StuckReason.OBJECTIVE_UNREACHABLE: ["B", "recalculate_path"],
        StuckReason.UNKNOWN: ["A", "B", "random_direction"],
    }

    def __init__(self,
                 stuck_detector: StuckDetector,
                 input_controller: "InputController",
                 state_detector: "PokemonGen3StateDetector",
                 vision_analyzer: Optional[VisionAnalyzer] = None):
        """
        Initialize the error recovery system.

        Args:
            stuck_detector: For reading stuck state
            input_controller: For executing recovery actions
            state_detector: For reading game state
            vision_analyzer: Optional vision API for advanced recovery
        """
        self.stuck_detector = stuck_detector
        self.input = input_controller
        self.state_detector = state_detector
        self.vision = vision_analyzer
        self.db = get_database()

        # Recovery state
        self._current_level = RecoveryLevel.MINIMAL
        self._attempts_at_level = 0
        self._total_attempts = 0  # Total attempts across all levels
        self._recovery_history: list[RecoveryAttempt] = []
        self._last_direction: Optional[str] = None

        # Track current recovery sequence for learning
        self._current_sequence: list[str] = []

    def attempt_recovery(self) -> bool:
        """
        Attempt to recover from stuck state.

        Returns:
            True if recovery action was executed
        """
        if not self.stuck_detector.is_stuck:
            self._reset_recovery_state()
            return False

        reason = self.stuck_detector.stuck_reason

        try:
            position = self.state_detector.get_player_position()
            map_loc = self.state_detector.get_map_location()
        except Exception:
            position = (0, 0)
            map_loc = (0, 0)

        logger.info(f"Attempting recovery (level={self._current_level.name}, "
                   f"reason={reason.name}, attempts={self._attempts_at_level})")

        # Build context key for action sequence lookup
        context = f"{map_loc}:{position}:{reason.name}"

        # Check for previously successful sequence at this exact context
        known_sequence = self.db.get_best_action_sequence(context)
        if known_sequence and self._attempts_at_level == 0:
            logger.info(f"Using learned recovery sequence: {known_sequence}")
            for action in known_sequence:
                self._execute_action(action, reason)
                self._current_sequence.append(action)
            return True

        # Check for previously successful recovery at this location
        known_recovery = self.db.get_successful_recovery_for_location(
            map_loc[0], map_loc[1], position[0], position[1], reason.name
        )
        if known_recovery:
            logger.info(f"Using known successful recovery: {known_recovery}")
            self._current_sequence.append(known_recovery)
            return self._execute_action(known_recovery, reason)

        # Check if we've exceeded max total attempts - reset to start fresh
        if self._total_attempts >= self.MAX_TOTAL_ATTEMPTS:
            logger.warning(f"Max total recovery attempts ({self.MAX_TOTAL_ATTEMPTS}) reached - resetting to MINIMAL")
            self._current_level = RecoveryLevel.MINIMAL
            self._attempts_at_level = 0
            self._total_attempts = 0

        # Escalate if needed
        if self._attempts_at_level >= self.MAX_ATTEMPTS_PER_LEVEL:
            self._escalate_level()

        # Execute recovery based on current level
        action = self._get_recovery_action(reason)
        success = self._execute_action(action, reason)

        # Track in current sequence for learning
        self._current_sequence.append(action)

        # Record attempt
        self._recovery_history.append(RecoveryAttempt(
            level=self._current_level,
            action=action,
            success=success,
            timestamp=datetime.now().isoformat()
        ))

        self._attempts_at_level += 1
        self._total_attempts += 1
        return success

    def _get_recovery_action(self, reason: StuckReason) -> str:
        """Get the next recovery action to try."""

        if self._current_level == RecoveryLevel.VISION:
            # Try Vision API
            if self.vision and self.vision.is_available:
                logger.info("Attempting Vision API recovery analysis...")
                suggested = self.vision.suggest_recovery_action(reason.name)
                if suggested:
                    logger.info(f"Vision API suggested: {suggested}")
                    return suggested
                else:
                    logger.warning("Vision API returned no suggestion")
            else:
                logger.warning("Vision API not available, escalating")
            # Fall back if Vision unavailable/failed
            self._escalate_level()

        if self._current_level == RecoveryLevel.SAVESTATE:
            return "load_state"

        # Get default actions for this reason
        actions = self.DEFAULT_RECOVERIES.get(reason, ["A", "B"])

        # Resolve special actions
        resolved_actions = []
        for action in actions:
            if action == "opposite_direction":
                resolved_actions.append(self._get_opposite_direction())
            elif action == "random_direction":
                resolved_actions.append(random.choice(["Up", "Down", "Left", "Right"]))
            else:
                resolved_actions.append(action)

        # Cycle through actions based on attempt count
        # Guard against empty list (shouldn't happen but be safe)
        if not resolved_actions:
            resolved_actions = ["A", "B"]
        index = self._attempts_at_level % len(resolved_actions)
        return resolved_actions[index]

    def _execute_action(self, action: str, reason: StuckReason) -> bool:
        """Execute a recovery action."""
        logger.debug(f"Executing recovery action: {action}")

        # Stop any current movement first
        self.input.stop_walking()

        if action in ("Up", "Down", "Left", "Right"):
            self._last_direction = action
            self.input.walk(action)
            return True

        elif action in ("A", "B", "Start", "Select"):
            self.input.tap(action)
            return True

        elif action == "stop":
            return True  # Already stopped

        elif action == "wait":
            import time
            time.sleep(0.5)
            return True

        elif action == "load_state":
            # This would need access to BizHawkClient
            logger.warning("Load state recovery not implemented")
            return False

        elif action == "recalculate_path":
            # Signal to navigation system to recalculate
            logger.info("Signaling path recalculation")
            return True

        else:
            logger.warning(f"Unknown recovery action: {action}")
            return False

    def _get_opposite_direction(self) -> str:
        """Get the opposite of the last movement direction."""
        opposites = {"Up": "Down", "Down": "Up", "Left": "Right", "Right": "Left"}
        if self._last_direction:
            return opposites.get(self._last_direction, "Up")
        return "Up"

    def _escalate_level(self) -> None:
        """Escalate to the next recovery level."""
        levels = list(RecoveryLevel)
        current_index = levels.index(self._current_level)

        if current_index < len(levels) - 1:
            self._current_level = levels[current_index + 1]
            self._attempts_at_level = 0
            logger.info(f"Escalating recovery to level: {self._current_level.name}")

    def _reset_recovery_state(self) -> None:
        """Reset recovery state when no longer stuck."""
        if self._current_level != RecoveryLevel.MINIMAL:
            logger.info("Recovery successful - resetting state")
        self._current_level = RecoveryLevel.MINIMAL
        self._attempts_at_level = 0
        self._total_attempts = 0
        self._current_sequence = []  # Clear sequence for next recovery

    def record_recovery_outcome(self, success: bool) -> None:
        """
        Record whether recovery was successful.

        Call this after recovery when we know the outcome.
        """
        if not self._recovery_history:
            return

        last_attempt = self._recovery_history[-1]
        last_attempt.success = success

        # Store in database
        try:
            position = self.state_detector.get_player_position()
            map_loc = self.state_detector.get_map_location()
        except Exception:
            position = (0, 0)
            map_loc = (0, 0)

        reason = self.stuck_detector.stuck_reason

        record = StuckRecord(
            id=None,
            map_group=map_loc[0],
            map_num=map_loc[1],
            x=position[0],
            y=position[1],
            reason=reason.name,
            recovery_action=last_attempt.action,
            recovery_success=success,
            ticks_stuck=self.stuck_detector.ticks_stuck,
            timestamp=datetime.now().isoformat()
        )
        self.db.store_stuck_event(record)

        # If successful, save the recovery sequence for future use
        if success and self._current_sequence:
            context = f"{map_loc}:{position}:{reason.name}"
            self.db.store_action_sequence(context, self._current_sequence, success=True)
            logger.info(f"Saved successful recovery sequence: {self._current_sequence}")

        self.stuck_detector.mark_recovery_attempted(success)

        # Clear sequence for next recovery
        self._current_sequence = []

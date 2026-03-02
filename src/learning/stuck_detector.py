"""
Stuck Detection System

Monitors player position and game state to detect when the bot is stuck.
Triggers are:
1. Position unchanged for N ticks
2. Same state repeated N times
3. Movement attempted but position unchanged (blocked)
4. Oscillation detected (back-and-forth movement)
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..games.pokemon_gen3.state_detector import PokemonGen3StateDetector

logger = logging.getLogger(__name__)


class StuckReason(Enum):
    """Categorization of why the bot is stuck."""
    NOT_STUCK = auto()
    POSITION_UNCHANGED = auto()      # Hasn't moved in N ticks
    MOVEMENT_BLOCKED = auto()        # Trying to move but can't
    OSCILLATING = auto()             # Moving back and forth
    STATE_LOOP = auto()              # Same game state repeated
    OBJECTIVE_UNREACHABLE = auto()   # Can't path to objective
    UNKNOWN = auto()


@dataclass
class StuckEvent:
    """Record of a stuck occurrence."""
    timestamp: float
    reason: StuckReason
    position: tuple[int, int]
    map_location: tuple[int, int]
    ticks_stuck: int
    attempted_direction: Optional[str] = None
    recovery_attempted: bool = False
    recovery_succeeded: bool = False


@dataclass
class MovementAttempt:
    """Record of a movement attempt for pattern detection."""
    tick: int
    direction: str
    start_position: tuple[int, int]
    end_position: tuple[int, int]
    successful: bool  # Did position actually change?


class StuckDetector:
    """
    Monitors bot state to detect when it's stuck.

    Usage:
        detector = StuckDetector(state_detector)

        # In game loop:
        detector.update(current_tick)
        if detector.is_stuck:
            reason = detector.stuck_reason
            # Handle stuck state
    """

    # Configuration
    POSITION_UNCHANGED_THRESHOLD = 15    # Ticks without movement = stuck
    OSCILLATION_WINDOW = 10              # Ticks to check for oscillation
    OSCILLATION_THRESHOLD = 4            # Back-forth count to trigger
    MOVEMENT_BLOCKED_THRESHOLD = 3       # Failed moves before "blocked"
    STATE_LOOP_THRESHOLD = 20            # Same state repeats = stuck
    CLEAR_STUCK_THRESHOLD = 3            # Must move 3 ticks before clearing stuck

    def __init__(self, state_detector: "PokemonGen3StateDetector"):
        """
        Initialize the stuck detector.

        Args:
            state_detector: Game state detector for position/state reading
        """
        self.state_detector = state_detector

        # Position tracking
        self._position_history: deque[tuple[int, int]] = deque(maxlen=50)
        self._last_position: Optional[tuple[int, int]] = None
        self._ticks_at_position: int = 0
        self._ticks_moving: int = 0  # Consecutive ticks with movement (for clearing stuck)

        # Movement tracking
        self._movement_history: deque[MovementAttempt] = deque(maxlen=20)
        self._current_direction: Optional[str] = None
        self._failed_movement_count: int = 0

        # State tracking
        self._state_history: deque[str] = deque(maxlen=30)

        # Stuck state
        self._is_stuck: bool = False
        self._stuck_reason: StuckReason = StuckReason.NOT_STUCK
        self._stuck_events: list[StuckEvent] = []
        self._current_tick: int = 0

    def update(self, tick: int, attempted_direction: Optional[str] = None) -> None:
        """
        Update detector with current game state.

        Call this every tick in the game loop.

        Args:
            tick: Current tick number
            attempted_direction: Direction bot tried to move (if any)
        """
        self._current_tick = tick

        # Read current position and state
        try:
            position = self.state_detector.get_player_position()
            state = getattr(self.state_detector, 'current_state', None)
            state_name = state.name if state else "UNKNOWN"
        except Exception as e:
            logger.debug(f"Failed to read state in stuck detector: {e}")
            return

        # Update histories
        self._position_history.append(position)
        self._state_history.append(state_name)

        # Track movement attempt
        if attempted_direction:
            self._record_movement_attempt(attempted_direction, position)

        # Check for stuck conditions
        self._check_position_unchanged(position)
        self._check_movement_blocked(position, attempted_direction)
        self._check_oscillation()
        self._check_state_loop()

        # Update last position
        self._last_position = position

    def _record_movement_attempt(self, direction: str, current_pos: tuple[int, int]) -> None:
        """Record a movement attempt for pattern analysis."""
        if self._last_position is None:
            return

        successful = current_pos != self._last_position

        attempt = MovementAttempt(
            tick=self._current_tick,
            direction=direction,
            start_position=self._last_position,
            end_position=current_pos,
            successful=successful
        )
        self._movement_history.append(attempt)
        self._current_direction = direction

        if not successful:
            self._failed_movement_count += 1
        else:
            self._failed_movement_count = 0

    def _check_position_unchanged(self, position: tuple[int, int]) -> None:
        """Check if position has been unchanged for too long."""
        if self._last_position == position:
            self._ticks_at_position += 1
            self._ticks_moving = 0  # Reset moving counter
        else:
            self._ticks_at_position = 0
            self._ticks_moving += 1  # Increment moving counter

        if self._ticks_at_position >= self.POSITION_UNCHANGED_THRESHOLD:
            self._set_stuck(StuckReason.POSITION_UNCHANGED)
        elif self._stuck_reason == StuckReason.POSITION_UNCHANGED:
            # Require sustained movement before clearing (prevents oscillation)
            if self._ticks_moving >= self.CLEAR_STUCK_THRESHOLD:
                self._clear_stuck()

    def _check_movement_blocked(self, position: tuple[int, int], direction: Optional[str]) -> None:
        """Check if movement is being blocked."""
        if direction is None:
            return

        if self._failed_movement_count >= self.MOVEMENT_BLOCKED_THRESHOLD:
            self._set_stuck(StuckReason.MOVEMENT_BLOCKED)
        elif self._stuck_reason == StuckReason.MOVEMENT_BLOCKED:
            # Require sustained successful movement before clearing
            if self._failed_movement_count == 0 and self._ticks_moving >= self.CLEAR_STUCK_THRESHOLD:
                self._clear_stuck()

    def _check_oscillation(self) -> None:
        """Check for back-and-forth movement pattern."""
        if len(self._movement_history) < self.OSCILLATION_WINDOW:
            return

        recent = list(self._movement_history)[-self.OSCILLATION_WINDOW:]

        # Count direction reversals
        reversals = 0
        opposite = {"Up": "Down", "Down": "Up", "Left": "Right", "Right": "Left"}

        for i in range(1, len(recent)):
            if recent[i].direction == opposite.get(recent[i-1].direction):
                reversals += 1

        if reversals >= self.OSCILLATION_THRESHOLD:
            self._set_stuck(StuckReason.OSCILLATING)
        elif self._stuck_reason == StuckReason.OSCILLATING:
            # Require sustained low reversals AND movement before clearing
            if reversals < 2 and self._ticks_moving >= self.CLEAR_STUCK_THRESHOLD:
                self._clear_stuck()

    def _check_state_loop(self) -> None:
        """Check for repeated state patterns.

        Note: DIALOGUE state is excluded from state loop detection because
        the bot is supposed to be stationary during dialogue, pressing A to advance.
        """
        if len(self._state_history) < self.STATE_LOOP_THRESHOLD:
            return

        recent = list(self._state_history)[-self.STATE_LOOP_THRESHOLD:]

        # Don't trigger state loop for DIALOGUE - that's expected behavior
        # during dialogue, the bot presses A repeatedly in the same state
        if len(set(recent)) == 1:
            repeated_state = recent[0]
            if repeated_state not in ("DIALOGUE", "UNKNOWN"):
                self._set_stuck(StuckReason.STATE_LOOP)
        elif self._stuck_reason == StuckReason.STATE_LOOP:
            # Require multiple different states before clearing
            if len(set(recent)) > 1 and self._ticks_moving >= self.CLEAR_STUCK_THRESHOLD:
                self._clear_stuck()

    def _set_stuck(self, reason: StuckReason) -> None:
        """Set stuck state and record event."""
        if self._is_stuck and self._stuck_reason == reason:
            return  # Already stuck for this reason

        self._is_stuck = True
        self._stuck_reason = reason

        try:
            position = self.state_detector.get_player_position()
            map_loc = self.state_detector.get_map_location()
        except Exception:
            position = (0, 0)
            map_loc = (0, 0)

        event = StuckEvent(
            timestamp=time.time(),
            reason=reason,
            position=position,
            map_location=map_loc,
            ticks_stuck=self._ticks_at_position,
            attempted_direction=self._current_direction
        )
        self._stuck_events.append(event)

        logger.warning(f"STUCK DETECTED: {reason.name} at pos={position}, map={map_loc}")

    def _clear_stuck(self) -> None:
        """Clear stuck state."""
        if self._is_stuck:
            logger.info(f"No longer stuck (was: {self._stuck_reason.name})")
        self._is_stuck = False
        self._stuck_reason = StuckReason.NOT_STUCK

    @property
    def is_stuck(self) -> bool:
        """Check if currently stuck."""
        return self._is_stuck

    @property
    def stuck_reason(self) -> StuckReason:
        """Get reason for being stuck."""
        return self._stuck_reason

    @property
    def ticks_stuck(self) -> int:
        """Get number of ticks at current position."""
        return self._ticks_at_position

    @property
    def stuck_events(self) -> list[StuckEvent]:
        """Get history of stuck events."""
        return self._stuck_events.copy()

    def get_recent_positions(self, count: int = 10) -> list[tuple[int, int]]:
        """Get recent position history."""
        return list(self._position_history)[-count:]

    def mark_recovery_attempted(self, success: bool = False) -> None:
        """Mark that recovery was attempted for the current stuck event."""
        if self._stuck_events:
            self._stuck_events[-1].recovery_attempted = True
            self._stuck_events[-1].recovery_succeeded = success

    def reset(self) -> None:
        """Reset all tracking state."""
        self._position_history.clear()
        self._movement_history.clear()
        self._state_history.clear()
        self._last_position = None
        self._ticks_at_position = 0
        self._ticks_moving = 0
        self._failed_movement_count = 0
        self._is_stuck = False
        self._stuck_reason = StuckReason.NOT_STUCK

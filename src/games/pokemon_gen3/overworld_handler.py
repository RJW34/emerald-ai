"""
Overworld Navigation Handler

Handles overworld movement using pathfinding and learned coordinates.
"""

import json
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ...input_controller import InputController
    from .state_detector import PokemonGen3StateDetector

from ...learning.pathfinder import Pathfinder
from ...learning.coordinate_learner import CoordinateLearner
from ...learning.stuck_detector import StuckDetector
from ...learning.database import get_database, RouteAttempt

logger = logging.getLogger(__name__)


class OverworldHandler:
    """
    Handles autonomous overworld navigation.

    Usage:
        handler = OverworldHandler(state_detector, input_controller)

        # Set navigation target
        handler.set_target(x=10, y=5)

        # In game loop:
        handler.tick()
    """

    def __init__(self,
                 state_detector: "PokemonGen3StateDetector",
                 input_controller: "InputController",
                 stuck_detector: Optional[StuckDetector] = None,
                 coordinate_learner: Optional[CoordinateLearner] = None):
        """
        Initialize the overworld handler.
        """
        self.state_detector = state_detector
        self.input = input_controller
        self.stuck_detector = stuck_detector
        self.coordinate_learner = coordinate_learner

        # Initialize pathfinder
        self.pathfinder = Pathfinder(state_detector)

        # Navigation state
        self._target: Optional[tuple[int, int]] = None
        self._target_map: Optional[tuple[int, int]] = None
        self._last_position: Optional[tuple[int, int]] = None
        self._ticks_at_position: int = 0

        # Route tracking for learning
        self._route_start_time: Optional[float] = None
        self._route_start_pos: Optional[tuple[int, int]] = None
        self._route_start_map: Optional[tuple[int, int]] = None
        self._route_path: list[tuple[int, int]] = []
        self.db = get_database()

    def set_target(self, x: int, y: int,
                   map_group: Optional[int] = None,
                   map_num: Optional[int] = None) -> bool:
        """
        Set navigation target.

        Args:
            x: Target X coordinate
            y: Target Y coordinate
            map_group: Target map group (current map if not specified)
            map_num: Target map number (current map if not specified)

        Returns:
            True if path found to target
        """
        # Record route start for tracking
        self._route_start_time = time.time()
        try:
            self._route_start_pos = self.state_detector.get_player_position()
            self._route_start_map = self.state_detector.get_map_location()
        except Exception:
            self._route_start_pos = (0, 0)
            self._route_start_map = (0, 0)
        self._route_path = [self._route_start_pos] if self._route_start_pos else []

        self._target = (x, y)

        if map_group is not None and map_num is not None:
            self._target_map = (map_group, map_num)
        else:
            try:
                self._target_map = self.state_detector.get_map_location()
            except Exception:
                self._target_map = (0, 0)

        # Calculate path
        path = self.pathfinder.find_path(x, y)
        return len(path) > 0

    def set_target_map(self, map_group: int, map_num: int) -> bool:
        """
        Set target to a different map (finds warp).

        Uses learned coordinates to find warps.
        """
        if not self.coordinate_learner:
            logger.error("CoordinateLearner required for cross-map navigation")
            return False

        try:
            current_map = self.state_detector.get_map_location()
        except Exception:
            logger.error("Failed to get current map location")
            return False

        warp_coords = self.coordinate_learner.get_warp_to_map(
            current_map, (map_group, map_num)
        )

        if warp_coords:
            return self.set_target(warp_coords[0], warp_coords[1])
        else:
            logger.warning(f"No known warp from {current_map} to ({map_group}, {map_num})")
            return False

    def tick(self) -> None:
        """
        Execute one navigation tick.

        Call this in the main game loop when in overworld state.
        """
        if not self._target:
            return

        try:
            current_pos = self.state_detector.get_player_position()
            current_map = self.state_detector.get_map_location()
        except Exception as e:
            logger.debug(f"Failed to read position in overworld handler: {e}")
            return

        # Track path for route logging
        if self._route_path and current_pos != self._route_path[-1]:
            self._route_path.append(current_pos)

        # Check if reached target
        if current_pos == self._target and current_map == self._target_map:
            logger.info(f"Reached target: {self._target}")
            self._record_route_attempt(success=True)
            self._target = None
            self.input.stop_walking()
            return

        # Track position changes
        if current_pos == self._last_position:
            self._ticks_at_position += 1
        else:
            # Moved - only record as walkable if moving TOWARD target
            if self.coordinate_learner and self._is_moving_toward_target(current_pos, self._last_position):
                self.coordinate_learner.record_successful_path(
                    current_map[0], current_map[1],
                    current_pos[0], current_pos[1]
                )
            self._ticks_at_position = 0

        self._last_position = current_pos

        # Handle stuck (movement blocked)
        if self._ticks_at_position > 5:
            self._handle_blocked()
            return

        # Get next direction from pathfinder
        direction = self.pathfinder.get_next_direction()

        if direction:
            self.input.walk(direction)
        else:
            # No path - set stuck flag instead of infinite recalculation
            logger.warning("No path direction - marking target unreachable")
            self._record_route_attempt(success=False, failure_reason="no_path")
            self._target = None  # Clear target to stop navigation
            self.input.stop_walking()

    def _is_moving_toward_target(self, current: tuple[int, int], previous: tuple[int, int]) -> bool:
        """Check if movement reduced distance to target."""
        if not self._target or not previous:
            return False
        prev_dist = abs(previous[0] - self._target[0]) + abs(previous[1] - self._target[1])
        curr_dist = abs(current[0] - self._target[0]) + abs(current[1] - self._target[1])
        return curr_dist < prev_dist

    def _handle_blocked(self) -> None:
        """Handle when movement is blocked."""
        try:
            current_pos = self.state_detector.get_player_position()
        except Exception:
            return

        # The tile we're trying to reach is blocked
        direction = self.pathfinder.get_next_direction()
        if direction:
            # Calculate blocked tile position
            dx = {"Right": 1, "Left": -1}.get(direction, 0)
            dy = {"Down": 1, "Up": -1}.get(direction, 0)
            blocked_tile = (current_pos[0] + dx, current_pos[1] + dy)

            # Mark as obstacle
            self.pathfinder.add_obstacle(blocked_tile[0], blocked_tile[1])
            logger.info(f"Marked obstacle at {blocked_tile}")

            # Recalculate path avoiding this obstacle
            self.pathfinder.recalculate_path()

        self._ticks_at_position = 0

    def clear_target(self) -> None:
        """Clear current navigation target."""
        if self._target:
            self._record_route_attempt(success=False, failure_reason="target_cleared")
        self._target = None
        self._target_map = None
        self.pathfinder.clear_path()
        self.input.stop_walking()

    def _record_route_attempt(self, success: bool, failure_reason: Optional[str] = None) -> None:
        """Record a route attempt to the database."""
        if not self._route_start_time or not self._route_start_pos or not self._route_start_map:
            return
        if not self._target or not self._target_map:
            return

        elapsed = time.time() - self._route_start_time

        attempt = RouteAttempt(
            id=None,
            start_map=self._route_start_map,
            start_pos=self._route_start_pos,
            target_map=self._target_map,
            target_pos=self._target,
            success=success,
            steps_taken=len(self._route_path),
            time_elapsed=elapsed,
            path_taken=json.dumps(self._route_path),
            failure_reason=failure_reason,
            timestamp=datetime.now().isoformat()
        )

        self.db.store_route_attempt(attempt)
        logger.debug(f"Recorded route attempt: success={success}, steps={len(self._route_path)}")

        # Reset tracking
        self._route_start_time = None
        self._route_start_pos = None
        self._route_start_map = None
        self._route_path = []

    @property
    def is_navigating(self) -> bool:
        """Check if currently navigating."""
        return self._target is not None

    @property
    def target(self) -> Optional[tuple[int, int]]:
        """Get current target position."""
        return self._target

"""
A* Pathfinding System

Provides pathfinding for overworld navigation using:
- Learned obstacle data from database
- Dynamic obstacle detection during movement
- Path caching for efficiency
"""

import heapq
import logging
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..games.pokemon_gen3.state_detector import PokemonGen3StateDetector

from .database import get_database
from ..data.map_loader import get_map_loader

logger = logging.getLogger(__name__)


@dataclass(order=True)
class PathNode:
    """Node in the A* search."""
    f_score: float
    position: tuple[int, int] = field(compare=False)
    g_score: float = field(compare=False)
    parent: Optional["PathNode"] = field(compare=False, default=None)


class Pathfinder:
    """
    A* pathfinder for Pokemon Emerald overworld navigation.

    Usage:
        pathfinder = Pathfinder(state_detector)

        # Find path to target
        path = pathfinder.find_path(target_x=10, target_y=5)

        # Get next direction to move
        direction = pathfinder.get_next_direction()
    """

    # Movement costs
    MOVE_COST = 1.0
    DIAGONAL_COST = 1.414  # Not used in Pokemon (4-directional only)

    # Search limits
    MAX_SEARCH_ITERATIONS = 1000
    MAX_PATH_LENGTH = 200

    # Directions (4-way movement)
    DIRECTIONS = [
        (0, -1, "Up"),
        (0, 1, "Down"),
        (-1, 0, "Left"),
        (1, 0, "Right"),
    ]

    def __init__(self, state_detector: "PokemonGen3StateDetector"):
        """
        Initialize the pathfinder.

        Args:
            state_detector: For reading current position and map
        """
        self.state_detector = state_detector
        self.db = get_database()

        # Current path state
        self._current_path: list[tuple[int, int]] = []
        self._path_index: int = 0
        self._target: Optional[tuple[int, int]] = None

        # Obstacle cache (cleared on map change)
        self._cached_obstacles: set[tuple[int, int]] = set()
        self._cached_map: Optional[tuple[int, int]] = None

    def find_path(self, target_x: int, target_y: int,
                  map_group: Optional[int] = None,
                  map_num: Optional[int] = None) -> list[tuple[int, int]]:
        """
        Find a path to the target position using A*.

        Args:
            target_x: Target X coordinate
            target_y: Target Y coordinate
            map_group: Map group (uses current if not specified)
            map_num: Map number (uses current if not specified)

        Returns:
            List of (x, y) positions forming the path, empty if no path found
        """
        # Get current position
        try:
            start = self.state_detector.get_player_position()
        except Exception as e:
            logger.error(f"Failed to get player position for pathfinding: {e}")
            return []

        target = (target_x, target_y)

        if start == target:
            return []

        # Get map for obstacle lookup
        if map_group is None or map_num is None:
            try:
                current_map = self.state_detector.get_map_location()
                map_group = current_map[0]
                map_num = current_map[1]
            except Exception:
                map_group = 0
                map_num = 0

        # Load obstacles
        self._load_obstacles(map_group, map_num)

        # A* search
        path = self._astar(start, target)

        if path:
            self._current_path = path
            self._path_index = 0
            self._target = target
            logger.info(f"Path found: {len(path)} steps from {start} to {target}")
        else:
            logger.warning(f"No path found from {start} to {target}")

        return path

    def _astar(self, start: tuple[int, int],
               target: tuple[int, int]) -> list[tuple[int, int]]:
        """Execute A* pathfinding algorithm."""

        # Priority queue: (f_score, node)
        open_set: list[PathNode] = []

        # Track visited nodes
        closed_set: set[tuple[int, int]] = set()

        # Track best g_score for each position
        g_scores: dict[tuple[int, int], float] = {start: 0}

        # Start node
        start_node = PathNode(
            f_score=self._heuristic(start, target),
            position=start,
            g_score=0
        )
        heapq.heappush(open_set, start_node)

        iterations = 0

        while open_set and iterations < self.MAX_SEARCH_ITERATIONS:
            iterations += 1

            # Get node with lowest f_score
            current = heapq.heappop(open_set)

            # Check if we reached target
            if current.position == target:
                return self._reconstruct_path(current)

            # Skip if already processed
            if current.position in closed_set:
                continue

            closed_set.add(current.position)

            # Explore neighbors
            for dx, dy, _ in self.DIRECTIONS:
                neighbor_pos = (current.position[0] + dx, current.position[1] + dy)

                # Skip if already processed or blocked
                if neighbor_pos in closed_set:
                    continue
                if neighbor_pos in self._cached_obstacles:
                    continue

                # Calculate scores
                tentative_g = current.g_score + self.MOVE_COST

                # Skip if we already have a better path to this neighbor
                if neighbor_pos in g_scores and tentative_g >= g_scores[neighbor_pos]:
                    continue

                # This is the best path to neighbor so far
                g_scores[neighbor_pos] = tentative_g

                neighbor_node = PathNode(
                    f_score=tentative_g + self._heuristic(neighbor_pos, target),
                    position=neighbor_pos,
                    g_score=tentative_g,
                    parent=current
                )
                heapq.heappush(open_set, neighbor_node)

        logger.warning(f"A* search exhausted after {iterations} iterations")
        return []

    def _heuristic(self, pos: tuple[int, int], target: tuple[int, int]) -> float:
        """Calculate heuristic (Manhattan distance)."""
        return abs(pos[0] - target[0]) + abs(pos[1] - target[1])

    def _reconstruct_path(self, end_node: PathNode) -> list[tuple[int, int]]:
        """Reconstruct path from end node to start."""
        path = []
        current: Optional[PathNode] = end_node

        while current is not None:
            path.append(current.position)
            current = current.parent

            if len(path) > self.MAX_PATH_LENGTH:
                logger.warning("Path reconstruction exceeded max length")
                break

        path.reverse()
        return path[1:]  # Exclude starting position

    def _load_obstacles(self, map_group: int, map_num: int) -> None:
        """Load obstacles from database AND pre-computed map data."""
        current_map = (map_group, map_num)

        # Clear cache if map changed
        if self._cached_map != current_map:
            self._cached_obstacles.clear()
            self._cached_map = current_map

            # Load learned obstacles from database
            obstacles = self.db.get_obstacles_for_map(map_group, map_num)
            for x, y, _ in obstacles:
                self._cached_obstacles.add((x, y))

            db_count = len(self._cached_obstacles)

            # Load pre-computed NPC positions from map data
            try:
                map_loader = get_map_loader()
                npc_positions = map_loader.get_npc_positions(map_group, map_num)
                for x, y in npc_positions:
                    self._cached_obstacles.add((x, y))

                # Also add NPC wander zones as soft obstacles
                zones = map_loader.get_npc_movement_zones(map_group, map_num)
                for base_x, base_y, range_x, range_y in zones:
                    for dx in range(-range_x, range_x + 1):
                        for dy in range(-range_y, range_y + 1):
                            self._cached_obstacles.add((base_x + dx, base_y + dy))

            except Exception as e:
                logger.debug(f"Could not load map data for obstacles: {e}")

            logger.debug(f"Loaded {len(self._cached_obstacles)} obstacles for map {current_map} ({db_count} from DB)")

    def get_next_direction(self) -> Optional[str]:
        """
        Get the next direction to move along the current path.

        Returns:
            Direction string ("Up", "Down", "Left", "Right") or None if no path
        """
        if not self._current_path or self._path_index >= len(self._current_path):
            return None

        try:
            current_pos = self.state_detector.get_player_position()
        except Exception:
            return None

        next_pos = self._current_path[self._path_index]

        # Check if we've reached the next waypoint
        if current_pos == next_pos:
            self._path_index += 1
            if self._path_index >= len(self._current_path):
                return None
            next_pos = self._current_path[self._path_index]

        # Calculate direction
        dx = next_pos[0] - current_pos[0]
        dy = next_pos[1] - current_pos[1]

        if dx > 0:
            return "Right"
        elif dx < 0:
            return "Left"
        elif dy > 0:
            return "Down"
        elif dy < 0:
            return "Up"

        return None

    def add_obstacle(self, x: int, y: int) -> None:
        """
        Add a dynamically discovered obstacle.

        Call this when movement fails to a tile.
        """
        self._cached_obstacles.add((x, y))

        # Also store in database
        if self._cached_map:
            self.db.store_obstacle(
                self._cached_map[0], self._cached_map[1],
                x, y, "discovered"
            )

    def clear_path(self) -> None:
        """Clear the current path."""
        self._current_path = []
        self._path_index = 0
        self._target = None

    def recalculate_path(self) -> list[tuple[int, int]]:
        """Recalculate path to current target."""
        if self._target:
            return self.find_path(self._target[0], self._target[1])
        return []

    @property
    def has_path(self) -> bool:
        """Check if there's a current path."""
        return len(self._current_path) > 0 and self._path_index < len(self._current_path)

    @property
    def path_progress(self) -> float:
        """Get progress along current path (0.0 to 1.0)."""
        if not self._current_path:
            return 0.0
        return self._path_index / len(self._current_path)

    @property
    def remaining_steps(self) -> int:
        """Get remaining steps in current path."""
        return max(0, len(self._current_path) - self._path_index)

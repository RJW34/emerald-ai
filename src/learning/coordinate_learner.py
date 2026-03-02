"""
Coordinate Discovery System

Learns map coordinates through gameplay:
- Detects warp triggers when map changes
- Records NPC positions when interaction occurs
- Learns obstacle positions from failed movements
- Verifies coordinates through repeated success
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..games.pokemon_gen3.state_detector import PokemonGen3StateDetector

from .database import (
    get_database,
    CoordinateRecord,
    LearningDatabase
)
from ..data.map_loader import get_map_loader, MAP_ID_TO_COORDS

logger = logging.getLogger(__name__)


class CoordinateLearner:
    """
    Learns and verifies coordinates through gameplay observation.

    Usage:
        learner = CoordinateLearner(state_detector)

        # In game loop - call every tick
        learner.update()

        # Query learned data
        warps = learner.get_known_warps(map_group=1, map_num=0)
    """

    # Minimum verifications before trusting a coordinate
    VERIFICATION_THRESHOLD = 3

    def __init__(self, state_detector: "PokemonGen3StateDetector"):
        """
        Initialize the coordinate learner.

        Args:
            state_detector: Game state detector for position reading
        """
        self.state_detector = state_detector
        self.db = get_database()

        # State tracking for discovery
        self._last_position: Optional[tuple[int, int]] = None
        self._last_map: Optional[tuple[int, int]] = None
        self._pending_warp_discovery: Optional[tuple[int, int, int, int]] = None

        # Pre-load known coordinates from EmeraldMapInterfaceTool
        self._preload_known_coordinates()

    def _preload_known_coordinates(self) -> None:
        """
        Pre-load coordinates from EmeraldMapInterfaceTool map data.

        This seeds the database with known warps and NPC positions,
        reducing the need for dynamic discovery during gameplay.
        """
        try:
            map_loader = get_map_loader()
        except Exception as e:
            logger.warning(f"Could not load map data for pre-seeding: {e}")
            return

        preloaded_warps = 0
        preloaded_obstacles = 0

        for map_id in map_loader.get_all_map_ids():
            coords = map_loader.get_map_coords(map_id)
            if not coords:
                continue

            map_group, map_num = coords
            map_data = map_loader.load_map(map_id)
            if not map_data:
                continue

            # Pre-load warps
            for warp in map_data.warps:
                existing = self.db.get_coordinate(
                    map_group, map_num, warp.x, warp.y, "warp"
                )
                if not existing:
                    self.record_coordinate(
                        map_group=map_group,
                        map_num=map_num,
                        x=warp.x,
                        y=warp.y,
                        location_type="warp",
                        description=f"Warp to {warp.destination} (preloaded)"
                    )
                    preloaded_warps += 1

            # Pre-load stationary NPC positions as obstacles
            for npc in map_data.npcs:
                # Only mark stationary NPCs as obstacles
                if npc.movement in ("face_up", "face_down", "face_left", "face_right", "stationary"):
                    if not self.db.is_obstacle(map_group, map_num, npc.x, npc.y):
                        self.db.store_obstacle(map_group, map_num, npc.x, npc.y, "npc")
                        preloaded_obstacles += 1

        if preloaded_warps > 0 or preloaded_obstacles > 0:
            logger.info(f"Pre-loaded {preloaded_warps} warps and {preloaded_obstacles} NPC obstacles from map data")

    def update(self) -> None:
        """
        Update learner with current game state.

        Call this every tick. Detects transitions and records discoveries.
        """
        try:
            current_pos = self.state_detector.get_player_position()
            current_map = self.state_detector.get_map_location()
        except Exception as e:
            logger.debug(f"Failed to read position in coordinate learner: {e}")
            return

        # Detect map transition (warp)
        if self._last_map is not None and current_map != self._last_map:
            self._handle_map_transition(
                from_map=self._last_map,
                from_pos=self._last_position,
                to_map=current_map,
                to_pos=current_pos
            )

        # Update tracking state
        self._last_position = current_pos
        self._last_map = current_map

    def _handle_map_transition(self, from_map: tuple[int, int],
                                from_pos: Optional[tuple[int, int]],
                                to_map: tuple[int, int],
                                to_pos: tuple[int, int]) -> None:
        """Handle detection of a map transition (warp)."""
        if from_pos is None:
            return

        logger.info(f"Map transition detected: {from_map}@{from_pos} -> {to_map}@{to_pos}")

        # Record the warp exit point on the source map
        self.record_coordinate(
            map_group=from_map[0],
            map_num=from_map[1],
            x=from_pos[0],
            y=from_pos[1],
            location_type="warp",
            description=f"Warp to map {to_map}"
        )

        # Record the warp entry point on the destination map
        self.record_coordinate(
            map_group=to_map[0],
            map_num=to_map[1],
            x=to_pos[0],
            y=to_pos[1],
            location_type="warp_entry",
            description=f"Entry from map {from_map}"
        )

    def record_coordinate(self, map_group: int, map_num: int, x: int, y: int,
                          location_type: str, description: str) -> None:
        """
        Record a discovered coordinate.

        Args:
            map_group: Map group ID
            map_num: Map number within group
            x: X tile coordinate
            y: Y tile coordinate
            location_type: Type of location (warp, npc, item, obstacle, path)
            description: Human-readable description
        """
        record = CoordinateRecord(
            map_group=map_group,
            map_num=map_num,
            x=x,
            y=y,
            location_type=location_type,
            description=description,
            discovered_at=datetime.now().isoformat()
        )

        self.db.store_coordinate(record)
        logger.debug(f"Recorded coordinate: {location_type} at ({x}, {y}) on map ({map_group}, {map_num})")

    def record_obstacle(self, map_group: int, map_num: int, x: int, y: int,
                        obstacle_type: str = "unknown") -> None:
        """
        Record an obstacle/impassable tile.

        Call this when movement fails to a tile.

        Args:
            map_group: Map group ID
            map_num: Map number
            x: X coordinate of obstacle
            y: Y coordinate of obstacle
            obstacle_type: Type of obstacle (wall, npc, rock, water, etc.)
        """
        self.db.store_obstacle(map_group, map_num, x, y, obstacle_type)
        logger.debug(f"Recorded obstacle at ({x}, {y}) on map ({map_group}, {map_num})")

    def record_successful_path(self, map_group: int, map_num: int, x: int, y: int) -> None:
        """
        Record a tile that was successfully walked on.

        Args:
            map_group: Map group ID
            map_num: Map number
            x: X coordinate
            y: Y coordinate
        """
        self.record_coordinate(
            map_group=map_group,
            map_num=map_num,
            x=x,
            y=y,
            location_type="path",
            description="Walkable tile"
        )

    def get_known_warps(self, map_group: int, map_num: int) -> list[CoordinateRecord]:
        """Get all known warps for a map."""
        return self.db.get_warps_for_map(map_group, map_num)

    def get_verified_warps(self, map_group: int, map_num: int) -> list[CoordinateRecord]:
        """Get only verified warps for a map."""
        all_warps = self.get_known_warps(map_group, map_num)
        return [w for w in all_warps
                if w.verified and w.verification_count >= self.VERIFICATION_THRESHOLD]

    def is_known_obstacle(self, map_group: int, map_num: int, x: int, y: int) -> bool:
        """Check if a tile is a known obstacle."""
        return self.db.is_obstacle(map_group, map_num, x, y)

    def get_obstacles(self, map_group: int, map_num: int) -> list[tuple[int, int, str]]:
        """Get all known obstacles for a map."""
        return self.db.get_obstacles_for_map(map_group, map_num)

    def get_warp_to_map(self, from_map: tuple[int, int],
                        to_map: tuple[int, int]) -> Optional[tuple[int, int]]:
        """
        Find the warp coordinates to get from one map to another.

        Args:
            from_map: Current map (group, num)
            to_map: Target map (group, num)

        Returns:
            (x, y) coordinates of warp, or None if not known
        """
        warps = self.get_known_warps(from_map[0], from_map[1])
        target_str = f"Warp to map {to_map}"

        for warp in warps:
            if target_str in warp.description:
                return (warp.x, warp.y)

        return None

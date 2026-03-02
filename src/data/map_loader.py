"""
Map Data Loader

Loads pre-parsed map data from EmeraldMapInterfaceTool.
Provides warps, NPCs, triggers, and map metadata.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Data directory
DATA_DIR = Path(__file__).parent.parent.parent / "data"
MAPS_DIR = DATA_DIR / "maps"


@dataclass
class WarpData:
    """Warp point on a map."""
    x: int
    y: int
    destination: str
    dest_warp_id: int
    elevation: int = 0


@dataclass
class NPCData:
    """NPC on a map."""
    x: int
    y: int
    movement: str
    movement_range_x: int = 0
    movement_range_y: int = 0
    graphics_id: str = ""
    script: str = ""
    flag: Optional[str] = None  # Flag that hides this NPC
    local_id: Optional[str] = None


@dataclass
class TriggerData:
    """Event trigger on a map."""
    x: int
    y: int
    trigger_type: str
    var: str
    var_value: int
    script: str
    elevation: int = 0


@dataclass
class BgEventData:
    """Background event (sign, hidden item, etc.)."""
    x: int
    y: int
    event_type: str
    script: str
    player_facing_dir: str = ""
    elevation: int = 0


@dataclass
class ConnectionData:
    """Map connection to adjacent map."""
    direction: str  # north, south, east, west
    destination: str
    offset: int


@dataclass
class MapData:
    """Complete parsed map data."""
    id: str
    name: str
    width: int
    height: int
    map_type: str
    weather: str
    warps: list[WarpData] = field(default_factory=list)
    npcs: list[NPCData] = field(default_factory=list)
    triggers: list[TriggerData] = field(default_factory=list)
    bg_events: list[BgEventData] = field(default_factory=list)
    connections: list[ConnectionData] = field(default_factory=list)
    allow_cycling: bool = True
    allow_running: bool = True


# Map ID to (map_group, map_num) mapping
# From EmeraldMapInterfaceTool and memory_map.py
MAP_ID_TO_COORDS = {
    "LITTLEROOT_TOWN": (0, 9),
    "OLDALE_TOWN": (0, 10),
    "ROUTE101": (0, 16),
    "LITTLEROOT_TOWN_BRENDANS_HOUSE_1F": (1, 0),
    "LITTLEROOT_TOWN_BRENDANS_HOUSE_2F": (1, 1),
    "LITTLEROOT_TOWN_MAYS_HOUSE_1F": (1, 2),
    "LITTLEROOT_TOWN_MAYS_HOUSE_2F": (1, 3),
    "LITTLEROOT_TOWN_PROFESSOR_BIRCHS_LAB": (1, 4),
}

# Reverse mapping
COORDS_TO_MAP_ID = {v: k for k, v in MAP_ID_TO_COORDS.items()}


class MapDataLoader:
    """
    Loads and caches map data from JSON files.

    Usage:
        loader = MapDataLoader()

        # Load by map ID
        map_data = loader.load_map("LITTLEROOT_TOWN")

        # Load by coordinates
        map_data = loader.load_map_by_coords(0, 9)

        # Get warps
        warps = loader.get_warps("LITTLEROOT_TOWN")

        # Get NPC positions for pathfinding
        npcs = loader.get_npc_positions(0, 9)
    """

    def __init__(self, maps_dir: Optional[Path] = None):
        """
        Initialize the map loader.

        Args:
            maps_dir: Directory containing map JSON files
        """
        self.maps_dir = maps_dir or MAPS_DIR
        self._cache: dict[str, MapData] = {}
        self._load_all_maps()

    def _load_all_maps(self) -> None:
        """Load all map files on initialization."""
        if not self.maps_dir.exists():
            logger.warning(f"Maps directory not found: {self.maps_dir}")
            return

        for map_file in self.maps_dir.glob("*.json"):
            try:
                self._load_map_file(map_file)
            except Exception as e:
                logger.error(f"Failed to load map {map_file.name}: {e}")

        logger.info(f"Loaded {len(self._cache)} maps from {self.maps_dir}")

    def _load_map_file(self, path: Path) -> Optional[MapData]:
        """Load a single map file."""
        with open(path, 'r') as f:
            data = json.load(f)

        map_id = data.get("id", path.stem)

        # Parse warps
        warps = []
        for w in data.get("warps", []):
            warps.append(WarpData(
                x=w["x"],
                y=w["y"],
                destination=w.get("destination", ""),
                dest_warp_id=w.get("destWarpId", 0),
                elevation=w.get("elevation", 0)
            ))

        # Parse NPCs
        npcs = []
        for n in data.get("npcs", []):
            movement_range = n.get("movementRange", {})
            npcs.append(NPCData(
                x=n["x"],
                y=n["y"],
                movement=n.get("movement", "face_down"),
                movement_range_x=movement_range.get("x", 0),
                movement_range_y=movement_range.get("y", 0),
                graphics_id=n.get("graphicsId", ""),
                script=n.get("script", ""),
                flag=n.get("flag"),
                local_id=n.get("localId")
            ))

        # Parse triggers
        triggers = []
        for t in data.get("triggers", []):
            triggers.append(TriggerData(
                x=t["x"],
                y=t["y"],
                trigger_type=t.get("type", "trigger"),
                var=t.get("var", ""),
                var_value=t.get("varValue", 0),
                script=t.get("script", ""),
                elevation=t.get("elevation", 0)
            ))

        # Parse background events
        bg_events = []
        for bg in data.get("bgEvents", []):
            bg_events.append(BgEventData(
                x=bg["x"],
                y=bg["y"],
                event_type=bg.get("type", "sign"),
                script=bg.get("script", ""),
                player_facing_dir=bg.get("playerFacingDir", ""),
                elevation=bg.get("elevation", 0)
            ))

        # Parse connections
        connections = []
        conn_data = data.get("connections")
        if conn_data and isinstance(conn_data, dict):
            for direction, conn in conn_data.items():
                if conn:
                    connections.append(ConnectionData(
                        direction=direction,
                        destination=conn.get("map", ""),
                        offset=conn.get("offset", 0)
                    ))

        # Parse dimensions
        dimensions = data.get("dimensions", {})

        # Parse flags
        flags = data.get("flags", {})

        map_data = MapData(
            id=map_id,
            name=data.get("name", map_id),
            width=dimensions.get("width", 0),
            height=dimensions.get("height", 0),
            map_type=data.get("mapType", ""),
            weather=data.get("weather", ""),
            warps=warps,
            npcs=npcs,
            triggers=triggers,
            bg_events=bg_events,
            connections=connections,
            allow_cycling=flags.get("allowCycling", True),
            allow_running=flags.get("allowRunning", True)
        )

        self._cache[map_id] = map_data
        return map_data

    def load_map(self, map_id: str) -> Optional[MapData]:
        """
        Load map data by map ID.

        Args:
            map_id: Map identifier (e.g., "LITTLEROOT_TOWN")

        Returns:
            MapData or None if not found
        """
        return self._cache.get(map_id)

    def load_map_by_coords(self, map_group: int, map_num: int) -> Optional[MapData]:
        """
        Load map data by coordinates.

        Args:
            map_group: Map group number
            map_num: Map number within group

        Returns:
            MapData or None if not found
        """
        map_id = COORDS_TO_MAP_ID.get((map_group, map_num))
        if map_id:
            return self.load_map(map_id)
        return None

    def get_warps(self, map_id: str) -> list[WarpData]:
        """Get all warps for a map."""
        map_data = self.load_map(map_id)
        return map_data.warps if map_data else []

    def get_warps_by_coords(self, map_group: int, map_num: int) -> list[WarpData]:
        """Get all warps for a map by coordinates."""
        map_data = self.load_map_by_coords(map_group, map_num)
        return map_data.warps if map_data else []

    def get_warp_to(self, map_group: int, map_num: int,
                    destination: str) -> Optional[tuple[int, int]]:
        """
        Find warp coordinates to a specific destination.

        Args:
            map_group: Current map group
            map_num: Current map number
            destination: Destination map ID

        Returns:
            (x, y) coordinates of warp, or None
        """
        warps = self.get_warps_by_coords(map_group, map_num)
        for warp in warps:
            if destination in warp.destination:
                return (warp.x, warp.y)
        return None

    def get_npcs(self, map_id: str) -> list[NPCData]:
        """Get all NPCs for a map."""
        map_data = self.load_map(map_id)
        return map_data.npcs if map_data else []

    def get_npc_positions(self, map_group: int, map_num: int) -> list[tuple[int, int]]:
        """
        Get NPC positions for pathfinding obstacle avoidance.

        Returns base positions only - movement ranges should be
        considered separately for wandering NPCs.
        """
        map_data = self.load_map_by_coords(map_group, map_num)
        if not map_data:
            return []
        return [(npc.x, npc.y) for npc in map_data.npcs]

    def get_npc_movement_zones(self, map_group: int,
                                map_num: int) -> list[tuple[int, int, int, int]]:
        """
        Get NPC movement zones (areas they can wander).

        Returns list of (x, y, range_x, range_y) tuples.
        Useful for soft obstacle marking in pathfinding.
        """
        map_data = self.load_map_by_coords(map_group, map_num)
        if not map_data:
            return []

        zones = []
        for npc in map_data.npcs:
            if "wander" in npc.movement:
                zones.append((
                    npc.x, npc.y,
                    npc.movement_range_x, npc.movement_range_y
                ))
        return zones

    def get_triggers(self, map_group: int, map_num: int) -> list[TriggerData]:
        """Get event triggers for a map."""
        map_data = self.load_map_by_coords(map_group, map_num)
        return map_data.triggers if map_data else []

    def get_bg_events(self, map_group: int, map_num: int) -> list[BgEventData]:
        """Get background events for a map."""
        map_data = self.load_map_by_coords(map_group, map_num)
        return map_data.bg_events if map_data else []

    def get_map_dimensions(self, map_group: int,
                           map_num: int) -> Optional[tuple[int, int]]:
        """Get map dimensions (width, height)."""
        map_data = self.load_map_by_coords(map_group, map_num)
        if map_data:
            return (map_data.width, map_data.height)
        return None

    def get_connection(self, map_group: int, map_num: int,
                       direction: str) -> Optional[str]:
        """
        Get the map connected in a direction.

        Args:
            map_group: Current map group
            map_num: Current map number
            direction: "north", "south", "east", or "west"

        Returns:
            Connected map ID or None
        """
        map_data = self.load_map_by_coords(map_group, map_num)
        if not map_data:
            return None

        for conn in map_data.connections:
            if conn.direction == direction:
                return conn.destination
        return None

    def get_all_map_ids(self) -> list[str]:
        """Get list of all loaded map IDs."""
        return list(self._cache.keys())

    def get_map_coords(self, map_id: str) -> Optional[tuple[int, int]]:
        """Get (map_group, map_num) for a map ID."""
        return MAP_ID_TO_COORDS.get(map_id)


# Singleton instance
_loader_instance: Optional[MapDataLoader] = None


def get_map_loader() -> MapDataLoader:
    """Get the singleton map loader instance."""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = MapDataLoader()
    return _loader_instance

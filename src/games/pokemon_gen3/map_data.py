"""
Pokemon Emerald Map Database
Maps (map_group, map_num) tuples to location metadata for navigation.

Data source: pret/pokeemerald disassembly
https://github.com/pret/pokeemerald
"""

from typing import Dict, Tuple, Optional, TypedDict


class LocationData(TypedDict):
    """Metadata for a Pokemon Emerald location."""
    name: str
    type: str  # "city", "town", "route", "dungeon", "indoor"
    gym: bool
    poke_center: bool


# Map (group, num) tuples to location data
# Group 0 = TownsAndRoutes (outdoor areas)
# Group 1+ = Indoor locations
EMERALD_MAPS: Dict[Tuple[int, int], LocationData] = {
    # ===== GROUP 0: TOWNS AND ROUTES =====
    # Early game path: Littleroot → Route 101 → Oldale → Route 103/102 → Petalburg → Woods → Rustboro
    
    # Towns (Early Game)
    (0, 9): {"name": "Littleroot Town", "type": "town", "gym": False, "poke_center": False},
    (0, 10): {"name": "Oldale Town", "type": "town", "gym": False, "poke_center": True},
    (0, 11): {"name": "Dewford Town", "type": "town", "gym": True, "poke_center": True},
    (0, 12): {"name": "Lavaridge Town", "type": "town", "gym": True, "poke_center": True},
    (0, 13): {"name": "Fallarbor Town", "type": "town", "gym": False, "poke_center": True},
    (0, 14): {"name": "Verdanturf Town", "type": "town", "gym": False, "poke_center": True},
    (0, 15): {"name": "Pacifidlog Town", "type": "town", "gym": False, "poke_center": True},
    
    # Cities (Gym Locations)
    (0, 0): {"name": "Petalburg City", "type": "city", "gym": True, "poke_center": True},
    (0, 1): {"name": "Slateport City", "type": "city", "gym": False, "poke_center": True},
    (0, 2): {"name": "Mauville City", "type": "city", "gym": True, "poke_center": True},
    (0, 3): {"name": "Rustboro City", "type": "city", "gym": True, "poke_center": True},
    (0, 4): {"name": "Fortree City", "type": "city", "gym": True, "poke_center": True},
    (0, 5): {"name": "Lilycove City", "type": "city", "gym": False, "poke_center": True},
    (0, 6): {"name": "Mossdeep City", "type": "city", "gym": True, "poke_center": True},
    (0, 7): {"name": "Sootopolis City", "type": "city", "gym": True, "poke_center": True},
    (0, 8): {"name": "Ever Grande City", "type": "city", "gym": False, "poke_center": True},
    
    # Routes (Early Game - First 10)
    (0, 16): {"name": "Route 101", "type": "route", "gym": False, "poke_center": False},
    (0, 17): {"name": "Route 102", "type": "route", "gym": False, "poke_center": False},
    (0, 18): {"name": "Route 103", "type": "route", "gym": False, "poke_center": False},
    (0, 19): {"name": "Route 104", "type": "route", "gym": False, "poke_center": False},
    (0, 20): {"name": "Route 105", "type": "route", "gym": False, "poke_center": False},
    (0, 21): {"name": "Route 106", "type": "route", "gym": False, "poke_center": False},
    (0, 22): {"name": "Route 107", "type": "route", "gym": False, "poke_center": False},
    (0, 23): {"name": "Route 108", "type": "route", "gym": False, "poke_center": False},
    (0, 24): {"name": "Route 109", "type": "route", "gym": False, "poke_center": False},
    (0, 25): {"name": "Route 110", "type": "route", "gym": False, "poke_center": False},
    
    # Routes (Mid Game)
    (0, 26): {"name": "Route 111", "type": "route", "gym": False, "poke_center": False},
    (0, 27): {"name": "Route 112", "type": "route", "gym": False, "poke_center": False},
    (0, 28): {"name": "Route 113", "type": "route", "gym": False, "poke_center": False},
    (0, 29): {"name": "Route 114", "type": "route", "gym": False, "poke_center": False},
    (0, 30): {"name": "Route 115", "type": "route", "gym": False, "poke_center": False},
    (0, 31): {"name": "Route 116", "type": "route", "gym": False, "poke_center": False},
    (0, 32): {"name": "Route 117", "type": "route", "gym": False, "poke_center": False},
    (0, 33): {"name": "Route 118", "type": "route", "gym": False, "poke_center": False},
    (0, 34): {"name": "Route 119", "type": "route", "gym": False, "poke_center": False},
    (0, 35): {"name": "Route 120", "type": "route", "gym": False, "poke_center": False},
    (0, 36): {"name": "Route 121", "type": "route", "gym": False, "poke_center": False},
    (0, 37): {"name": "Route 122", "type": "route", "gym": False, "poke_center": False},
    (0, 38): {"name": "Route 123", "type": "route", "gym": False, "poke_center": False},
    (0, 39): {"name": "Route 124", "type": "route", "gym": False, "poke_center": False},
    (0, 40): {"name": "Route 125", "type": "route", "gym": False, "poke_center": False},
    (0, 41): {"name": "Route 126", "type": "route", "gym": False, "poke_center": False},
    (0, 42): {"name": "Route 127", "type": "route", "gym": False, "poke_center": False},
    (0, 43): {"name": "Route 128", "type": "route", "gym": False, "poke_center": False},
    (0, 44): {"name": "Route 129", "type": "route", "gym": False, "poke_center": False},
    (0, 45): {"name": "Route 130", "type": "route", "gym": False, "poke_center": False},
    (0, 46): {"name": "Route 131", "type": "route", "gym": False, "poke_center": False},
    (0, 47): {"name": "Route 132", "type": "route", "gym": False, "poke_center": False},
    (0, 48): {"name": "Route 133", "type": "route", "gym": False, "poke_center": False},
    (0, 49): {"name": "Route 134", "type": "route", "gym": False, "poke_center": False},
    
    # Underwater Routes
    (0, 50): {"name": "Underwater Route 124", "type": "route", "gym": False, "poke_center": False},
    (0, 51): {"name": "Underwater Route 126", "type": "route", "gym": False, "poke_center": False},
    (0, 52): {"name": "Underwater Route 127", "type": "route", "gym": False, "poke_center": False},
    (0, 53): {"name": "Underwater Route 128", "type": "route", "gym": False, "poke_center": False},
    (0, 54): {"name": "Underwater Route 129", "type": "route", "gym": False, "poke_center": False},
    (0, 55): {"name": "Underwater Route 105", "type": "route", "gym": False, "poke_center": False},
    (0, 56): {"name": "Underwater Route 125", "type": "route", "gym": False, "poke_center": False},
    
    # ===== GROUP 1: INDOOR LITTLEROOT =====
    (1, 0): {"name": "Littleroot Town - Brendan's House 1F", "type": "indoor", "gym": False, "poke_center": False},
    (1, 1): {"name": "Littleroot Town - Brendan's House 2F", "type": "indoor", "gym": False, "poke_center": False},
    (1, 2): {"name": "Littleroot Town - May's House 1F", "type": "indoor", "gym": False, "poke_center": False},
    (1, 3): {"name": "Littleroot Town - May's House 2F", "type": "indoor", "gym": False, "poke_center": False},
    (1, 4): {"name": "Littleroot Town - Professor Birch's Lab", "type": "indoor", "gym": False, "poke_center": False},
    
    # ===== GROUP 2: INDOOR OLDALE =====
    (2, 0): {"name": "Oldale Town - House 1", "type": "indoor", "gym": False, "poke_center": False},
    (2, 1): {"name": "Oldale Town - House 2", "type": "indoor", "gym": False, "poke_center": False},
    (2, 2): {"name": "Oldale Town - Pokemon Center 1F", "type": "indoor", "gym": False, "poke_center": True},
    (2, 3): {"name": "Oldale Town - Pokemon Center 2F", "type": "indoor", "gym": False, "poke_center": True},
    (2, 4): {"name": "Oldale Town - Mart", "type": "indoor", "gym": False, "poke_center": False},
    
    # ===== GROUP 8: INDOOR PETALBURG =====
    (8, 0): {"name": "Petalburg City - Wally's House", "type": "indoor", "gym": False, "poke_center": False},
    (8, 1): {"name": "Petalburg City - Gym", "type": "indoor", "gym": True, "poke_center": False},
    (8, 2): {"name": "Petalburg City - House 1", "type": "indoor", "gym": False, "poke_center": False},
    (8, 3): {"name": "Petalburg City - House 2", "type": "indoor", "gym": False, "poke_center": False},
    (8, 4): {"name": "Petalburg City - Pokemon Center 1F", "type": "indoor", "gym": False, "poke_center": True},
    (8, 5): {"name": "Petalburg City - Pokemon Center 2F", "type": "indoor", "gym": False, "poke_center": True},
    (8, 6): {"name": "Petalburg City - Mart", "type": "indoor", "gym": False, "poke_center": False},
    
    # ===== GROUP 11: INDOOR RUSTBORO =====
    (11, 0): {"name": "Rustboro City - Devon Corp 1F", "type": "indoor", "gym": False, "poke_center": False},
    (11, 1): {"name": "Rustboro City - Devon Corp 2F", "type": "indoor", "gym": False, "poke_center": False},
    (11, 2): {"name": "Rustboro City - Devon Corp 3F", "type": "indoor", "gym": False, "poke_center": False},
    (11, 3): {"name": "Rustboro City - Gym", "type": "indoor", "gym": True, "poke_center": False},
    (11, 4): {"name": "Rustboro City - Pokemon School", "type": "indoor", "gym": False, "poke_center": False},
    (11, 5): {"name": "Rustboro City - Pokemon Center 1F", "type": "indoor", "gym": False, "poke_center": True},
    (11, 6): {"name": "Rustboro City - Pokemon Center 2F", "type": "indoor", "gym": False, "poke_center": True},
    (11, 7): {"name": "Rustboro City - Mart", "type": "indoor", "gym": False, "poke_center": False},
    
    # ===== GROUP 24: DUNGEONS (Early Game) =====
    (24, 11): {"name": "Petalburg Woods", "type": "dungeon", "gym": False, "poke_center": False},
    (24, 4): {"name": "Rusturf Tunnel", "type": "dungeon", "gym": False, "poke_center": False},
    (24, 7): {"name": "Granite Cave 1F", "type": "dungeon", "gym": False, "poke_center": False},
    (24, 8): {"name": "Granite Cave B1F", "type": "dungeon", "gym": False, "poke_center": False},
    (24, 9): {"name": "Granite Cave B2F", "type": "dungeon", "gym": False, "poke_center": False},
    (24, 10): {"name": "Granite Cave - Steven's Room", "type": "dungeon", "gym": False, "poke_center": False},
}


def get_location_name(group: int, num: int) -> str:
    """
    Get human-readable location name from map group and number.
    
    Args:
        group: Map group ID (0-33 in Emerald)
        num: Map number within group
        
    Returns:
        Location name string, or "Unknown Location" if not found
        
    Example:
        >>> get_location_name(0, 9)
        'Littleroot Town'
        >>> get_location_name(0, 16)
        'Route 101'
        >>> get_location_name(24, 11)
        'Petalburg Woods'
    """
    location = EMERALD_MAPS.get((group, num))
    if location:
        return location["name"]
    return f"Unknown Location (Group {group}, Map {num})"


def get_location_data(group: int, num: int) -> Optional[LocationData]:
    """
    Get full location metadata from map group and number.
    
    Args:
        group: Map group ID
        num: Map number within group
        
    Returns:
        LocationData dict with name, type, gym, and poke_center fields,
        or None if location not found
        
    Example:
        >>> data = get_location_data(0, 0)
        >>> data['name']
        'Petalburg City'
        >>> data['gym']
        True
        >>> data['poke_center']
        True
    """
    return EMERALD_MAPS.get((group, num))


def has_pokemon_center(group: int, num: int) -> bool:
    """Check if a location has a Pokemon Center."""
    location = EMERALD_MAPS.get((group, num))
    return location["poke_center"] if location else False


def has_gym(group: int, num: int) -> bool:
    """Check if a location has a Gym."""
    location = EMERALD_MAPS.get((group, num))
    return location["gym"] if location else False


# Early game progression path for reference
EARLY_GAME_PATH = [
    (0, 9),   # Littleroot Town
    (0, 16),  # Route 101
    (0, 10),  # Oldale Town
    (0, 18),  # Route 103 (rival battle)
    (0, 17),  # Route 102
    (0, 0),   # Petalburg City (visit gym, can't battle yet)
    (0, 19),  # Route 104
    (24, 11), # Petalburg Woods
    (0, 3),   # Rustboro City (first gym)
]

"""
Mock BizHawk Client for testing the full AI pipeline without an emulator.

Simulates a Pokemon Emerald battle by maintaining in-memory state
and responding to memory reads with realistic values. Useful for:
- Running the AI loop offline
- Testing battle decision sequences end-to-end
- Benchmarking AI performance against known scenarios
"""

import logging
import struct
from typing import Optional

from ..games.pokemon_gen3.memory_map import PokemonGen3Memory as Mem
from ..games.pokemon_gen3.data_types import PokemonType, Weather

logger = logging.getLogger(__name__)


class MockBattlePokemon:
    """A simulated Pokemon for mock battles."""
    def __init__(self, species_id: int, level: int, hp: int, max_hp: int,
                 attack: int, defense: int, speed: int, sp_attack: int, sp_defense: int,
                 type1: int, type2: int, ability: int,
                 moves: list[tuple[int, int]],  # (move_id, pp) pairs
                 status: int = 0):
        self.species_id = species_id
        self.level = level
        self.hp = hp
        self.max_hp = max_hp
        self.attack = attack
        self.defense = defense
        self.speed = speed
        self.sp_attack = sp_attack
        self.sp_defense = sp_defense
        self.type1 = type1
        self.type2 = type2
        self.ability = ability
        self.moves = moves
        self.status = status

    def to_battle_struct(self) -> bytes:
        """Serialize to 88-byte battle mon struct matching memory layout."""
        data = bytearray(88)
        # species @ 0x00
        struct.pack_into('<H', data, 0x00, self.species_id)
        # stats @ 0x02-0x0B
        struct.pack_into('<H', data, 0x02, self.attack)
        struct.pack_into('<H', data, 0x04, self.defense)
        struct.pack_into('<H', data, 0x06, self.speed)
        struct.pack_into('<H', data, 0x08, self.sp_attack)
        struct.pack_into('<H', data, 0x0A, self.sp_defense)
        # moves @ 0x0C (4 x 2 bytes)
        for i, (move_id, _pp) in enumerate(self.moves[:4]):
            struct.pack_into('<H', data, 0x0C + i * 2, move_id)
        # ability @ 0x20, types @ 0x21-0x22
        data[0x20] = self.ability
        data[0x21] = self.type1
        data[0x22] = self.type2
        # PP @ 0x24 (4 x 1 byte)
        for i, (_mid, pp) in enumerate(self.moves[:4]):
            data[0x24 + i] = pp
        # HP @ 0x28, level @ 0x2A, max_hp @ 0x2C
        struct.pack_into('<H', data, 0x28, self.hp)
        data[0x2A] = self.level
        struct.pack_into('<H', data, 0x2C, self.max_hp)
        # status @ 0x4C
        struct.pack_into('<I', data, 0x4C, self.status)
        return bytes(data)


# Preset battle scenarios for testing
SCENARIOS = {
    "mudkip_vs_poochyena": {
        "description": "Early game: Lv5 Mudkip vs Lv2 wild Poochyena",
        "player": MockBattlePokemon(
            species_id=258, level=5, hp=20, max_hp=20,
            attack=12, defense=11, speed=9, sp_attack=11, sp_defense=11,
            type1=11, type2=11,  # Water
            ability=67,  # Torrent
            moves=[(33, 35), (45, 40)],  # Tackle, Growl
        ),
        "enemy": MockBattlePokemon(
            species_id=261, level=2, hp=11, max_hp=11,
            attack=7, defense=6, speed=6, sp_attack=5, sp_defense=5,
            type1=17, type2=17,  # Dark
            ability=50,  # Run Away
            moves=[(33, 35)],  # Tackle
        ),
        "battle_flags": 0x0004,  # Wild
        "weather": 0,
    },
    "blaziken_vs_flygon": {
        "description": "Mid-game: Lv36 Blaziken vs Lv35 Flygon",
        "player": MockBattlePokemon(
            species_id=257, level=36, hp=110, max_hp=110,
            attack=95, defense=60, speed=65, sp_attack=88, sp_defense=58,
            type1=10, type2=1,  # Fire/Fighting
            ability=66,  # Blaze
            moves=[(299, 10), (280, 15), (38, 15), (53, 15)],
            # Blaze Kick, Brick Break, Double-Edge, Flamethrower
        ),
        "enemy": MockBattlePokemon(
            species_id=330, level=35, hp=95, max_hp=95,
            attack=78, defense=62, speed=78, sp_attack=62, sp_defense=62,
            type1=4, type2=16,  # Ground/Dragon
            ability=26,  # Levitate
            moves=[(89, 10), (225, 20), (28, 15), (200, 15)],
            # Earthquake, DragonBreath, Sand Attack, Outrage
        ),
        "battle_flags": 0x0008,  # Trainer
        "weather": 0,
    },
    "swampert_vs_wailord_rain": {
        "description": "Late game: Lv45 Swampert vs Lv42 Wailord in Rain",
        "player": MockBattlePokemon(
            species_id=260, level=45, hp=155, max_hp=155,
            attack=105, defense=85, speed=55, sp_attack=78, sp_defense=82,
            type1=11, type2=4,  # Water/Ground
            ability=67,  # Torrent
            moves=[(57, 15), (89, 10), (58, 10), (280, 15)],
            # Surf, Earthquake, Ice Beam, Brick Break
        ),
        "enemy": MockBattlePokemon(
            species_id=321, level=42, hp=210, max_hp=210,
            attack=75, defense=38, speed=50, sp_attack=75, sp_defense=38,
            type1=11, type2=11,  # Water
            ability=11,  # Water Absorb
            moves=[(57, 15), (56, 5), (34, 15), (156, 10)],
            # Surf, Hydro Pump, Body Slam, Rest
        ),
        "battle_flags": 0x0004,  # Wild
        "weather": 0x03,  # Rain
    },
}


class MockBizHawkClient:
    """
    Mock BizHawk client that simulates memory reads for a battle scenario.
    
    Lets you test the full AI pipeline (state detection → battle AI → decisions)
    without needing BizHawk running.
    """

    def __init__(self, scenario_name: str = "mudkip_vs_poochyena"):
        self.scenario = SCENARIOS[scenario_name]
        self._connected = False
        
        # Build memory simulation
        self._battle_mon_data = bytearray(88 * 4)  # 4 battler slots
        player_data = self.scenario["player"].to_battle_struct()
        enemy_data = self.scenario["enemy"].to_battle_struct()
        self._battle_mon_data[0:88] = player_data
        self._battle_mon_data[88:176] = enemy_data
        
        # Save block pointers (fake valid EWRAM addresses)
        self._sb1_ptr = 0x02025A00
        self._sb2_ptr = 0x02024000
        
        # Minimal save block data
        self._save_block_1 = bytearray(0x2000)
        self._save_block_2 = bytearray(0x1000)

    def connect(self) -> bool:
        self._connected = True
        logger.info(f"MockClient: Connected ({self.scenario['description']})")
        return True

    def is_connected(self) -> bool:
        return self._connected

    def close(self):
        self._connected = False

    def read8(self, address: int) -> int:
        return self._read(address, 1)

    def read16(self, address: int) -> int:
        return self._read(address, 2)

    def read32(self, address: int) -> int:
        return self._read(address, 4)

    def read_range(self, address: int, length: int) -> bytes:
        # Battle mons
        base = Mem.BATTLE_MONS
        if base <= address < base + len(self._battle_mon_data):
            offset = address - base
            return bytes(self._battle_mon_data[offset:offset + length])
        
        # Save blocks
        if self._sb1_ptr <= address < self._sb1_ptr + len(self._save_block_1):
            offset = address - self._sb1_ptr
            return bytes(self._save_block_1[offset:offset + length])
        if self._sb2_ptr <= address < self._sb2_ptr + len(self._save_block_2):
            offset = address - self._sb2_ptr
            return bytes(self._save_block_2[offset:offset + length])
        
        return bytes(length)

    def _read(self, address: int, size: int) -> int:
        # Save block pointers
        if address == Mem.SAVE_BLOCK_1_PTR:
            return self._sb1_ptr
        if address == Mem.SAVE_BLOCK_2_PTR:
            return self._sb2_ptr
        
        # Battle type flags
        if address == Mem.BATTLE_TYPE_FLAGS:
            return self.scenario["battle_flags"]
        
        # Battle weather
        if address == Mem.BATTLE_WEATHER:
            return self.scenario["weather"]
        
        # Callbacks (non-zero = not in transition)
        if address == Mem.CALLBACK1:
            return 0x08001234
        if address == Mem.CALLBACK2:
            return 0x08005678
        
        # Text printers (not in dialogue)
        if address == Mem.TEXT_PRINTERS:
            return 0
        if address == Mem.TEXT_PRINTERS + 0x24:
            return 0
        
        # Battle mons
        base = Mem.BATTLE_MONS
        if base <= address < base + len(self._battle_mon_data):
            offset = address - base
            data = self._battle_mon_data[offset:offset + size]
            if size == 1:
                return data[0]
            elif size == 2:
                return int.from_bytes(data, 'little')
            elif size == 4:
                return int.from_bytes(data, 'little')
        
        # Save block reads
        if self._sb1_ptr <= address < self._sb1_ptr + len(self._save_block_1):
            offset = address - self._sb1_ptr
            data = self._save_block_1[offset:offset + size]
            return int.from_bytes(data, 'little') if size > 1 else data[0]
        
        return 0

    def tap_button(self, button: str) -> bool:
        logger.debug(f"MockClient: tap {button}")
        return True

    def hold_button(self, button: str, frames: int) -> bool:
        logger.debug(f"MockClient: hold {button} for {frames}f")
        return True

    def press_buttons(self, buttons: list[str], frames: int = 1) -> bool:
        return True

    def get_game_title(self) -> str:
        return "Pokemon - Emerald Version (U)"

    def get_game_code(self) -> str:
        return "BPEE"

    def get_frame_count(self) -> int:
        return 12345

    def save_screenshot(self, filepath: str) -> bool:
        return True

    def save_state(self, slot: int) -> bool:
        return True

    def load_state(self, slot: int) -> bool:
        return True

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

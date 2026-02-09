"""
Pokemon Generation 3 State Detector.

Detects the current game state by reading memory values using pointer chasing.
Used for reactive gameplay - knowing when we're in battle, menu, overworld, etc.
Shared across Ruby, Sapphire, Emerald, FireRed, and LeafGreen.

CRITICAL: Gen 3 uses DMA protection. All dynamic data must be read through
pointer chasing - read the pointer first, then add offsets.
"""

import logging
import time
from enum import Enum, auto
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...emulator.bizhawk_client import BizHawkClient

from .memory_map import PokemonGen3Memory as Mem
from .data_types import Pokemon, Move, PokemonParty, Ability, Nature, PokemonType
from ...data.move_data import enrich_move
from ...data.species_data import get_species_name
from .exceptions import (
    StateDetectorError,
    PointerInvalidError,
    MemoryReadError,
)

logger = logging.getLogger(__name__)


class PokemonGen3State(Enum):
    """
    Possible game states in Pokemon Gen 3 games.

    Expanded from Gen 1 to include double battles, contests, etc.
    """

    UNKNOWN = auto()
    TITLE_SCREEN = auto()
    OVERWORLD = auto()

    # Battle states
    BATTLE_WILD = auto()
    BATTLE_TRAINER = auto()
    BATTLE_DOUBLE_WILD = auto()
    BATTLE_DOUBLE_TRAINER = auto()
    BATTLE_SAFARI = auto()
    BATTLE_TOWER = auto()
    BATTLE_FRONTIER = auto()      # Emerald-specific
    BATTLE_LEGENDARY = auto()     # Special encounters

    # Battle sub-states
    BATTLE_MENU = auto()          # Selecting Fight/Bag/Pokemon/Run
    BATTLE_FIGHT_MENU = auto()    # Selecting which move
    BATTLE_BAG_MENU = auto()      # Selecting item
    BATTLE_POKEMON_MENU = auto()  # Selecting Pokemon to switch
    BATTLE_TARGET_MENU = auto()   # Selecting target in double battle

    # Menu states
    MENU_START = auto()           # Start menu open
    MENU_POKEMON = auto()         # Pokemon summary/party
    MENU_BAG = auto()             # Bag menu
    MENU_POKEDEX = auto()         # Pokedex
    MENU_SAVE = auto()            # Save menu
    MENU_OPTIONS = auto()         # Options menu
    MENU_POKENAV = auto()         # PokeNav (RSE)

    # Other states
    DIALOGUE = auto()             # Text box/NPC dialogue
    TRANSITION = auto()           # Screen transition/fade
    NAMING = auto()               # Naming screen
    POKEMON_CENTER = auto()       # Healing at Pokemon Center
    PC_STORAGE = auto()           # PC box system
    MART = auto()                 # Poke Mart shopping

    # Contest states (RSE)
    CONTEST = auto()
    CONTEST_APPEAL = auto()

    # Special locations
    SECRET_BASE = auto()          # RSE secret bases
    SAFARI_ZONE = auto()          # Safari Zone (not in battle)


class PokemonGen3StateDetector:
    """
    Detects the current game state in Pokemon Gen 3 games.

    Uses pointer chasing to read memory values and determine game mode,
    enabling reactive gameplay decisions.

    IMPORTANT: Call refresh_pointers() frequently to ensure pointer values
    are current, as DMA can move data at any time.
    """

    def __init__(self, client: "BizHawkClient", memory_class: type = Mem):
        """
        Initialize the state detector.

        Args:
            client: BizHawkClient for memory reads
            memory_class: Memory class to use (for game-specific addresses)
        """
        self.client = client
        self.mem = memory_class
        self._last_state = PokemonGen3State.UNKNOWN
        self._state_changed = False

        # Cached pointer values with TTL to reduce HTTP calls
        # DMA doesn't happen every frame - safe to cache for ~1 second
        self._save_block_1: int = 0
        self._save_block_2: int = 0
        self._pointers_valid: bool = False
        self._pointer_cache_time: float = 0.0
        self._pointer_cache_ttl: float = 1.0  # seconds

    def refresh_pointers(self, force: bool = False) -> bool:
        """
        Refresh the cached pointer values with TTL-based caching.

        Uses a 1-second TTL to reduce HTTP calls since DMA doesn't shift
        data every frame. Force refresh on state transitions where DMA
        is more likely to occur.

        Args:
            force: If True, bypass TTL and force a fresh read

        Returns:
            True if pointers are valid (either from cache or fresh read)
        """
        current_time = time.time()

        # Check if cache is still valid
        if not force and self._pointers_valid:
            if (current_time - self._pointer_cache_time) < self._pointer_cache_ttl:
                return True

        try:
            self._save_block_1 = self.client.read32(self.mem.SAVE_BLOCK_1_PTR)
            self._save_block_2 = self.client.read32(self.mem.SAVE_BLOCK_2_PTR)

            # Basic validation - pointers should be in EWRAM (0x02000000-0x0203FFFF)
            if not (0x02000000 <= self._save_block_1 <= 0x0203FFFF):
                logger.warning(f"Save Block 1 pointer out of range: 0x{self._save_block_1:08X}")
                self._pointers_valid = False
                return False

            if not (0x02000000 <= self._save_block_2 <= 0x0203FFFF):
                logger.warning(f"Save Block 2 pointer out of range: 0x{self._save_block_2:08X}")
                self._pointers_valid = False
                return False

            self._pointers_valid = True
            self._pointer_cache_time = current_time
            return True

        except MemoryReadError as e:
            logger.error(f"Memory read failed during pointer refresh: {e}")
            self._pointers_valid = False
            return False
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Connection error during pointer refresh: {e}")
            self._pointers_valid = False
            return False
        except Exception as e:
            # Catch-all for unexpected errors (e.g., mGBA-http issues)
            logger.error(f"Unexpected error refreshing pointers: {e}")
            self._pointers_valid = False
            return False

    def _read_from_save_block_1(self, offset: int, size: int = 1) -> int:
        """
        Read a value from Save Block 1 using pointer chasing.

        Args:
            offset: Offset within Save Block 1
            size: Number of bytes to read (1, 2, or 4)

        Returns:
            Value read from memory, or 0 if pointers are invalid
        """
        if not self._pointers_valid:
            self.refresh_pointers()

        # Return 0 if pointers are still invalid (e.g., at title screen)
        if not self._pointers_valid:
            return 0

        addr = self._save_block_1 + offset

        if size == 1:
            return self.client.read8(addr)
        elif size == 2:
            return self.client.read16(addr)
        elif size == 4:
            return self.client.read32(addr)
        else:
            raise ValueError(f"Invalid size: {size}")

    def _read_from_save_block_2(self, offset: int, size: int = 1) -> int:
        """Read a value from Save Block 2 using pointer chasing."""
        if not self._pointers_valid:
            self.refresh_pointers()

        addr = self._save_block_2 + offset

        if size == 1:
            return self.client.read8(addr)
        elif size == 2:
            return self.client.read16(addr)
        elif size == 4:
            return self.client.read32(addr)
        else:
            raise ValueError(f"Invalid size: {size}")

    def get_event_flag(self, flag_id: int) -> bool:
        """
        Read an event flag by ID.

        Event flags are stored as a bit array in Save Block 1.

        Args:
            flag_id: Flag ID (e.g., 0x895 for FLAG_SYS_CLOCK_SET)

        Returns:
            True if flag is set
        """
        try:
            if not self._pointers_valid:
                self.refresh_pointers()

            # Calculate byte and bit position
            byte_index = flag_id // 8
            bit_index = flag_id % 8

            # Read the byte containing this flag
            flags_base = self._save_block_1 + self.mem.EVENT_FLAGS_OFFSET
            flag_byte = self.client.read8(flags_base + byte_index)

            # Check the specific bit
            return bool(flag_byte & (1 << bit_index))

        except Exception as e:
            logger.warning(f"Failed to read event flag 0x{flag_id:03X}: {e}")
            return False

    def detect(self) -> PokemonGen3State:
        """
        Detect the current game state.

        Returns:
            Current PokemonGen3State
        """
        try:
            # Check for title screen first (before pointer validation)
            # Title screen has game state byte = 0xFF at 0x0300500C
            try:
                game_state_byte = self.client.read8(0x0300500C)
                if game_state_byte == 0xFF:
                    # Title screen detected
                    if self._last_state != PokemonGen3State.TITLE_SCREEN:
                        logger.info(f"State: {self._last_state.name} -> TITLE_SCREEN")
                        self._state_changed = True
                        self._last_state = PokemonGen3State.TITLE_SCREEN
                    else:
                        self._state_changed = False
                    return PokemonGen3State.TITLE_SCREEN
            except Exception:
                pass  # If read fails, continue with normal detection
            
            # Refresh pointers first
            if not self.refresh_pointers():
                return PokemonGen3State.UNKNOWN

            # Read battle type flags (direct address, not through pointer)
            battle_flags = self.client.read32(self.mem.BATTLE_TYPE_FLAGS)

            # Determine state based on memory values
            new_state = self._determine_state(battle_flags)

            # Track state changes
            if new_state != self._last_state:
                logger.info(f"State: {self._last_state.name} -> {new_state.name}")
                self._state_changed = True
                self._last_state = new_state
                # Force pointer refresh on state transitions (DMA more likely)
                self.refresh_pointers(force=True)
            else:
                self._state_changed = False

            return new_state

        except PointerInvalidError:
            # Expected at title screen - not an error
            return PokemonGen3State.UNKNOWN
        except MemoryReadError as e:
            logger.warning(f"Memory read failed during state detection: {e}")
            return PokemonGen3State.UNKNOWN
        except StateDetectorError as e:
            logger.error(f"State detection error: {e}")
            return PokemonGen3State.UNKNOWN
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Connection issue during state detection: {e}")
            return PokemonGen3State.UNKNOWN
        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"Unexpected state detection error: {e}")
            return PokemonGen3State.UNKNOWN

    def _determine_state(self, battle_flags: int) -> PokemonGen3State:
        """
        Determine game state from battle flags and other memory values.

        Priority order matters - check most specific states first.
        """
        # Check for battle first (battle flags are non-zero during battle)
        if battle_flags != 0:
            return self._determine_battle_state(battle_flags)

        # Check for active callback (can indicate menus, transitions, etc.)
        try:
            callback1 = self.client.read32(self.mem.CALLBACK1)
            callback2 = self.client.read32(self.mem.CALLBACK2)

            # If callbacks are null or specific values, we might be in transition
            if callback1 == 0 and callback2 == 0:
                return PokemonGen3State.TRANSITION

        except Exception:
            pass

        # Check for active dialogue/text box before defaulting to overworld
        # This enables state-based intro handling and responsive dialogue detection
        if self.is_dialogue_active():
            return PokemonGen3State.DIALOGUE

        # Default to overworld if no special state detected
        return PokemonGen3State.OVERWORLD

    def _determine_battle_state(self, battle_flags: int) -> PokemonGen3State:
        """
        Determine which type of battle based on flags.

        Args:
            battle_flags: Value from BATTLE_TYPE_FLAGS address
        """
        # Check for special battle types first
        if battle_flags & self.mem.BATTLE_TYPE_SAFARI:
            return PokemonGen3State.BATTLE_SAFARI

        if battle_flags & self.mem.BATTLE_TYPE_BATTLE_TOWER:
            # Check if this is Battle Frontier (Emerald) or just Tower
            if hasattr(self.mem, 'FRONTIER_STATUS'):
                return PokemonGen3State.BATTLE_FRONTIER
            return PokemonGen3State.BATTLE_TOWER

        if battle_flags & self.mem.BATTLE_TYPE_LEGENDARY:
            return PokemonGen3State.BATTLE_LEGENDARY

        # Check for double battle
        is_double = bool(battle_flags & self.mem.BATTLE_TYPE_DOUBLE)
        is_trainer = bool(battle_flags & self.mem.BATTLE_TYPE_TRAINER)
        is_wild = bool(battle_flags & self.mem.BATTLE_TYPE_WILD)

        if is_double:
            if is_trainer:
                return PokemonGen3State.BATTLE_DOUBLE_TRAINER
            return PokemonGen3State.BATTLE_DOUBLE_WILD

        if is_trainer:
            return PokemonGen3State.BATTLE_TRAINER

        if is_wild:
            return PokemonGen3State.BATTLE_WILD

        # Default to wild if unclear
        return PokemonGen3State.BATTLE_WILD

    # -------------------------------------------------------------------------
    # Property Accessors
    # -------------------------------------------------------------------------

    @property
    def current_state(self) -> PokemonGen3State:
        """Get the last detected state without re-reading memory."""
        return self._last_state

    @property
    def state_changed(self) -> bool:
        """Check if state changed on the last detect() call."""
        return self._state_changed

    @property
    def in_battle(self) -> bool:
        """Check if currently in any type of battle."""
        return self._last_state in (
            PokemonGen3State.BATTLE_WILD,
            PokemonGen3State.BATTLE_TRAINER,
            PokemonGen3State.BATTLE_DOUBLE_WILD,
            PokemonGen3State.BATTLE_DOUBLE_TRAINER,
            PokemonGen3State.BATTLE_SAFARI,
            PokemonGen3State.BATTLE_TOWER,
            PokemonGen3State.BATTLE_FRONTIER,
            PokemonGen3State.BATTLE_LEGENDARY,
            PokemonGen3State.BATTLE_MENU,
            PokemonGen3State.BATTLE_FIGHT_MENU,
            PokemonGen3State.BATTLE_BAG_MENU,
            PokemonGen3State.BATTLE_POKEMON_MENU,
            PokemonGen3State.BATTLE_TARGET_MENU,
        )

    @property
    def in_double_battle(self) -> bool:
        """Check if in a double battle."""
        return self._last_state in (
            PokemonGen3State.BATTLE_DOUBLE_WILD,
            PokemonGen3State.BATTLE_DOUBLE_TRAINER,
        )

    @property
    def in_overworld(self) -> bool:
        """Check if in normal overworld gameplay."""
        return self._last_state == PokemonGen3State.OVERWORLD

    @property
    def in_dialogue(self) -> bool:
        """Check if a text box is active."""
        return self._last_state == PokemonGen3State.DIALOGUE

    @property
    def in_menu(self) -> bool:
        """Check if in any menu."""
        return self._last_state in (
            PokemonGen3State.MENU_START,
            PokemonGen3State.MENU_POKEMON,
            PokemonGen3State.MENU_BAG,
            PokemonGen3State.MENU_POKEDEX,
            PokemonGen3State.MENU_SAVE,
            PokemonGen3State.MENU_OPTIONS,
            PokemonGen3State.MENU_POKENAV,
        )

    # -------------------------------------------------------------------------
    # Position and Map Reading (Pointer-based)
    # -------------------------------------------------------------------------

    def get_player_position(self) -> tuple[int, int]:
        """
        Get player X, Y coordinates using pointer chasing.

        Returns:
            (x, y) tuple of tile coordinates
        """
        x = self._read_from_save_block_1(self.mem.PLAYER_X_OFFSET, 2)
        y = self._read_from_save_block_1(self.mem.PLAYER_Y_OFFSET, 2)
        return (x, y)

    def get_map_location(self) -> tuple[int, int]:
        """
        Get current map group and number.

        Returns:
            (map_group, map_num) tuple
        """
        group = self._read_from_save_block_1(self.mem.MAP_GROUP_OFFSET, 1)
        num = self._read_from_save_block_1(self.mem.MAP_NUM_OFFSET, 1)
        return (group, num)

    # -------------------------------------------------------------------------
    # Party Reading (Pointer-based)
    # -------------------------------------------------------------------------

    def get_party_count(self) -> int:
        """Get number of Pokemon in party (0-6)."""
        return self._read_from_save_block_1(self.mem.PARTY_COUNT_OFFSET, 1)

    def get_play_time(self) -> tuple[int, int, int]:
        """Get play time (hours, minutes, seconds).

        Play time only starts after the clock is set in the intro.
        Returns (0, 0, 0) if clock not set or save data invalid.
        """
        try:
            # Play time is at offset 0xE in Save Block 2
            # Format: hours (2 bytes), minutes (1 byte), seconds (1 byte), frames (1 byte)
            hours = self._read_from_save_block_2(self.mem.SB2_PLAY_TIME_OFFSET, 2)
            minutes = self._read_from_save_block_2(self.mem.SB2_PLAY_TIME_OFFSET + 2, 1)
            seconds = self._read_from_save_block_2(self.mem.SB2_PLAY_TIME_OFFSET + 3, 1)
            return (hours, minutes, seconds)
        except Exception:
            return (0, 0, 0)

    def is_clock_set(self) -> bool:
        """Check if the in-game clock has been set.

        The clock is set during the intro sequence. Once set, play time
        starts incrementing. If play time is non-zero or incrementing,
        the clock has been set.
        """
        try:
            hours, minutes, seconds = self.get_play_time()
            # If any play time component is non-zero, clock was set
            # Note: At the very start, time might be 0:00:00 but will tick
            return hours > 0 or minutes > 0 or seconds > 0
        except Exception:
            return False

    def read_party(self) -> PokemonParty:
        """
        Read the player's party from memory.

        Returns:
            PokemonParty with all party Pokemon
        """
        count = self.get_party_count()
        pokemon_list = []

        for i in range(min(count, 6)):
            pokemon = self._read_party_pokemon(i)
            if pokemon:
                pokemon_list.append(pokemon)

        return PokemonParty(pokemon=pokemon_list)

    def _read_party_pokemon(self, index: int) -> Optional[Pokemon]:
        """
        Read a single Pokemon from the party using batched memory read.

        Uses a single read_range() call for the entire 100-byte Pokemon struct
        instead of 12+ individual reads, reducing HTTP calls by ~90%.

        Args:
            index: Party slot (0-5)

        Returns:
            Pokemon or None if slot is empty
        """
        if not self._pointers_valid:
            self.refresh_pointers()

        if not self._pointers_valid:
            return None

        base_offset = self.mem.PARTY_DATA_OFFSET + (index * self.mem.PARTY_POKEMON_SIZE)
        base_addr = self._save_block_1 + base_offset

        try:
            # Single HTTP call for entire Pokemon struct (100 bytes)
            data = self.client.read_range(base_addr, self.mem.PARTY_POKEMON_SIZE)

            # Parse personality and OT ID (first 8 bytes)
            personality = int.from_bytes(data[0x00:0x04], 'little')
            ot_id = int.from_bytes(data[0x04:0x08], 'little')

            # Parse level and HP from calculated stats section
            level = data[0x54]
            current_hp = int.from_bytes(data[0x56:0x58], 'little')
            max_hp = int.from_bytes(data[0x58:0x5A], 'little')

            if level == 0 or max_hp == 0:
                return None  # Empty slot

            # Parse stats
            attack = int.from_bytes(data[0x5A:0x5C], 'little')
            defense = int.from_bytes(data[0x5C:0x5E], 'little')
            speed = int.from_bytes(data[0x5E:0x60], 'little')
            sp_attack = int.from_bytes(data[0x60:0x62], 'little')
            sp_defense = int.from_bytes(data[0x62:0x64], 'little')

            # Parse status
            status = int.from_bytes(data[0x50:0x54], 'little')

            # Calculate nature from personality
            nature = Nature(personality % 25)

            # Check if shiny
            p_high = (personality >> 16) & 0xFFFF
            p_low = personality & 0xFFFF
            tid = ot_id & 0xFFFF
            sid = (ot_id >> 16) & 0xFFFF
            is_shiny = ((tid ^ sid) ^ (p_high ^ p_low)) < 8

            pokemon = Pokemon(
                species_id=0,  # Would need to read from encrypted data
                level=level,
                hp=current_hp,
                max_hp=max_hp,
                status=status,
                attack=attack,
                defense=defense,
                speed=speed,
                sp_attack=sp_attack,
                sp_defense=sp_defense,
                nature=nature,
                personality=personality,
                ot_id=ot_id,
                is_shiny=is_shiny,
            )

            return pokemon

        except MemoryReadError as e:
            logger.warning(f"Memory read failed for party Pokemon {index}: {e}")
            return None
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Connection issue reading party Pokemon {index}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading party Pokemon {index}: {e}")
            return None

    # -------------------------------------------------------------------------
    # Battle State Reading (Direct addresses during battle)
    # -------------------------------------------------------------------------

    def get_battle_weather(self) -> int:
        """Get current battle weather."""
        try:
            return self.client.read16(self.mem.BATTLE_WEATHER)
        except Exception:
            return 0

    def read_battle_pokemon(self, battler_index: int) -> Optional[Pokemon]:
        """
        Read a Pokemon's battle data using batched memory read.

        Uses a single read_range() call for the entire 88-byte battle mon struct
        instead of 15+ individual reads, reducing HTTP calls by ~90%.

        Args:
            battler_index: 0=player1, 1=enemy1, 2=player2 (double), 3=enemy2 (double)

        Returns:
            Pokemon with battle stats, or None if not in battle
        """
        if not self.in_battle:
            return None

        try:
            base_addr = self.mem.BATTLE_MONS + (battler_index * self.mem.BATTLE_MON_SIZE)

            # Single HTTP call for entire battle mon struct (88 bytes)
            data = self.client.read_range(base_addr, self.mem.BATTLE_MON_SIZE)

            # Parse species (offset 0x00, 2 bytes)
            species = int.from_bytes(data[0x00:0x02], 'little')
            if species == 0:
                return None

            # Parse stats (offsets 0x02-0x0B, 2 bytes each)
            attack = int.from_bytes(data[0x02:0x04], 'little')
            defense = int.from_bytes(data[0x04:0x06], 'little')
            speed = int.from_bytes(data[0x06:0x08], 'little')
            sp_attack = int.from_bytes(data[0x08:0x0A], 'little')
            sp_defense = int.from_bytes(data[0x0A:0x0C], 'little')

            # Parse HP and level
            hp = int.from_bytes(data[0x28:0x2A], 'little')
            level = data[0x2A]
            max_hp = int.from_bytes(data[0x2C:0x2E], 'little')

            # Parse status (offset 0x4C, 4 bytes)
            status = int.from_bytes(data[0x4C:0x50], 'little')

            # Parse ability and types
            ability_id = data[0x20]
            type1 = data[0x21]
            type2 = data[0x22]

            # Parse moves and enrich with database data
            moves = []
            for i in range(4):
                move_offset = 0x0C + (i * 2)
                move_id = int.from_bytes(data[move_offset:move_offset + 2], 'little')
                pp = data[0x24 + i]  # PP offset is 0x24
                if move_id != 0:
                    move = Move(id=move_id, pp=pp)
                    enrich_move(move)
                    moves.append(move)

            pokemon = Pokemon(
                species_id=species,
                species_name=get_species_name(species),
                level=level,
                hp=hp,
                max_hp=max_hp,
                status=status,
                attack=attack,
                defense=defense,
                speed=speed,
                sp_attack=sp_attack,
                sp_defense=sp_defense,
                ability=Ability(ability_id) if ability_id <= 77 else Ability.NONE,
                type1=PokemonType(type1) if type1 <= 17 else None,
                type2=PokemonType(type2) if type2 <= 17 and type2 != type1 else None,
                moves=moves,
            )

            return pokemon

        except MemoryReadError as e:
            logger.warning(f"Memory read failed for battle Pokemon {battler_index}: {e}")
            return None
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Connection issue reading battle Pokemon {battler_index}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading battle Pokemon {battler_index}: {e}")
            return None

    # -------------------------------------------------------------------------
    # Options/Settings Reading (Pointer-based)
    # -------------------------------------------------------------------------

    def read_options(self) -> dict[str, int]:
        """
        Read game options from Save Block 2.
        
        Options are stored as a bitfield at offset 0x13:
        - Bits 0-2: Text Speed (0=Slow, 1=Mid, 2=Fast)
        - Bit 3: Battle Scene (0=On, 1=Off)
        - Bit 4: Battle Style (0=Switch, 1=Set)
        - Bit 5: Sound (0=Mono, 1=Stereo)
        
        Returns:
            Dictionary with option names and values
        """
        try:
            options_byte = self._read_from_save_block_2(self.mem.OPTIONS_OFFSET, 1)
            
            return {
                'text_speed': options_byte & 0x07,           # Bits 0-2
                'battle_scene': (options_byte >> 3) & 0x01,  # Bit 3
                'battle_style': (options_byte >> 4) & 0x01,  # Bit 4
                'sound': (options_byte >> 5) & 0x01,         # Bit 5
                'raw': options_byte,                         # Full byte for debugging
            }
        except Exception as e:
            logger.warning(f"Failed to read options: {e}")
            return {
                'text_speed': 0,
                'battle_scene': 0,
                'battle_style': 0,
                'sound': 0,
                'raw': 0,
            }

    def verify_optimal_settings(self) -> bool:
        """
        Check if game settings are configured optimally for AI play.
        
        Optimal settings:
        - Text Speed: Fast (2)
        - Battle Scene: Off (1)
        - Battle Style: Set (1)
        
        Returns:
            True if all settings are optimal
        """
        options = self.read_options()
        
        is_optimal = (
            options['text_speed'] == 2 and      # Fast
            options['battle_scene'] == 1 and    # Off
            options['battle_style'] == 1        # Set
        )
        
        if not is_optimal:
            logger.info(f"Settings check: "
                       f"Text={options['text_speed']} (want 2), "
                       f"Scene={options['battle_scene']} (want 1), "
                       f"Style={options['battle_style']} (want 1)")
        
        return is_optimal

    # -------------------------------------------------------------------------
    # Convenience Methods
    # -------------------------------------------------------------------------

    def is_wild_battle(self) -> bool:
        """Check if in a wild Pokemon battle."""
        return self._last_state in (
            PokemonGen3State.BATTLE_WILD,
            PokemonGen3State.BATTLE_DOUBLE_WILD,
        )

    def is_trainer_battle(self) -> bool:
        """Check if in a trainer battle."""
        return self._last_state in (
            PokemonGen3State.BATTLE_TRAINER,
            PokemonGen3State.BATTLE_DOUBLE_TRAINER,
            PokemonGen3State.BATTLE_TOWER,
            PokemonGen3State.BATTLE_FRONTIER,
        )

    def is_dialogue_active(self) -> bool:
        """
        Check if text/dialogue is currently being displayed.

        Checks the sTextPrinters array to see if any text printer is active.
        Text printer states are typically:
        - 0 = RENDER_STATE_IDLE (inactive)
        - 1 = RENDER_STATE_HANDLE_CHAR (active)
        - 2 = RENDER_STATE_WAIT (waiting for input)
        - 3+ = various pause/wait states

        High values (100+) are likely garbage data or unrelated, not dialogue.

        Returns:
            True if text is currently being rendered on screen
        """
        try:
            # Check first text printer's active flag (offset 0x1C in struct)
            # Actually, the first byte is 'active' boolean
            printer_active = self.client.read8(self.mem.TEXT_PRINTERS)

            # Conservative check: Only treat small values (1-10) as active dialogue
            # Higher values are likely uninitialized memory, not dialogue states
            if printer_active >= 1 and printer_active <= 10:
                return True

            # Check a second printer (some dialogues use multiple)
            printer2_active = self.client.read8(self.mem.TEXT_PRINTERS + 0x24)
            if printer2_active >= 1 and printer2_active <= 10:
                return True

            return False

        except (MemoryReadError, ConnectionError, TimeoutError):
            # Connection issues - assume no dialogue to avoid blocking
            return False
        except Exception as e:
            logger.debug(f"Dialogue check failed: {e}")
            return False


# =============================================================================
# Game-specific aliases
# =============================================================================

PokemonEmeraldState = PokemonGen3State
PokemonEmeraldStateDetector = PokemonGen3StateDetector

PokemonRubyState = PokemonGen3State
PokemonRubyStateDetector = PokemonGen3StateDetector

PokemonSapphireState = PokemonGen3State
PokemonSapphireStateDetector = PokemonGen3StateDetector

PokemonFireRedState = PokemonGen3State
PokemonFireRedStateDetector = PokemonGen3StateDetector

PokemonLeafGreenState = PokemonGen3State
PokemonLeafGreenStateDetector = PokemonGen3StateDetector

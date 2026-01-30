"""
Pokemon Generation 3 Memory Map.

Memory addresses for Pokemon Ruby/Sapphire/Emerald/FireRed/LeafGreen.
Addresses are for US versions. Japanese versions may differ.

CRITICAL: Gen 3 uses DMA protection - data locations shift during gameplay.
You MUST use pointer chasing to read dynamic data:
    1. Read the static pointer address to get the current data location
    2. Add the offset to find the specific field
    3. Read from the calculated address

VERIFIED ADDRESSES (from pret symbol files):
- Emerald: https://github.com/pret/pokeemerald/tree/symbols (pokeemerald.sym)
- Ruby: https://github.com/pret/pokeruby/tree/symbols (pokeruby.sym)
- FireRed: https://github.com/pret/pokefirered/tree/symbols (pokefirered.sym)

Primary sources:
- https://github.com/pret/pokeemerald (Emerald disassembly)
- https://github.com/pret/pokeruby (Ruby disassembly)
- https://github.com/pret/pokefirered (FireRed disassembly)
- https://bulbapedia.bulbagarden.net/wiki/Save_data_structure_(Generation_III)

Address notation:
- Static pointers: 0x03XXXXXX (IWRAM) or 0x02XXXXXX (EWRAM)
- Offsets: Added to dereferenced pointer value
- Format: 0xXXXXXXXX (32-bit address)

Platform: Game Boy Advance (ARM7TDMI, 32-bit)

Verification Status:
- Emerald (BPEE): VERIFIED from pokeemerald.sym
- Ruby (AXVE): VERIFIED from pokeruby.sym
- Sapphire (AXPE): Same as Ruby
- FireRed (BPRE): VERIFIED from pokefirered.sym
- LeafGreen (BPGE): Same as FireRed
"""

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class PokemonGen3Memory:
    """
    Memory addresses for Pokemon Gen 3 (GBA).

    IMPORTANT: Most addresses here are either:
    - Static pointers that must be dereferenced
    - Offsets to add to dereferenced pointer values

    Use get_save_block_1() and get_save_block_2() helper methods
    to properly read dynamic data.
    """

    # =========================================================================
    # STATIC ADDRESSES (Always Valid - Read These Directly)
    # =========================================================================

    # Game code in ROM header (4 bytes ASCII)
    # "BPEE" = Emerald, "AXVE" = Ruby, "AXPE" = Sapphire
    # "BPRE" = FireRed, "BPGE" = LeafGreen
    GAME_CODE: ClassVar[int] = 0x080000AC

    # =========================================================================
    # SAVE BLOCK POINTERS (Static - Dereference to Get Dynamic Addresses)
    # =========================================================================

    # Save Block 1: Player data, position, party, items, etc.
    # Read this pointer, then add offsets below to access data
    SAVE_BLOCK_1_PTR: ClassVar[int] = 0x03005D8C

    # Save Block 2: Pokedex, options, game stats, etc.
    SAVE_BLOCK_2_PTR: ClassVar[int] = 0x03005D90

    # Pokemon Storage pointer (PC boxes)
    POKEMON_STORAGE_PTR: ClassVar[int] = 0x03005D94

    # =========================================================================
    # SAVE BLOCK 1 OFFSETS (Add to dereferenced SAVE_BLOCK_1_PTR)
    # =========================================================================

    # Player position (from Save Block 1)
    PLAYER_X_OFFSET: ClassVar[int] = 0x0      # 2 bytes (u16)
    PLAYER_Y_OFFSET: ClassVar[int] = 0x2      # 2 bytes (u16)
    MAP_GROUP_OFFSET: ClassVar[int] = 0x4     # 1 byte (u8)
    MAP_NUM_OFFSET: ClassVar[int] = 0x5       # 1 byte (u8)

    # Player name (from Save Block 1) - 8 bytes including terminator
    PLAYER_NAME_OFFSET: ClassVar[int] = 0x0   # In SaveBlock2 actually

    # Party Pokemon (from Save Block 1)
    PARTY_COUNT_OFFSET: ClassVar[int] = 0x234         # 1 byte (u8), 0-6
    PARTY_DATA_OFFSET: ClassVar[int] = 0x238          # 6 Pokemon × 100 bytes
    PARTY_POKEMON_SIZE: ClassVar[int] = 100           # Bytes per Pokemon

    # Money (from Save Block 1) - encrypted with security key
    MONEY_OFFSET: ClassVar[int] = 0x0490              # 4 bytes (u32)
    SECURITY_KEY_OFFSET: ClassVar[int] = 0x0AF8       # XOR key for money/coins

    # Coins (Game Corner) - encrypted with security key
    COINS_OFFSET: ClassVar[int] = 0x0494              # 2 bytes (u16)

    # Bag items (from Save Block 1)
    BAG_ITEMS_OFFSET: ClassVar[int] = 0x0560          # Regular items pocket
    BAG_KEY_ITEMS_OFFSET: ClassVar[int] = 0x05D8      # Key items pocket
    BAG_POKEBALLS_OFFSET: ClassVar[int] = 0x0650      # Pokeballs pocket
    BAG_TM_HM_OFFSET: ClassVar[int] = 0x0690          # TMs/HMs pocket
    BAG_BERRIES_OFFSET: ClassVar[int] = 0x0790        # Berries pocket

    # =========================================================================
    # SAVE BLOCK 2 OFFSETS (Add to dereferenced SAVE_BLOCK_2_PTR)
    # =========================================================================

    # Player name is in Save Block 2
    SB2_PLAYER_NAME_OFFSET: ClassVar[int] = 0x0       # 8 bytes
    SB2_PLAYER_GENDER_OFFSET: ClassVar[int] = 0x8     # 1 byte (0=male, 1=female)
    SB2_PLAYER_ID_OFFSET: ClassVar[int] = 0xA         # 4 bytes (trainer ID)
    SB2_PLAY_TIME_OFFSET: ClassVar[int] = 0xE         # 5 bytes (hours, mins, secs, frames)

    # Pokedex flags (from Save Block 2)
    POKEDEX_OWNED_OFFSET: ClassVar[int] = 0x28        # 52 bytes (416 bits for national dex)
    POKEDEX_SEEN_OFFSET: ClassVar[int] = 0x5C         # 52 bytes

    # Options (from Save Block 2)
    OPTIONS_OFFSET: ClassVar[int] = 0x13              # Game options byte

    # Badges - stored as event flags (from Save Block 1)
    # Event flags are at offset 0x1270 in Save Block 1 (Emerald)
    EVENT_FLAGS_OFFSET: ClassVar[int] = 0x1270

    # Badge flag indices (bit positions in event flags)
    # Emerald badge flags (FLAG_BADGE01_GET = 0x807, etc.)
    BADGE_FLAG_BASE: ClassVar[int] = 0x807  # First badge flag
    BADGE_1_STONE: ClassVar[int] = 0x807    # Roxanne (Rustboro)
    BADGE_2_KNUCKLE: ClassVar[int] = 0x808  # Brawly (Dewford)
    BADGE_3_DYNAMO: ClassVar[int] = 0x809   # Wattson (Mauville)
    BADGE_4_HEAT: ClassVar[int] = 0x80A     # Flannery (Lavaridge)
    BADGE_5_BALANCE: ClassVar[int] = 0x80B  # Norman (Petalburg)
    BADGE_6_FEATHER: ClassVar[int] = 0x80C  # Winona (Fortree)
    BADGE_7_MIND: ClassVar[int] = 0x80D     # Tate & Liza (Mossdeep)
    BADGE_8_RAIN: ClassVar[int] = 0x80E     # Wallace (Sootopolis)

    # Special story flags
    FLAG_SYS_POKEMON_GET: ClassVar[int] = 0x860        # Has received first Pokemon
    FLAG_SYS_POKEDEX_GET: ClassVar[int] = 0x861        # Has received Pokedex
    FLAG_SYS_POKENAV_GET: ClassVar[int] = 0x862        # Has received PokeNav
    FLAG_DEFEATED_ELITE_FOUR: ClassVar[int] = 0x864    # Beat Elite Four
    FLAG_SYS_GAME_CLEAR: ClassVar[int] = 0x864         # Entered Hall of Fame (same as defeated E4)
    FLAG_SYS_CLOCK_SET: ClassVar[int] = 0x895          # Clock has been set by player
    FLAG_CAUGHT_LATIAS: ClassVar[int] = 0x8B4          # Caught roaming Latias
    FLAG_CAUGHT_LATIOS: ClassVar[int] = 0x8B5          # Caught roaming Latios

    # Legendary encounter flags
    FLAG_HIDE_RAYQUAZA: ClassVar[int] = 0x3AC          # Rayquaza caught/fled
    FLAG_HIDE_GROUDON: ClassVar[int] = 0x3AB           # Groudon caught/fled
    FLAG_HIDE_KYOGRE: ClassVar[int] = 0x3AA            # Kyogre caught/fled
    FLAG_CAUGHT_REGIROCK: ClassVar[int] = 0x8C0
    FLAG_CAUGHT_REGICE: ClassVar[int] = 0x8C1
    FLAG_CAUGHT_REGISTEEL: ClassVar[int] = 0x8C2

    # =========================================================================
    # BATTLE RAM (Valid During Battle Only - Direct Addresses)
    # =========================================================================

    # These addresses are in EWRAM and relatively stable during battle
    # Note: Some may shift slightly - verify with pokeemerald sym_ewram.txt

    # Battle type flags (Emerald-specific, other games override)
    BATTLE_TYPE_FLAGS: ClassVar[int] = 0x02022FEC     # u32 bitfield

    # Current battle outcome (0 = ongoing)
    BATTLE_OUTCOME: ClassVar[int] = 0x02022B50

    # Active battler index (0-3 for double battles)
    ACTIVE_BATTLER: ClassVar[int] = 0x02024064

    # Battle struct base for all battlers (4 battlers × ~88 bytes each)
    BATTLE_MONS: ClassVar[int] = 0x02024084
    BATTLE_MON_SIZE: ClassVar[int] = 88               # Bytes per battle mon

    # Offsets within each battle mon struct
    BATTLE_MON_SPECIES_OFFSET: ClassVar[int] = 0x0    # 2 bytes
    BATTLE_MON_ATTACK_OFFSET: ClassVar[int] = 0x2     # 2 bytes
    BATTLE_MON_DEFENSE_OFFSET: ClassVar[int] = 0x4    # 2 bytes
    BATTLE_MON_SPEED_OFFSET: ClassVar[int] = 0x6      # 2 bytes
    BATTLE_MON_SP_ATK_OFFSET: ClassVar[int] = 0x8     # 2 bytes
    BATTLE_MON_SP_DEF_OFFSET: ClassVar[int] = 0xA     # 2 bytes
    BATTLE_MON_MOVES_OFFSET: ClassVar[int] = 0xC      # 4 × 2 bytes
    BATTLE_MON_IV_OFFSET: ClassVar[int] = 0x14        # 4 bytes (packed)
    BATTLE_MON_HP_OFFSET: ClassVar[int] = 0x28        # 2 bytes
    BATTLE_MON_MAX_HP_OFFSET: ClassVar[int] = 0x2C    # 2 bytes (aligned)
    BATTLE_MON_LEVEL_OFFSET: ClassVar[int] = 0x2A     # 1 byte
    BATTLE_MON_PP_OFFSET: ClassVar[int] = 0x24        # 4 × 1 byte
    BATTLE_MON_STATUS_OFFSET: ClassVar[int] = 0x4C    # 4 bytes
    BATTLE_MON_ABILITY_OFFSET: ClassVar[int] = 0x20   # 1 byte
    BATTLE_MON_TYPE1_OFFSET: ClassVar[int] = 0x21     # 1 byte
    BATTLE_MON_TYPE2_OFFSET: ClassVar[int] = 0x22     # 1 byte

    # Stat stage modifiers (-6 to +6, stored as 0-12 with 6 = neutral)
    STAT_STAGES: ClassVar[int] = 0x02024470           # 8 bytes per battler

    # Current move being used
    CURRENT_MOVE: ClassVar[int] = 0x020241EA          # 2 bytes

    # Move selection cursor
    MOVE_SELECTION_CURSOR: ClassVar[int] = 0x02024064

    # Battle menu cursor
    BATTLE_MENU_CURSOR: ClassVar[int] = 0x02024065

    # Weather in battle (0=none, 1=rain, 2=sandstorm, 3=sunny, etc.)
    BATTLE_WEATHER: ClassVar[int] = 0x02024DB8

    # =========================================================================
    # OVERWORLD STATE (Direct Addresses)
    # =========================================================================

    # Callback pointers - can indicate game state
    CALLBACK1: ClassVar[int] = 0x030022C0
    CALLBACK2: ClassVar[int] = 0x030022C4

    # Text/window state - from pokeemerald.sym symbols
    # gDisableTextPrinters controls if text printing is disabled
    DISABLE_TEXT_PRINTERS: ClassVar[int] = 0x03002F83
    # sTextPrinters array base (8 printers x 0x24 bytes each)
    TEXT_PRINTERS: ClassVar[int] = 0x020201B0
    # gWindows array
    WINDOWS: ClassVar[int] = 0x02020004
    # Legacy address (incorrect - kept for reference)
    TEXT_PRINTER_ACTIVE: ClassVar[int] = 0x020201B0  # First text printer struct

    # Player avatar state
    PLAYER_AVATAR: ClassVar[int] = 0x02037078

    # =========================================================================
    # POKEMON DATA STRUCTURE OFFSETS (Within 100-byte Pokemon struct)
    # =========================================================================

    # Pokemon data is encrypted in save, decrypted when loaded to party
    # Party/battle structs are decrypted

    PKM_PERSONALITY_OFFSET: ClassVar[int] = 0x0       # 4 bytes - determines nature, gender, ability
    PKM_OT_ID_OFFSET: ClassVar[int] = 0x4             # 4 bytes - original trainer ID
    PKM_NICKNAME_OFFSET: ClassVar[int] = 0x8          # 10 bytes
    PKM_LANGUAGE_OFFSET: ClassVar[int] = 0x12         # 1 byte
    PKM_OT_NAME_OFFSET: ClassVar[int] = 0x14          # 7 bytes
    PKM_MARKINGS_OFFSET: ClassVar[int] = 0x1B         # 1 byte
    PKM_CHECKSUM_OFFSET: ClassVar[int] = 0x1C         # 2 bytes
    PKM_DATA_OFFSET: ClassVar[int] = 0x20             # 48 bytes (encrypted substructs)

    # Decrypted/party Pokemon additional fields (after 0x50)
    PKM_STATUS_OFFSET: ClassVar[int] = 0x50           # 4 bytes
    PKM_LEVEL_OFFSET: ClassVar[int] = 0x54            # 1 byte
    PKM_POKERUS_OFFSET: ClassVar[int] = 0x55          # 1 byte
    PKM_CURRENT_HP_OFFSET: ClassVar[int] = 0x56       # 2 bytes
    PKM_MAX_HP_OFFSET: ClassVar[int] = 0x58           # 2 bytes
    PKM_ATTACK_OFFSET: ClassVar[int] = 0x5A           # 2 bytes
    PKM_DEFENSE_OFFSET: ClassVar[int] = 0x5C          # 2 bytes
    PKM_SPEED_OFFSET: ClassVar[int] = 0x5E            # 2 bytes
    PKM_SP_ATTACK_OFFSET: ClassVar[int] = 0x60        # 2 bytes
    PKM_SP_DEFENSE_OFFSET: ClassVar[int] = 0x62       # 2 bytes

    # =========================================================================
    # STATUS CONDITION CONSTANTS
    # =========================================================================

    STATUS_NONE: ClassVar[int] = 0
    STATUS_SLEEP_MASK: ClassVar[int] = 0x07           # Bits 0-2 = sleep turns
    STATUS_POISON: ClassVar[int] = 0x08               # Bit 3
    STATUS_BURN: ClassVar[int] = 0x10                 # Bit 4
    STATUS_FREEZE: ClassVar[int] = 0x20               # Bit 5
    STATUS_PARALYSIS: ClassVar[int] = 0x40            # Bit 6
    STATUS_TOXIC: ClassVar[int] = 0x80                # Bit 7 (bad poison)

    # =========================================================================
    # TYPE CONSTANTS (Gen 3 type IDs)
    # =========================================================================

    TYPE_NORMAL: ClassVar[int] = 0
    TYPE_FIGHTING: ClassVar[int] = 1
    TYPE_FLYING: ClassVar[int] = 2
    TYPE_POISON: ClassVar[int] = 3
    TYPE_GROUND: ClassVar[int] = 4
    TYPE_ROCK: ClassVar[int] = 5
    TYPE_BUG: ClassVar[int] = 6
    TYPE_GHOST: ClassVar[int] = 7
    TYPE_STEEL: ClassVar[int] = 8
    TYPE_MYSTERY: ClassVar[int] = 9                   # ??? type (Curse pre-fairy)
    TYPE_FIRE: ClassVar[int] = 10
    TYPE_WATER: ClassVar[int] = 11
    TYPE_GRASS: ClassVar[int] = 12
    TYPE_ELECTRIC: ClassVar[int] = 13
    TYPE_PSYCHIC: ClassVar[int] = 14
    TYPE_ICE: ClassVar[int] = 15
    TYPE_DRAGON: ClassVar[int] = 16
    TYPE_DARK: ClassVar[int] = 17

    # =========================================================================
    # BATTLE TYPE FLAGS (Bitfield values for BATTLE_TYPE_FLAGS)
    # =========================================================================

    BATTLE_TYPE_DOUBLE: ClassVar[int] = 0x0001
    BATTLE_TYPE_LINK: ClassVar[int] = 0x0002
    BATTLE_TYPE_WILD: ClassVar[int] = 0x0004
    BATTLE_TYPE_TRAINER: ClassVar[int] = 0x0008
    BATTLE_TYPE_FIRST_BATTLE: ClassVar[int] = 0x0010
    BATTLE_TYPE_SAFARI: ClassVar[int] = 0x0080
    BATTLE_TYPE_BATTLE_TOWER: ClassVar[int] = 0x0200
    BATTLE_TYPE_ROAMER: ClassVar[int] = 0x1000
    BATTLE_TYPE_LEGENDARY: ClassVar[int] = 0x2000

    # =========================================================================
    # WEATHER CONSTANTS
    # =========================================================================

    WEATHER_NONE: ClassVar[int] = 0
    WEATHER_SUNNY_CLOUDS: ClassVar[int] = 1
    WEATHER_SUNNY: ClassVar[int] = 2
    WEATHER_RAIN: ClassVar[int] = 3
    WEATHER_SNOW: ClassVar[int] = 4
    WEATHER_THUNDERSTORM: ClassVar[int] = 5
    WEATHER_FOG_HORIZONTAL: ClassVar[int] = 6
    WEATHER_VOLCANIC_ASH: ClassVar[int] = 7
    WEATHER_SANDSTORM: ClassVar[int] = 8
    WEATHER_FOG_DIAGONAL: ClassVar[int] = 9
    WEATHER_UNDERWATER: ClassVar[int] = 10
    WEATHER_SHADE: ClassVar[int] = 11
    WEATHER_DROUGHT: ClassVar[int] = 12
    WEATHER_DOWNPOUR: ClassVar[int] = 13

    # =========================================================================
    # MAP CONSTANTS (Hoenn - Emerald)
    # =========================================================================

    # Map group 0: Towns/Cities
    MAP_PETALBURG_CITY: ClassVar[tuple] = (0, 0)
    MAP_SLATEPORT_CITY: ClassVar[tuple] = (0, 1)
    MAP_MAUVILLE_CITY: ClassVar[tuple] = (0, 2)
    MAP_RUSTBORO_CITY: ClassVar[tuple] = (0, 3)
    MAP_FORTREE_CITY: ClassVar[tuple] = (0, 4)
    MAP_LILYCOVE_CITY: ClassVar[tuple] = (0, 5)
    MAP_MOSSDEEP_CITY: ClassVar[tuple] = (0, 6)
    MAP_SOOTOPOLIS_CITY: ClassVar[tuple] = (0, 7)
    MAP_EVER_GRANDE_CITY: ClassVar[tuple] = (0, 8)
    MAP_LITTLEROOT_TOWN: ClassVar[tuple] = (1, 0)
    MAP_OLDALE_TOWN: ClassVar[tuple] = (1, 1)
    MAP_DEWFORD_TOWN: ClassVar[tuple] = (1, 2)
    MAP_LAVARIDGE_TOWN: ClassVar[tuple] = (1, 3)
    MAP_FALLARBOR_TOWN: ClassVar[tuple] = (1, 4)
    MAP_VERDANTURF_TOWN: ClassVar[tuple] = (1, 5)
    MAP_PACIFIDLOG_TOWN: ClassVar[tuple] = (1, 6)

    # Routes
    MAP_ROUTE_101: ClassVar[tuple] = (25, 16)
    MAP_ROUTE_102: ClassVar[tuple] = (25, 17)
    MAP_ROUTE_103: ClassVar[tuple] = (25, 18)

    # Interior maps (map group 25 = Special/Indoor)
    MAP_INSIDE_TRUCK: ClassVar[tuple] = (25, 40)       # Moving truck interior
    MAP_PLAYER_HOUSE_1F: ClassVar[tuple] = (25, 5)     # Player's house 1st floor
    MAP_PLAYER_HOUSE_2F: ClassVar[tuple] = (25, 6)     # Player's house 2nd floor


# =============================================================================
# GAME-SPECIFIC MEMORY CLASSES
# =============================================================================

class PokemonEmeraldMemory(PokemonGen3Memory):
    """
    Emerald-specific memory addresses (US version).

    Game Code: BPEE
    Uses the base Gen 3 addresses defined above.
    """

    # Emerald uses the same pointer addresses as base class
    # Battle Frontier specific addresses could be added here

    # Battle Frontier data
    FRONTIER_STATUS: ClassVar[int] = 0x03005D98       # Frontier save block ptr


class PokemonRubyMemory(PokemonGen3Memory):
    """
    Ruby-specific memory addresses (US version).

    Game Code: AXVE
    Some pointers differ from Emerald.
    """

    # Ruby has different pointer locations
    SAVE_BLOCK_1_PTR: ClassVar[int] = 0x03005D90      # Different from Emerald
    SAVE_BLOCK_2_PTR: ClassVar[int] = 0x03005D94
    POKEMON_STORAGE_PTR: ClassVar[int] = 0x03005D98

    # Ruby-specific battle RAM addresses
    BATTLE_TYPE_FLAGS: ClassVar[int] = 0x020239FC     # Different from Emerald
    BATTLE_MONS: ClassVar[int] = 0x02024BE0           # Different from Emerald


class PokemonSapphireMemory(PokemonRubyMemory):
    """
    Sapphire-specific memory addresses (US version).

    Game Code: AXPE
    Shares memory layout with Ruby.
    """
    pass  # Same as Ruby


class PokemonFireRedMemory(PokemonGen3Memory):
    """
    FireRed-specific memory addresses (US version).

    Game Code: BPRE
    FRLG have a different memory layout from RSE.
    """

    # FireRed/LeafGreen have different pointer addresses
    SAVE_BLOCK_1_PTR: ClassVar[int] = 0x03005008
    SAVE_BLOCK_2_PTR: ClassVar[int] = 0x0300500C
    POKEMON_STORAGE_PTR: ClassVar[int] = 0x03005010

    # FRLG-specific battle RAM locations (verified from pokefirered.sym)
    BATTLE_TYPE_FLAGS: ClassVar[int] = 0x02022B4C
    BATTLE_MONS: ClassVar[int] = 0x02023BE4


class PokemonLeafGreenMemory(PokemonFireRedMemory):
    """
    LeafGreen-specific memory addresses (US version).

    Game Code: BPGE
    Shares memory layout with FireRed.
    """
    pass  # Same as FireRed


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_nature_from_personality(personality: int) -> int:
    """
    Calculate nature from personality value.

    Nature = personality % 25

    Args:
        personality: 32-bit personality value

    Returns:
        Nature ID (0-24)
    """
    return personality % 25


def get_ability_slot_from_personality(personality: int) -> int:
    """
    Determine which ability slot from personality.

    Ability slot = personality & 1

    Args:
        personality: 32-bit personality value

    Returns:
        0 or 1 (ability slot index)
    """
    return personality & 1


def get_gender_from_personality(personality: int, gender_threshold: int) -> int:
    """
    Determine gender from personality value.

    Args:
        personality: 32-bit personality value
        gender_threshold: Species-specific threshold (0=always male, 254=always female, 255=genderless)

    Returns:
        0 = male, 1 = female, 2 = genderless
    """
    if gender_threshold == 0:
        return 0  # Always male
    elif gender_threshold == 254:
        return 1  # Always female
    elif gender_threshold == 255:
        return 2  # Genderless

    # Gender byte is lowest byte of personality
    gender_byte = personality & 0xFF
    return 1 if gender_byte < gender_threshold else 0


def is_shiny(personality: int, trainer_id: int) -> bool:
    """
    Check if a Pokemon is shiny.

    Shiny = ((trainer_id ^ secret_id) ^ (personality_high ^ personality_low)) < 8

    Args:
        personality: 32-bit personality value
        trainer_id: Full 32-bit trainer ID (includes secret ID in high 16 bits)

    Returns:
        True if shiny
    """
    p_high = (personality >> 16) & 0xFFFF
    p_low = personality & 0xFFFF
    tid = trainer_id & 0xFFFF
    sid = (trainer_id >> 16) & 0xFFFF

    return ((tid ^ sid) ^ (p_high ^ p_low)) < 8

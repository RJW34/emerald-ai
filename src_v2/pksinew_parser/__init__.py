"""
Gen 3 Pokemon Save Parser Package

A modular parser for Generation 3 Pokemon save files.
Supports: FireRed, LeafGreen, Ruby, Sapphire, Emerald

Usage:
    from parser import Gen3SaveParser

    parser = Gen3SaveParser("path/to/save.sav")
    if parser.loaded:
        print(f"Trainer: {parser.trainer_name}")
        print(f"Party: {len(parser.party_pokemon)} Pokemon")
"""

# Constants (commonly used)
from .constants import OFFSETS_RSE  # Legacy alias for OFFSETS_RS
from .constants import (
    EXP_TABLES,
    INTERNAL_TO_NATIONAL,
    NATIONAL_TO_INTERNAL,
    OFFSETS_E,
    OFFSETS_FRLG,
    OFFSETS_RS,
    PERMUTATIONS,
    calculate_level_from_exp,
    convert_species_to_internal,
    convert_species_to_national,
    get_growth_rate,
    is_valid_species,
)

# Crypto utilities
from .crypto import (
    decode_gen3_text,
    decrypt_pokemon_data,
    encode_gen3_text,
    encrypt_pokemon_data,
    get_block_order,
    get_block_position,
)

# Main parser class
from .gen3_parser import Gen3SaveParser

# Item utilities
from .items import (
    ITEM_NAMES,
    get_bag_summary,
    get_item_name,
    parse_bag,
    parse_money,
)

# Pokedex
from .pokedex import (
    count_bits_set,
    get_pokemon_from_bitfield,
    parse_pokedex,
)

# Pokemon parsing
from .pokemon import (
    get_box_structure,
    parse_party,
    parse_party_pokemon,
    parse_pc_boxes,
    parse_pc_pokemon,
)

# Save structure
from .save_structure import (
    build_section_map,
    detect_game_type,
    find_active_save_slot,
    get_save_info,
    validate_save,
)

# Trainer utilities
from .trainer import (
    NATURE_NAMES,
    format_play_time,
    format_trainer_id,
    get_nature_name,
    get_pokemon_nature,
    is_shiny,
    parse_trainer_info,
)

# Version
__version__ = "2.1.0"
__author__ = "Cameron"

# For backwards compatibility, also export as Gen3SaveParser
__all__ = [
    "Gen3SaveParser",
    "PERMUTATIONS",
    "INTERNAL_TO_NATIONAL",
    "convert_species_to_national",
    "is_valid_species",
    "calculate_level_from_exp",
    "decode_gen3_text",
    "encode_gen3_text",
    "parse_party_pokemon",
    "parse_pc_pokemon",
    "get_item_name",
    "is_shiny",
    "get_nature_name",
    "parse_pokedex",
]

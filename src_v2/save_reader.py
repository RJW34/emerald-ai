"""
save_reader.py — Wraps PKsinew Gen3SaveParser to read .sav files
and return clean structured game state for emerald-ai.
"""

import logging
import os

log = logging.getLogger(__name__)

# Trade evolution species (national dex IDs)
TRADE_EVOS = {
    64: "Kadabra",
    67: "Machoke",
    75: "Graveler",
    93: "Haunter",
}

# Emerald badge names in bit order (bit 0 through bit 7)
# Badge byte at section2 + 0x3FD: bit 7 = Stone (badge 1), bit 0 = Rain (badge 8)
EMERALD_BADGES_BY_BIT = {
    7: "Stone",
    6: "Knuckle",
    5: "Dynamo",
    4: "Heat",
    3: "Balance",
    2: "Feather",
    1: "Mind",
    0: "Rain",
}


def read_save(sav_path):
    """
    Parse a Gen3 .sav file and return structured game state.

    Args:
        sav_path: Path to the .sav file

    Returns:
        dict with keys: trainer, badges, party, boxes, trade_evos_ready
        or None on failure
    """
    if not os.path.exists(sav_path):
        log.debug(f"Save file not found: {sav_path}")
        return None

    try:
        from .pksinew_parser import Gen3SaveParser
    except ImportError as e:
        log.error(f"Failed to import Gen3SaveParser: {e}")
        return None

    try:
        parser = Gen3SaveParser(sav_path)
        if not parser.loaded:
            log.warning(f"Parser failed to load save: {sav_path}")
            return None

        # --- Trainer info ---
        trainer_info = parser.get_trainer_info() or {}
        trainer = {
            "name": trainer_info.get("name", "Unknown"),
            "gender": trainer_info.get("gender", "Unknown"),
            "trainer_id": trainer_info.get("trainer_id", 0),
            "money": parser.money,
            "play_time": f"{trainer_info.get('play_hours', 0)}:{trainer_info.get('play_minutes', 0):02d}:{trainer_info.get('play_seconds', 0):02d}",
        }

        # --- Badges (Emerald specific: section 2 + 0x3FD) ---
        # Ordered Stone -> Rain (badge 1 through 8)
        badges_list = [False] * 8
        badge_names = []
        try:
            section2_offset = parser.section_offsets.get(2, 0)
            if section2_offset > 0:
                badge_byte = parser.data[section2_offset + 0x3FD]
                for i in range(8):
                    # i=0 -> Stone (bit 7), i=1 -> Knuckle (bit 6), etc.
                    bit_index = 7 - i
                    badges_list[i] = bool(badge_byte & (1 << bit_index))
                    if badges_list[i]:
                        badge_names.append(EMERALD_BADGES_BY_BIT[bit_index])
        except Exception as e:
            log.warning(f"Badge parsing failed: {e}")

        trainer["badges_count"] = sum(badges_list)
        trainer["badges"] = badge_names

        # --- Party ---
        party_raw = parser.get_party() or []
        party = []
        trade_evos_ready = []
        for poke in party_raw:
            if not poke:
                continue
            species_id = poke.get("species", 0)
            entry = {
                "species_id": species_id,
                "nickname": poke.get("nickname", "???"),
                "level": poke.get("level", 0),
            }
            party.append(entry)
            if species_id in TRADE_EVOS:
                trade_evos_ready.append({
                    "species_id": species_id,
                    "name": TRADE_EVOS[species_id],
                    "nickname": poke.get("nickname", "???"),
                    "level": poke.get("level", 0),
                })

        # --- PC Boxes ---
        pc_raw = parser.get_pc_boxes() or []
        boxes = []
        for poke in pc_raw:
            if not poke:
                continue
            species_id = poke.get("species", 0)
            entry = {
                "species_id": species_id,
                "nickname": poke.get("nickname", "???"),
                "level": poke.get("level", 0),
                "box": poke.get("box_number", 0),
            }
            boxes.append(entry)
            if species_id in TRADE_EVOS:
                trade_evos_ready.append({
                    "species_id": species_id,
                    "name": TRADE_EVOS[species_id],
                    "nickname": poke.get("nickname", "???"),
                    "level": poke.get("level", 0),
                    "location": f"Box {poke.get('box_number', '?')}",
                })

        return {
            "trainer": trainer,
            "badges": badges_list,
            "party": party,
            "boxes": boxes,
            "trade_evos_ready": trade_evos_ready,
        }

    except Exception as e:
        log.error(f"Error reading save file: {e}", exc_info=True)
        return None

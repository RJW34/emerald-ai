"""
Run Configuration — gameplay constants for emerald-ai.

These are hardcoded constraints for every autonomous run.
The battle AI and game loop reference these values.
"""

# =============================================================================
# Player Identity
# =============================================================================
PLAYER_NAME = "RYAN"

# =============================================================================
# Starter Selection
# =============================================================================
STARTER_CHOICE = "MUDKIP"  # Left bag at Prof Birch's lab

# =============================================================================
# Text Speed / Options
# =============================================================================
# Options byte location: Save Block 2 base + 0x13
# In Pokemon Emerald, Save Block 2 pointer is at 0x03005D90
# For direct EWRAM access: 0x02024E00 + 0x13 = 0x02024E13
OPTIONS_BYTE_ADDR = 0x02024E13

# Text speed bits (bits 0-1 of options byte)
TEXT_SPEED_SLOW = 0
TEXT_SPEED_MID = 1
TEXT_SPEED_FAST = 2
TEXT_SPEED_MASK = 0x03  # bits 0-1

# Full optimal options byte: text=FAST(2) | animations=OFF(1<<3) | style=SET(1<<6)
# 0x02 | 0x08 | 0x40 = 0x4A
OPTIMAL_OPTIONS_BYTE = 0x4A

# =============================================================================
# Shiny Detection (Gen 3)
# =============================================================================
# A Pokemon is shiny if: ((OT_ID ^ OT_SID) ^ (PID_HI ^ PID_LO)) < 8
#
# In battle, the enemy mon struct starts at a known offset in battle memory.
# Key fields for shiny check:
#   PID:    personality value (32-bit) — PID_HI = PID >> 16, PID_LO = PID & 0xFFFF
#   OT_ID:  original trainer ID (16-bit)
#   OT_SID: original trainer secret ID (16-bit)
SHINY_THRESHOLD = 8

# Battle mon struct offsets (from base of battle mon in EWRAM)
# These are for the *enemy* mon in a wild battle.
# The battle AI reads these to detect shininess and trigger capture.
BATTLE_MON_PID_OFFSET = 0x00       # 4 bytes, personality value
BATTLE_MON_OT_ID_OFFSET = 0x04     # 2 bytes, trainer ID
BATTLE_MON_OT_SID_OFFSET = 0x06    # 2 bytes, secret ID


def is_shiny(pid: int, ot_id: int, ot_sid: int) -> bool:
    """
    Check if a Pokemon is shiny using Gen 3 formula.

    Args:
        pid: 32-bit personality value
        ot_id: 16-bit original trainer ID
        ot_sid: 16-bit original trainer secret ID

    Returns:
        True if the Pokemon is shiny.
    """
    pid_hi = (pid >> 16) & 0xFFFF
    pid_lo = pid & 0xFFFF
    return ((ot_id ^ ot_sid) ^ (pid_hi ^ pid_lo)) < SHINY_THRESHOLD


# =============================================================================
# Shiny Encounter Rule
# =============================================================================
# If a wild encounter is shiny, the AI MUST attempt to capture it.
# This overrides all other battle strategies (flee, fight, etc).
SHINY_MUST_CAPTURE = True

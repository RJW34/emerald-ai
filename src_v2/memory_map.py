"""Emerald (BPEE) memory addresses — verified from pokeemerald.sym"""


# Save block pointers (IWRAM — always valid)
SAVE_BLOCK_1_PTR = 0x03005D8C  # Dereference → SaveBlock1 base
SAVE_BLOCK_2_PTR = 0x03005D90  # Dereference → SaveBlock2 base

# SaveBlock1 offsets (add to dereferenced ptr)
PLAYER_X_OFFSET = 0x00  # u16
PLAYER_Y_OFFSET = 0x02  # u16
MAP_GROUP_OFFSET = 0x04  # u8
MAP_NUM_OFFSET = 0x05  # u8

# SaveBlock2 offsets (add to dereferenced ptr)
OPTIONS_OFFSET = 0x13  # u16 — game options (text speed in bits 2-0)

# OPTIONS byte value for: fast text (2) + no battle anims (bit3) + stereo (bits 6-5 = 10)
OPTIONS_FAST = 0x4A

# Battle type flags (EWRAM — read directly)
BATTLE_TYPE_FLAGS = 0x02022FEC  # u32

VALID_SAVE_PTR_MIN = 0x02000000
VALID_SAVE_PTR_MAX = 0x04000000

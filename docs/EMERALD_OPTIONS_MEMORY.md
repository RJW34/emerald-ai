# Pokemon Emerald Options Memory Documentation

## Overview
Game options in Pokemon Emerald are stored as a single byte (bitfield) in Save Block 2 at offset 0x13.

## Memory Location
- **Address**: Save Block 2 + 0x13 (already defined in `memory_map.py` as `OPTIONS_OFFSET`)
- **Type**: 1 byte (u8)
- **Access**: Pointer-based read via Save Block 2 pointer

## Options Bitfield Layout

Based on pokeemerald source code structure:

| Bits | Option | Values |
|------|--------|--------|
| 0-2  | Text Speed | 0 = Slow, 1 = Mid, 2 = Fast |
| 3    | Battle Scene | 0 = On, 1 = Off |
| 4    | Battle Style | 0 = Switch, 1 = Set |
| 5    | Sound | 0 = Mono, 1 = Stereo |
| 6-7  | Button Mode & Frame | (not critical for AI) |

## Optimal Settings for AI Bot

1. **Text Speed**: Fast (value = 2)
   - Bits 0-2 = 0b010 (binary) = 2 (decimal)
   - Reduces dialogue waiting time

2. **Battle Scene**: Off (value = 1)
   - Bit 3 = 1
   - Skips battle animations for faster battles

3. **Battle Style**: Set (value = 1)
   - Bit 4 = 1
   - No switching prompt after KO (more aggressive gameplay)

## Calculated Optimal Value

```
Bit layout for optimal settings:
- Bits 0-2 (Text Speed): 010 (Fast = 2)
- Bit 3 (Battle Scene): 1 (Off)
- Bit 4 (Battle Style): 1 (Set)
- Bits 5-7: 000 (defaults)

Binary: 0001_1010
Hex: 0x1A
Decimal: 26
```

**Expected optimal options byte: 0x1A (26)**

## Reading Settings

```python
# Read current options value
options_byte = state_detector._read_from_save_block_2(OPTIONS_OFFSET, 1)

# Extract individual settings
text_speed = options_byte & 0x07          # Bits 0-2
battle_scene = (options_byte >> 3) & 0x01 # Bit 3
battle_style = (options_byte >> 4) & 0x01 # Bit 4
```

## Options Menu Navigation

The Options menu is accessed via: START → OPTIONS

Menu structure (vertical navigation):
1. Text Speed (toggle with LEFT/RIGHT: Slow → Mid → Fast)
2. Battle Scene (toggle with LEFT/RIGHT: On → Off)
3. Battle Style (toggle with LEFT/RIGHT: Switch → Set)
4. Sound (toggle)
5. Button Mode (toggle)
6. Frame (cycles through frame styles)
7. Cancel (exits menu)

**Navigation strategy:**
- Use UP/DOWN to move between options
- Use LEFT/RIGHT or A to toggle settings
- Press B or select "Cancel" to exit

## Sources
- pokeemerald decompilation project (github.com/pret/pokeemerald)
- Save data structure documentation (Bulbapedia)
- Verified against memory_map.py in this project

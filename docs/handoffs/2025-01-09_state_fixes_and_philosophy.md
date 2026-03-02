# Session Handoff: 2025-01-09 - State Detection Fixes & Philosophy

## What Was Accomplished

### 1. Battle State Detection Fixed
- **Problem**: `BATTLE_TYPE_FLAGS` retained residual data after battle ended, causing false positives
- **Solution**: Added check for `BATTLE_OUTCOME` (non-zero = battle ended) and validate player species in battle RAM
- **File**: `src/games/pokemon_gen3/state_detector.py:294-320`

### 2. Post-Intro Location Recognition
- **Problem**: Loading save states in Birch's Lab showed UNKNOWN state
- **Solution**: Added `MAP_BIRCHS_LAB = (1, 4)` and updated `_infer_initial_state()` and `_determine_state_from_map()` to recognize post-starter locations
- **File**: `src/games/pokemon_gen3/intro_handler.py`

### 3. Ambiguous State Naming Fixed
- **Problem**: `IN_LITTLEROOT` was ambiguous - houses ARE in Littleroot Town
- **Solution**: Renamed to `LITTLEROOT_EXTERIOR` to clearly mean "outside in town, not inside any building"
- **Pattern identified**: Location-based states should be specific about indoor vs outdoor

### 4. Robust House Exit Validation
- **Problem**: `_has_exited_house` flag was set on glitchy single map reads during 1F cutscene
- **Solution**:
  - Added position validation: `is_valid_exterior_position = (y >= 7 and x >= 3 and x <= 12)`
  - Added consecutive confirmation counter: requires 3 valid readings before setting flag
  - If position looks like interior and current state is INSIDE_HOUSE_1F, stay in that state
- **File**: `src/games/pokemon_gen3/intro_handler.py:621-662`

### 5. Knowledge Philosophy Documented
- **New section in CLAUDE.md**: "Knowledge Philosophy: Mechanics vs Gameplay"
- **Core principle**: Use external resources for ENGINE knowledge (input timing, memory addresses, menu navigation), keep GAMEPLAY decisions organic (routes, team building, battle strategy)
- **Rationale**: Technical competence enables authentic play; nobody wants to watch fumbling with basic inputs

### 6. Dialogue Turbo Mode
- **Problem**: Bot pressed A only once per 0.2s tick during dialogue - too slow
- **Solution**: Added `turbo_a()` method that sends 3 rapid A presses (~0.03s apart)
- **Files**:
  - `src/input_controller.py:127-149` - new method
  - `src/main.py:107-109` - uses turbo_a for dialogue
  - `src/games/pokemon_gen3/intro_handler.py` - multiple dialogue handlers updated

### 7. Speedrun Research
Key frame data from speedrun.com and TASVideos:
- Walking: 16 frames per tile (~0.27s at 60fps)
- Turning: 8 frames (~0.13s)
- No input buffering in Gen 3 - must wait for actions to complete
- Text on Fast speed runs at fixed rate - mash A constantly

## Current State
- Battle handler integration: Working (defeated Zigzagoon in testing)
- Intro sequence: Partially working, still has navigation issues in Littleroot
- State detection: Much more robust with validation and confirmation counters

## Critical Context
**The core pattern we identified**: Permanent flags should NEVER be set based on single memory reads. Always require:
1. Position validation (is the position consistent with the claimed state?)
2. Consecutive confirmations (multiple readings before committing)
3. Ability to recover if wrong (don't make irreversible decisions on glitchy data)

## Blockers / Issues Remaining
- Littleroot navigation still oscillates without reaching Route 101
- Many connection timeouts in BizHawk IPC (may be performance issue)
- User hasn't provided full playthrough feedback yet

## Next Steps
1. Get user's detailed writeup on remaining dysfunctions
2. Fix Littleroot -> Route 101 navigation
3. Test complete intro sequence end-to-end
4. Verify text speed is being set correctly

## Save States Available
- Slot 1: Truck (start of game)
- Slot 2: Battle with Zigzagoon
- Slot 10: Birch's lab after getting starter

---
*Session date: 2025-01-09*

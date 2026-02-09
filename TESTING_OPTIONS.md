# Testing Guide: Options Menu Configuration

## Overview
Implemented automatic configuration of game settings for optimal AI performance.

**Commit**: `0b9cc4e` - Add Pokemon Emerald Options menu navigation and settings verification

## What Was Implemented

### 1. Memory Reading
- `read_options()` - Reads options bitfield from Save Block 2 offset 0x13
- `verify_optimal_settings()` - Checks if settings match optimal values
- Extracts: Text Speed, Battle Scene, Battle Style, Sound

### 2. Automatic Configuration
- `_configure_game_settings()` - Opens Options menu and sets optimal values
- Runs once per session when bot starts in overworld
- Fixed sequence navigation (no state detection dependency)

### 3. Optimal Settings
- **Text Speed**: Fast (value 2) - reduces dialogue delays
- **Battle Scene**: Off (value 1) - skips battle animations
- **Battle Style**: Set (value 1) - no switch prompt after KO

Expected memory value: `0x1A` (26 decimal)

## Testing Steps

### Test 1: Memory Read Verification

**Goal**: Verify options are read correctly from memory

1. Start BizHawk with Pokemon Emerald
2. Load a save file (any progress level)
3. Run test script:
   ```bash
   python test_options.py
   ```

**Expected Output**:
```
CURRENT SETTINGS:
  Text Speed:    [Current value]
  Battle Scene:  [Current value]
  Battle Style:  [Current value]
  Sound:         [Current value]
  Raw byte:      0xXX

OPTIMAL SETTINGS CHECK:
  ✓ PASS - All settings are optimal!
  OR
  ✗ FAIL - Settings need configuration:
    - [List of non-optimal settings]
```

**Pass Criteria**:
- Script connects to BizHawk successfully
- Settings display correctly (match in-game options)
- Optimal check reports correct status

### Test 2: Automatic Configuration (Safe Test)

**Goal**: Verify bot can navigate and configure options

**Setup**:
1. Load a save file in overworld (any location)
2. Manually set options to NON-optimal values:
   - Text Speed: Slow or Mid
   - Battle Scene: On
   - Battle Style: Switch
3. Save the game

**Test**:
1. Start bot: `python -m src.main --strategy safe`
2. Bot should be in overworld state
3. Watch for log output:
   ```
   Settings not optimal - configuring...
   [Configuration sequence]
   ✓ Settings configured successfully!
   ```

**Expected Behavior**:
- Bot opens Start menu
- Navigates to Options
- Changes each setting
- Exits back to overworld
- Logs confirm optimal settings
- Bot continues normal gameplay

**Pass Criteria**:
- Options menu opens successfully
- All 3 settings change to optimal values
- Bot returns to overworld without getting stuck
- Settings persist (check with test_options.py after)

### Test 3: Already Optimal (Skip Test)

**Goal**: Verify bot skips configuration if already optimal

**Setup**:
1. Manually set options to optimal:
   - Text Speed: Fast
   - Battle Scene: Off
   - Battle Style: Set
2. Save the game

**Test**:
1. Start bot: `python -m src.main`
2. Watch logs

**Expected Output**:
```
✓ Settings already optimal!
[Bot continues to gameplay]
```

**Pass Criteria**:
- Bot does NOT open Options menu
- Logs confirm settings are optimal
- Bot immediately starts normal gameplay

### Test 4: Integration Test

**Goal**: Full end-to-end test with battles

**Test**:
1. Set options to non-optimal
2. Start bot in area with wild Pokemon (e.g., Route 101 grass)
3. Let bot run for 5-10 battles
4. Observe:
   - Battle text speed (should be Fast after first check)
   - Battle animations (should skip after first check)
   - Switch prompts after KO (should not appear - Set mode)

**Pass Criteria**:
- Settings configure automatically
- Battle flow is faster (no animations, fast text)
- No switch prompts in Set mode
- No configuration errors during battles

## Known Issues / Limitations

1. **Timing Dependent**: Uses fixed delays for menu navigation
   - May need adjustment if emulator is laggy
   - Should work at normal speed

2. **State Detection**: Options menu not detected as specific state
   - Uses timed sequence instead
   - Works but less robust than state-based logic

3. **Toggle Logic**: Battle Scene and Style are toggles
   - Current code presses RIGHT once
   - Assumes this will set to correct value
   - May need to read-verify-retry loop for safety

4. **One-Time Only**: Configuration runs once per session
   - If player manually changes settings mid-session, bot won't reconfigure
   - Acceptable for AI-only gameplay

## Debugging

If tests fail, check:

1. **Pointer validity**: Are save pointers valid? (Check logs)
2. **Menu navigation timing**: Are delays too short for emulator?
3. **Memory addresses**: Is this US Emerald (BPEE)?
4. **Lua script**: Is BizHawk socket server running?

**Debug mode**: Set logging to DEBUG in test script:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Success Criteria Summary

- ✅ test_options.py reads settings correctly
- ✅ Bot opens Options menu from overworld
- ✅ Bot navigates menu and changes settings
- ✅ Settings verify as optimal after config
- ✅ Bot skips config if already optimal
- ✅ Battle gameplay benefits from optimal settings
- ✅ No stuck states or errors

## Next Steps After Testing

If all tests pass:
1. Test in various overworld locations
2. Test from different save states (early/mid/late game)
3. Consider adding retry logic for failed configuration
4. Consider detecting Options menu state for robustness

## Contact

Post results to #deku-bakugo-sync with:
- Which tests passed/failed
- Screenshots of logs
- Any unexpected behavior
- Timing issues noted

@DEKU - ready for review/refinement based on test results

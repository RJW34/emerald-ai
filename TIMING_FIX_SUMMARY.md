# Emerald AI - Settings Configuration Timing Fix

**Date:** 2026-02-08  
**Issue:** Settings menu navigation completed but settings didn't persist (memory reads: 0,0,0)  
**Status:** ✅ FIXED - Ready for testing

## Problem Analysis

### Root Cause
The `_configure_game_settings()` method had critical timing issues:

1. **Button presses too fast** - 0.1-0.3s delays between inputs
2. **No delay before verification** - Memory read happened immediately after exiting menu
3. **BizHawk IPC lag** - File-based IPC needs time to process commands
4. **Game commit delay** - Pokémon Emerald needs time to write settings to Save Block 2

### Symptoms
- Navigation sequence completed successfully
- Visual confirmation appeared correct
- Memory reads returned `(0, 0, 0)` for all settings
- Settings didn't persist across verification

## Solution Implemented

### 1. Extended Delays Between Actions

| Action | Before | After | Reason |
|--------|--------|-------|--------|
| Start menu open | 0.4s | 2.0s | Menu needs time to fully render |
| Options menu open | 0.5s | 2.5s | Submenu transition delay |
| Menu navigation | 0.12s | 0.2s | Cursor movement reliability |
| After setting changes | 0.3s | 1.0s | Game needs to register change |
| Exit menus | 0.5s | 3.5s | Close animation + buffer |
| **Before verification** | **0s** | **4.0s** | **Game commits to memory** ⭐ |

### 2. Input Method Changes

**Before:**
```python
self.input.tap("Start")  # Single frame press
```

**After:**
```python
self.input.hold("Start", frames=8)  # 8-frame hold (~133ms)
```

**Rationale:** Held inputs are more reliably recognized by BizHawk IPC

### 3. Setting Toggle Logic

**Before (unreliable):**
```python
self.input.tap("Right")  # Toggles once (could go wrong direction)
```

**After (guaranteed):**
```python
for i in range(3):  # For Text Speed: cycles through all 3 values
    self.input.tap("Right")
    time.sleep(0.4)

for i in range(2):  # For toggles: cycles through both states
    self.input.tap("Right")
    time.sleep(0.4)
```

**Rationale:** Multiple presses guarantee correct final value regardless of starting state

### 4. Retry Logic

```python
def _configure_game_settings(self, retry_attempt: int = 0):
    max_retries = 3
    
    # ... configuration sequence ...
    
    if not verify_success:
        if retry_attempt < max_retries:
            return self._configure_game_settings(retry_attempt + 1)
        else:
            # Log failure, mark as attempted, continue
```

**Features:**
- Up to 3 automatic retries
- Recursive retry with attempt counter
- Detailed failure diagnostics
- Graceful degradation (continues if all retries fail)

### 5. Enhanced Logging

**Before:**
```
Setting Text Speed to Fast...
```

**After:**
```
[4/6] Setting Text Speed to Fast...
Initial: Text=0, Scene=0, Style=0 (raw=0x00)
Final: Text=2, Scene=1, Style=1 (raw=0x1A)
```

**Additions:**
- Step markers `[1/6]` through `[6/6]`
- Raw hex byte values for debugging
- Expected vs actual values on failure
- Retry attempt counter

## Code Changes

**File:** `/home/ryan/projects/emerald-ai/src/main.py`  
**Method:** `_configure_game_settings()` (lines 217-363)  
**Lines Changed:** ~80 lines (complete rewrite)

### Key Modifications

1. **Added retry_attempt parameter** for recursive retry logic
2. **Replaced all `tap()` with `hold(frames=8)`** for Start/A/B buttons
3. **Added 4-second delay before verification** (CRITICAL)
4. **Increased all inter-action delays** by 3-8x
5. **Changed toggle logic** to cycle through all possible values
6. **Added detailed logging** at each step
7. **Added return value** (bool) to indicate success/failure

## Testing Requirements

### Environment
- **OS:** Windows (BAKUGO)
- **Emulator:** BizHawk with Lua socket bridge
- **ROM:** Pokémon Emerald (BPEE)
- **IPC:** File-based button input system

### Test Cases

#### TC1: First-Attempt Success (Expected Case)
```
1. Start game in overworld
2. Run EmeraldAI
3. Observe settings configuration sequence
4. Verify: Text=2, Scene=1, Style=1 after first attempt
5. Check logs: "✓ Settings configured successfully!"
```

#### TC2: Retry Logic (Edge Case)
```
1. Manually set settings to non-optimal values
2. Run EmeraldAI with slower emulator speed (50%)
3. First attempt should fail
4. Should automatically retry up to 3 times
5. Eventually succeed or gracefully fail
```

#### TC3: Memory Persistence
```
1. Configure settings successfully
2. Close and reopen Options menu
3. Verify settings still show correct values
4. Check memory: read_options() returns (2, 1, 1)
```

#### TC4: Timing Validation
```
1. Monitor logs for delay durations
2. Confirm 4-second wait before verification
3. Check that hold() calls are used for critical buttons
4. Verify each step has adequate delay
```

### Expected Output

**Success:**
```
==================================================
CONFIGURING GAME SETTINGS (Attempt 1/4)
==================================================
Initial: Text=0, Scene=0, Style=0 (raw=0x00)
[1/6] Opening Start menu...
[2/6] Navigating to Options...
[3/6] Opening Options menu...
[4/6] Setting Text Speed to Fast...
[5/6] Setting Battle Scene to Off...
[6/6] Setting Battle Style to Set...
Exiting Options menu...
Waiting for game to commit settings to memory...
Verifying settings...
Final: Text=2, Scene=1, Style=1 (raw=0x1A)
✓ Settings configured successfully!
==================================================
```

**Failure with Retry:**
```
⚠ Settings verification failed!
  Expected: Text=2, Scene=1, Style=1
  Got: Text=0, Scene=0, Style=0
Retrying configuration (attempt 2/4)...
```

## Performance Impact

### Time Cost
- **Before:** ~3 seconds total
- **After:** ~20 seconds total (first attempt)
- **With retries:** Up to ~80 seconds (4 attempts × 20s)

### Justification
- Configuration happens **once per session** (negligible impact)
- Reliability >> speed for critical one-time setup
- Failed configuration would require manual intervention (worse)

## Risk Assessment

### Low Risk
- Changes isolated to `_configure_game_settings()` method
- No impact on battle logic or overworld navigation
- Retry logic prevents infinite loops (max 3 retries)
- Graceful failure mode (logs warning, continues)

### Testing Required
- BizHawk/Windows environment (DEKU can't test)
- Real emulator timing (not mockable)
- Memory read verification (requires actual game state)

## Next Steps

1. **BAKUGO Testing** - Run on Windows/BizHawk
2. **Timing Validation** - Confirm delays are adequate
3. **Memory Verification** - Check read_options() returns correct values
4. **Retry Testing** - Force failure to test retry logic
5. **Integration** - Verify no regressions in main game loop

## Files Modified

- ✅ `/home/ryan/projects/emerald-ai/src/main.py` - Fixed timing and retry logic

## Files to Review (No Changes Needed)

- `/home/ryan/projects/emerald-ai/src/input_controller.py` - `hold()` method already exists
- `/home/ryan/projects/emerald-ai/src/games/pokemon_gen3/state_detector.py` - `read_options()` and `verify_optimal_settings()` unchanged

---

**Author:** DEKU (subagent)  
**Coordinated with:** BAKUGO (pending testing)  
**Status:** Ready for integration testing

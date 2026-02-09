# Testing Notes - Settings Configuration Timing Fix

## Testing Coordinator: BAKUGO (Windows/BizHawk)

### Pre-Test Setup

1. **Ensure BizHawk is running** with Pokémon Emerald ROM loaded
2. **Load Lua socket bridge script** for IPC communication
3. **Start from overworld** with character able to open Start menu
4. **Set settings to non-optimal** (manually via Options menu):
   - Text Speed: Slow (0)
   - Battle Scene: On (0)
   - Battle Style: Switch (0)

### Test 1: Basic Functionality

**Goal:** Verify settings change and persist

**Steps:**
```bash
cd /home/ryan/projects/emerald-ai  # (Windows equivalent)
python -m src.main --strategy aggressive
```

**Watch for:**
- [ ] Start menu opens (should see 2-second pause)
- [ ] Cursor moves to Options (6 Down presses visible)
- [ ] Options menu opens (2.5-second delay)
- [ ] Text Speed changes (visible in menu)
- [ ] Battle Scene toggles
- [ ] Battle Style toggles
- [ ] Menu exits cleanly
- [ ] 4-second wait before "Verifying settings..." log

**Expected Log Output:**
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

**Success Criteria:**
- Final values: `Text=2, Scene=1, Style=1`
- Raw byte: `0x1A` (binary: 00011010)
  - Bits 0-2 (Text Speed): 010 = 2 (Fast)
  - Bit 3 (Battle Scene): 1 = Off
  - Bit 4 (Battle Style): 1 = Set
- No retry attempts needed

### Test 2: Retry Logic

**Goal:** Verify retry mechanism works

**Steps:**
1. Modify timing to be too fast (temporarily reduce delays)
2. Run EmeraldAI
3. Observe retry behavior

**Expected:**
- First attempt fails (settings read as 0,0,0)
- Log shows: "⚠ Settings verification failed!"
- Automatically retries up to 3 times
- Eventually succeeds or logs final error

**OR:**
1. Pause emulator during settings configuration
2. Unpause after verification starts
3. Should fail and retry

### Test 3: Memory Persistence

**Goal:** Confirm settings persist across menu opens

**Steps:**
1. Run EmeraldAI, wait for settings config success
2. Manually open Start menu → Options
3. Visually confirm settings show:
   - Text Speed: **FAST**
   - Battle Scene: **OFF**
   - Battle Style: **SET**
4. Exit and continue

**Success Criteria:**
- Settings visually match expected values
- No manual changes required

### Test 4: Timing Validation

**Goal:** Verify all delays are adequate

**Method:** Add timestamp logging to confirm delays

**Checkpoints:**
- Start menu open: ~2.0s delay
- Options menu open: ~2.5s delay
- Between menu moves: ~0.2s per step
- After setting changes: ~1.0s each
- Exit sequence: ~3.5s total
- **Before verification: ~4.0s** ⭐

**Measurement:**
```python
# Add to code temporarily for validation:
import time
t1 = time.time()
# ... action ...
t2 = time.time()
logger.info(f"Elapsed: {t2 - t1:.2f}s")
```

### Test 5: Edge Cases

#### Case A: Already Optimal
**Setup:** Manually set settings to optimal (2, 1, 1)
**Expected:** `verify_optimal_settings()` returns True, skips config
**Location:** Check `_handle_overworld()` logic

#### Case B: Partial Success
**Setup:** One setting fails to change
**Expected:** Retry logic catches mismatch, retries entire sequence

#### Case C: Total Failure
**Setup:** Disconnect IPC during config (simulate complete failure)
**Expected:** 
- 3 retry attempts
- Final error log
- `_settings_configured = True` (prevents infinite loop)
- Game continues with warning

### Test 6: Integration

**Goal:** Verify no regressions in main loop

**Steps:**
1. Run EmeraldAI for 5 minutes
2. Observe:
   - Settings config happens once
   - Overworld navigation works
   - Battle system works
   - No hangs or crashes

**Success Criteria:**
- Settings configured successfully on first tick in overworld
- Normal gameplay continues after config
- No repeated config attempts

## Known Issues to Watch For

### Issue 1: Toggle State Confusion
**Symptom:** Battle Scene or Battle Style toggle wrong direction
**Cause:** Current value not read before toggling
**Fix Applied:** Cycle through all values (press Right 2x for toggles)
**Verify:** Both settings end at correct value regardless of starting state

### Issue 2: IPC Lag Spikes
**Symptom:** Occasional input drops even with delays
**Cause:** Windows/BizHawk process scheduling
**Mitigation:** Retry logic handles transient failures
**Verify:** Retries eventually succeed

### Issue 3: Memory Read Timing
**Symptom:** Read happens before game commits to Save Block 2
**Cause:** File-based IPC and game frame timing
**Fix Applied:** 4-second delay before verification
**Verify:** Memory reads return non-zero values

## Debugging Commands

### Read Current Settings (Python REPL)
```python
from src.emulator.bizhawk_client import BizHawkClient
from src.games.pokemon_gen3.state_detector import PokemonGen3StateDetector

client = BizHawkClient()
client.connect()
detector = PokemonGen3StateDetector(client)
opts = detector.read_options()
print(f"Text={opts['text_speed']}, Scene={opts['battle_scene']}, Style={opts['battle_style']}, raw=0x{opts['raw']:02X}")
```

### Manual Button Test
```python
from src.input_controller import InputController

input_ctrl = InputController(client)
input_ctrl.hold("Start", frames=8)  # Test hold vs tap
```

### Verify Save Block 2 Read
```python
# Check if memory reads are working at all
detector._read_from_save_block_2(0x13, 1)  # Should return options byte
```

## Success Metrics

- [ ] Settings configure successfully on first attempt (90%+ of runs)
- [ ] Retry logic activates and succeeds if first attempt fails
- [ ] Memory reads return correct values after 4-second delay
- [ ] No infinite loops or hangs
- [ ] Configuration completes in <25 seconds (single attempt)
- [ ] No regressions in battle or overworld systems

## Failure Scenarios

If tests fail:

1. **Check BizHawk Lua bridge** - ensure IPC is responsive
2. **Increase delays further** - try 2x all current values
3. **Check emulator speed** - must be 100% (not fast-forward)
4. **Verify ROM** - must be Pokémon Emerald (BPEE)
5. **Check logs** - which step fails? (step marker [X/6])
6. **Test manual navigation** - can you manually navigate Options menu?

## Post-Test Deliverables

Report to #deku-bakugo-sync:

```
## Test Results: Emerald AI Settings Config

**Environment:** Windows 11, BizHawk 2.9.1, Emerald (BPEE)
**Date:** YYYY-MM-DD

### Test 1: Basic Functionality
- Result: [PASS/FAIL]
- Settings final: Text=_, Scene=_, Style=_
- Raw byte: 0x__
- Retries needed: _
- Notes: ___

### Test 2: Retry Logic
- Result: [PASS/FAIL]
- Notes: ___

### Test 3: Memory Persistence
- Result: [PASS/FAIL]
- Notes: ___

### Issues Found:
- [ ] None
- [ ] Issue description...

### Recommendations:
- [ ] Ship as-is
- [ ] Adjust timing: ___
- [ ] Other: ___
```

---

**Prepared by:** DEKU  
**For:** BAKUGO testing  
**Status:** Ready for Windows/BizHawk validation

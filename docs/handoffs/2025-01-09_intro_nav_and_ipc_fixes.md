# Session Handoff: 2025-01-09 - Intro Navigation & IPC Fixes

## What Was Accomplished

### 1. Fixed tap() vs walk() for Overworld Movement
- **Problem**: Multiple places in `intro_handler.py` used `tap(direction)` for overworld movement instead of `walk(direction)`
- **Root cause**: `tap()` holds button for 6 frames (single press), `walk()` holds for 12 frames (continuous movement)
- **Solution**: Replaced ALL overworld `tap()` calls with `walk()`:
  - Line 1105: Exit door navigation
  - Line 1147: Stair warp positioning
  - Line 1199: Clock approach
  - Line 1238, 1249: Stair navigation
  - Line 1254: Clock movement
- **File**: `src/games/pokemon_gen3/intro_handler.py`
- **Pattern**: `tap()` is ONLY for menu navigation. `walk()` for ALL overworld movement.

### 2. Simplified Rival House Logic
- **Problem**: Original code tried to navigate upstairs in rival house - unnecessary for story progression
- **Discovery**: Just talking to May on 1F is enough to "meet rival" and unlock Route 101 access
- **Solution**:
  - Removed upstairs navigation logic
  - Added `_visited_rival_house` flag
  - After 40 ticks in rival house without detecting dialogue, assume dialogue completed and set flag
  - Once flag set, navigate to door at x=2 and walk down to exit
- **File**: `src/games/pokemon_gen3/intro_handler.py` (`_handle_rival_house_1f()`)

### 3. Added Floor Transition Cooldown for Rival House
- **Problem**: State oscillated rapidly between `INSIDE_RIVAL_HOUSE_1F` and `INSIDE_RIVAL_HOUSE_2F` during map detection glitches
- **Solution**: Added cooldown logic (same pattern as player's house):
  - `block_rival_1f_to_2f` and `block_rival_2f_to_1f` checks
  - Set `_floor_transition_cooldown` when transitioning between rival house floors
- **File**: `src/games/pokemon_gen3/intro_handler.py` (state transition section)

### 4. Added IPC File Write Retry Logic
- **Problem**: Intermittent `[Errno 13] Permission denied` errors on `command.txt` during high-frequency writes
- **Root cause**: Windows file locking - Lua script has file open when Python tries to write
- **Solution**: Added retry loop (5 attempts, 50ms delay) in `_send_command()`:
  ```python
  for attempt in range(max_write_retries):
      try:
          with open(self.command_file, "w") as f:
              f.write(f"{cmd_id}:{command}")
          break
      except PermissionError:
          if attempt < max_write_retries - 1:
              time.sleep(write_retry_delay)
          else:
              logger.error("Failed after retries")
              return None
  ```
- **File**: `src/emulator/bizhawk_client.py:78-108`

### 5. Fixed Rival House Exit Navigation
- **Problem**: Bot stuck at (3, 8) when trying to exit - kept walking down but door was at x=2
- **Solution**: Added x-axis navigation before walking down:
  ```python
  if x > 2:
      self.input.walk("Left")
  elif x < 2:
      self.input.walk("Right")
  else:
      self.input.walk("Down")
  ```

## Current State
- Intro sequence: Truck → House 1F → Room 2F (clock) → House 1F → Littleroot → Rival House → Littleroot (Route 101 direction)
- Bot successfully exits rival's house with `visited_rival=True` flag
- IPC retry logic should prevent command.txt permission failures

## Critical Code Patterns (Add to CLAUDE.md)

### Movement Pattern
```python
# OVERWORLD (walking around)
self._move("Up")          # Best - uses walk() with stuck detection
self.input.walk("Left")   # Good - continuous movement
self.input.tap("Up")      # WRONG for overworld - too short

# MENUS (cursor navigation)
self.input.tap("Down")    # Correct - single frame input
self.input.tap("A")       # Correct - button press
```

### Story Flag Pattern
```python
# Don't need complex interactions - simple flags work
if self._state_ticks > 40 and not self._visited_rival_house:
    logger.info("Assuming dialogue completed")
    self._visited_rival_house = True
```

## Blockers / Issues Remaining
- Route 101 navigation not tested yet (bot reaches Littleroot with flag set)
- Prof. Birch encounter / starter selection not implemented
- May need to handle "save the professor" cutscene

## Save States
- Slot 1: Truck (start of game) - use for full intro testing

### 6. Process Manager for Autonomous Control
- **Created**: `scripts/process_manager.py`
- **Capabilities**:
  - `start` - Start BizHawk + bot + load save state
  - `stop` - Stop everything
  - `restart` - Full restart
  - `restart-bot` - Restart only bot (for code changes, keeps BizHawk)
  - `status` - Check running processes
- **Key fix**: Uses targeted PID killing instead of `taskkill /F /IM python.exe` which would kill itself
- **Usage**: `python scripts/process_manager.py restart-bot` after code changes

## Next Steps
1. Complete full intro test to Route 101
2. Implement Route 101 → Save Birch → Starter selection
3. Test battle handler integration with wild encounters

---
*Session date: 2025-01-09 (Late evening - process manager added)*

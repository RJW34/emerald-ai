# Session Handoff: 2025-01-10 - Continuous Movement & Script Lock Detection

## What Was Accomplished

### 1. True Continuous Movement (HOLD_START/HOLD_STOP)
- **Problem**: Player took stuttery short steps instead of smooth continuous movement
- **Root cause**: Even with 60-frame HOLD commands, gaps between commands caused stuttering
- **User insight**: "When I play pokemon, it's as simple as holding the physical joystick down so it is continually registering"
- **Solution**: Implemented HOLD_START/HOLD_STOP for indefinite button holding

**Files Modified:**

**bizhawk_bridge.lua** - Added commands:
```lua
-- HOLD_START - Start holding a button indefinitely (until HOLD_STOP)
elseif command == "HOLD_START" then
    local button = parts[2]
    held_buttons[button] = true
    hold_frames[button] = 999999  -- Effectively infinite
    return "OK"

-- HOLD_STOP - Stop holding a button
elseif command == "HOLD_STOP" then
    local button = parts[2]
    held_buttons[button] = false
    hold_frames[button] = 0
    return "OK"
```

**bizhawk_client.py** - Added methods:
```python
def hold_start(self, button: str) -> bool:
    """Start holding a button indefinitely until hold_stop is called."""
    response = self._send_command(f"HOLD_START {button}")
    return response is not None and response.startswith("OK")

def hold_stop(self, button: str) -> bool:
    """Stop holding a button."""
    response = self._send_command(f"HOLD_STOP {button}")
    return response is not None and response.startswith("OK")
```

**input_controller.py** - Rewrote walk() and added stop_walking():
```python
def walk(self, direction: str, frames: int = 60) -> bool:
    """Walk in a direction by holding the button CONTINUOUSLY."""
    # If already holding this direction, no need to resend
    if self._current_held_direction == direction:
        return True

    # Stop any currently held direction first
    if self._current_held_direction is not None:
        self.client.hold_stop(self._current_held_direction)

    # Start holding the new direction
    result = self.client.hold_start(direction)
    if result:
        self._current_held_direction = direction
    return result

def stop_walking(self) -> bool:
    """Stop all directional movement."""
    if self._current_held_direction is None:
        return True
    result = self.client.hold_stop(self._current_held_direction)
    if result:
        self._current_held_direction = None
    return result
```

**Key Pattern**: Always call `stop_walking()` before pressing A for dialogue or any non-movement action.

### 2. Script Lock Detection Using sLockFieldControls
- **Problem**: TEXT_PRINTERS approach had gaps between dialogue boxes where it returned false
- **User feedback**: "Mom keeps speaking but we only advance the conversation once"
- **Source**: pokeemerald symbols branch (https://github.com/pret/pokeemerald/tree/symbols)
- **Discovery**: `sLockFieldControls` at 0x03000F2C is the authoritative bool for player movement lock

**memory_map.py** - Added addresses:
```python
# sLockFieldControls - TRUE (1) when player cannot move due to script/dialogue
SCRIPT_LOCK_FIELD_CONTROLS: ClassVar[int] = 0x03000F2C  # 1 byte bool

# sGlobalScriptContextStatus - Script execution state
SCRIPT_CONTEXT_STATUS: ClassVar[int] = 0x03000E38  # 1 byte
```

**state_detector.py** - Added method:
```python
def is_player_locked(self) -> bool:
    """Check if player movement is locked by scripts/dialogue."""
    try:
        lock_state = self.client.read8(self.mem.SCRIPT_LOCK_FIELD_CONTROLS)
        return lock_state != 0
    except (MemoryReadError, ConnectionError, TimeoutError):
        return False
```

**Why sLockFieldControls is better than TEXT_PRINTERS:**
- TEXT_PRINTERS has gaps between individual text boxes (returns false briefly)
- sLockFieldControls stays locked for ENTIRE script execution (set by LockPlayerFieldControls, cleared by UnlockPlayerFieldControls)
- This means all of Mom's multi-box dialogue keeps player locked the whole time

### 3. Coordinate Fixes for Male Player
- **Problem**: Bot navigated to x=7-8 but player house is at x=5 for male character
- **Discovery**: Player gender affects Littleroot layout:
  - Male (Brendan) = Player house on LEFT (x~5)
  - Female (May) = Player house on RIGHT
- **Files**: Fixed coordinates in `intro_handler.py` (_handle_outside_truck, stair navigation)

### 4. Simplified House Navigation
- **Problem**: Bot moved in multiple directions when only UP was needed
- **User insight**: "All the player *should* have to do after completing his conversation with mom is walk straight to his room"
- **Solution**: Simplified `_handle_inside_house` first visit to just walk UP:
```python
else:
    # First visit: just walk UP to stairs
    # After Mom's greeting dialogue, stairs are straight ahead
    self.input.walk("Up")
```

## Critical Pokeemerald References

Found in symbols branch:
- `sLockFieldControls` = 0x03000F2C (bool, player movement lock)
- `sGlobalScriptContextStatus` = 0x03000E38 (script execution state)
- `sGlobalScriptContext` = 0x03000E40 (full script context struct, 116 bytes)

Script context status values:
- CONTEXT_RUNNING = some value when script executing
- CONTEXT_WAITING = waiting for input/event
- CONTEXT_SHUTDOWN = script complete

## Current State
- Bot should navigate: Truck → House 1F (Mom dialogue) → 2F (room) → Clock set → Rival house → Route 101
- Movement is now truly continuous (HOLD_START/HOLD_STOP)
- Dialogue detection uses proper sLockFieldControls
- House navigation simplified to just walk UP

## Known Issues / Next Steps
1. Test full intro sequence from truck
2. May need further coordinate tweaks based on testing
3. Route 101 / Birch encounter not yet implemented

## Important User Feedback This Session
- "Are you using the scripting and emerald speedrunning/TAS resources provided to find methodology to use, or are you just 'freeballing' changes?" - Led to proper pokeemerald research
- "When I play pokemon, it's as simple as holding the physical joystick down" - Led to HOLD_START/HOLD_STOP
- "All the player *should* have to do after completing his conversation with mom is walk straight to his room" - Led to simplified navigation

---
*Session date: 2025-01-10 (Early morning - continuous movement and script lock)*

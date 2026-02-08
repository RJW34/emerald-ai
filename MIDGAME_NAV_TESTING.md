# Mid-Game Overworld Navigation - Testing Guide

**Commit:** `370d509`  
**Date:** 2026-02-08  
**Changes:** Added overworld navigation logic to get bot moving in mid-game

## What Changed

### Problem
Bot was stuck in mid-game overworld - `_handle_overworld()` was essentially empty (just logging position every 10 ticks).

### Solution
Implemented random walk navigation with:
1. **Direction persistence** - walks in one direction for 5-15 ticks instead of randomly changing every frame
2. **Obstacle detection** - tracks position each tick; if stuck in same position for 3+ ticks, immediately picks new direction
3. **Natural battle triggering** - random walking in grass/caves will trigger wild encounters which existing battle AI handles

### Code Changes
- Added navigation state tracking to `EmeraldAI.__init__()`:
  - `_current_direction` - which way we're walking
  - `_direction_persist_ticks` - how long we've walked this direction
  - `_direction_persist_target` - how long to walk before changing
  - `_last_position` - for detecting walls/obstacles
  - `_position_stuck_counter` - how many ticks we've been stuck

- Replaced stub `_handle_overworld()` with actual navigation logic

## Testing Instructions for BAKUGO

### Setup
1. Pull latest code: `git pull origin master`
2. Verify commit hash: `git log --oneline -1` should show `370d509`
3. Make sure BizHawk is running with Emerald loaded at mid-game overworld position

### Test Scenarios

#### Test 1: Basic Movement
**Location:** Any overworld area (route, town, etc.)  
**Expected:** Bot should:
- Walk in one direction for 5-15 ticks
- Change direction smoothly when timer expires
- Log direction changes to console: `New direction: Up for 12 ticks`

#### Test 2: Obstacle Handling
**Location:** Next to a wall, NPC, or building  
**Expected:** Bot should:
- Hit the obstacle and detect position not changing
- After 3 stuck ticks, immediately pick new direction
- Log: `Hit obstacle at (x, y), changing direction`
- Successfully navigate around the obstacle

#### Test 3: Wild Battles
**Location:** Tall grass area (e.g., Route 101, 102, etc.)  
**Expected:** Bot should:
- Walk around randomly in grass
- Eventually trigger wild encounter
- Seamlessly transition to battle (existing battle AI takes over)
- After battle, resume random walking

#### Test 4: Intro Sequence (Regression Test)
**Location:** Start new game from beginning  
**Expected:** Bot should:
- Still handle intro sequence correctly (dialogue pressing A)
- NOT interfere with intro cutscenes
- Only start random walking once reaching normal overworld gameplay

### What to Watch For

**Good Signs:**
- ✅ Bot walks smoothly in one direction for several steps
- ✅ Direction changes look natural (not spamming inputs)
- ✅ Bot navigates around walls/obstacles without getting stuck
- ✅ Wild battles trigger and are handled correctly
- ✅ Position logs show coordinates actually changing

**Bad Signs:**
- ❌ Bot gets stuck in corners/against walls forever
- ❌ Bot rapidly changes direction every tick (direction persistence broken)
- ❌ Bot doesn't move at all
- ❌ Intro sequence broken (starts walking during cutscenes)

### Console Output to Check

Look for these log patterns:
```
[INFO] State: DIALOGUE → OVERWORLD
[DEBUG] New direction: Up for 8 ticks
[DEBUG] Overworld: pos=(123, 456), map=(25, 16)
[DEBUG] Hit obstacle at (123, 456), changing direction
[DEBUG] New direction: Right for 12 ticks
[INFO] State transition: OVERWORLD → BATTLE_WILD
[INFO] Battle started!
[INFO] Wild battle: Lv.3 ZIGZAGOON
```

### Known Limitations

1. **No pathfinding** - Bot walks randomly, not toward objectives
2. **No tall grass preference** - Doesn't seek out grass to trigger battles
3. **No danger avoidance** - Won't avoid trainers or dangerous areas
4. **No map awareness** - Might walk into dead ends

These are future enhancements. Current goal: **get it moving and battling**.

## Next Steps (After Testing)

If testing succeeds:
- [ ] Bot can navigate mid-game overworld without getting stuck
- [ ] Bot triggers and handles wild battles
- [ ] No regression in intro sequence

Then we can enhance with:
1. Tall grass seeking (maximize wild encounters for training)
2. Trainer detection and engagement
3. Basic pathfinding toward objectives
4. Healing awareness (go to Pokemon Center when low HP)

## Rollback Instructions

If this breaks something:
```bash
git revert 370d509
```

Or checkout previous commit:
```bash
git checkout HEAD~1
```

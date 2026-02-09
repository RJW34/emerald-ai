# Pokemon Emerald - Title Screen & New Game Testing Instructions

## What Was Implemented

1. **Title Screen Detection**
   - Reads game state byte at `0x0300500C`
   - Value `0xFF` = Title Screen detected
   - Added to `detect()` method in `state_detector.py`

2. **New Game Initialization Handler**
   - Comprehensive 171+ step state machine
   - Automates entire startup sequence from title → playable game
   - **CRITICAL**: Selects **MUDKIP** (left bag)
   
3. **State Tracking**
   - `_in_new_game_flow`: Boolean flag for flow activation
   - `_new_game_step`: Current step in sequence (0-171+)
   - `_new_game_input_delay`: Timing control between inputs

## Testing Procedure

### Prerequisites
- Windows machine with BizHawk
- Pokemon Emerald ROM (US version, BPEE)
- **Fresh ROM boot** (no save file) OR reset to title screen
- Lua script running in BizHawk (`emerald-ai/bizhawk_lua/http_server.lua`)

### Test 1: Fresh ROM Boot
1. Start BizHawk with clean Pokemon Emerald ROM
2. Load the Lua HTTP server script
3. Start the AI: `python -m src.main`
4. **Expected behavior:**
   - Bot detects title screen (state byte = 0xFF)
   - Automatically presses Start
   - Navigates through New Game
   - Advances dialogue (spams A)
   - Selects gender (Boy)
   - Accepts default name OR enters "DEKU"
   - Advances through moving truck intro
   - Sets clock (accepts defaults)
   - Navigates to Prof Birch event on Route 101
   - **Selects LEFT bag = MUDKIP**
   - Completes first battle vs Poochyena
   - Returns to lab, receives Pokedex
   - Flow completes when `party_count > 0`

5. **Success criteria:**
   - Mudkip is in party slot 1
   - Game state transitions to OVERWORLD
   - Bot begins normal autonomous play
   - No manual input required

### Test 2: Mid-Intro Resume (Idempotence)
1. Start ROM and manually advance to ANY point in intro (naming, truck, etc.)
2. Start the AI
3. **Expected behavior:**
   - Bot continues from current point
   - May spam A through remaining dialogue
   - Should eventually reach playable state
   - Flow completes gracefully

### Test 3: Title Screen Loop
1. Boot to title screen
2. Start AI
3. Let it run through New Game
4. Once in overworld, manually reset ROM to title
5. **Expected behavior:**
   - Bot detects title screen again
   - Restarts new game flow
   - Can repeat indefinitely

## What to Watch For

### ✅ Success Indicators
- Console log: `"TITLE SCREEN DETECTED - Starting new game initialization"`
- Console log: `"Step 111: SELECTING MUDKIP (left bag) - CRITICAL STEP"`
- Console log: `"✓ NEW GAME INITIALIZATION COMPLETE!"`
- Party count = 1 (Mudkip)
- Game transitions to OVERWORLD state
- Bot begins random walking/battling

### ❌ Failure Modes

1. **Wrong starter selected**
   - Symptom: Treecko or Torchic in party instead of Mudkip
   - Cause: Left input not registered or timing issue
   - Fix: Adjust delay at step 111, or add multiple Left presses

2. **Stuck in dialogue loop**
   - Symptom: Step counter keeps incrementing, no progress
   - Cause: Timing delays too short, missing state transitions
   - Fix: Increase `_new_game_input_delay` values

3. **Failsafe triggered (step > 200)**
   - Symptom: Warning log "New game step exceeded"
   - Cause: Flow took longer than expected
   - Fix: Flow will reset to step 50 and continue

4. **Title screen not detected**
   - Symptom: Bot stays in UNKNOWN state
   - Cause: Memory address incorrect or emulator issue
   - Fix: Verify `0x0300500C` reads `0xFF` at title screen

## Verification Commands

After new game flow completes:

```python
# Check party (should have 1 Pokemon - Mudkip)
party_count = state_detector.get_party_count()
print(f"Party count: {party_count}")

# Check first Pokemon (should be Mudkip, species ID 258)
if party_count > 0:
    pokemon = state_detector.read_party().pokemon[0]
    print(f"Species: {pokemon.species_name or pokemon.species_id}")
    print(f"Level: {pokemon.level}")
```

Expected output:
```
Party count: 1
Species: MUDKIP (or species ID 258)
Level: 5
```

## Logging Output Example

```
[12:34:56] INFO: TITLE SCREEN DETECTED - Starting new game initialization
[12:34:57] INFO: Step 0: Pressing Start to advance past title
[12:34:58] INFO: Step 1: Selecting 'New Game'
[12:34:59] INFO: Step 2-15: Advancing through intro dialogue
[12:35:05] INFO: Step 16: Selecting gender (Boy)
[12:35:10] INFO: Step 21: Naming character 'DEKU'
[12:35:15] INFO: Step 22-50: Advancing through intro sequence
[12:35:30] INFO: Step 81-100: Navigating to Prof Birch event
[12:35:45] INFO: Step 101-110: Prof Birch dialogue, approaching bag
[12:35:50] INFO: Step 111: SELECTING MUDKIP (left bag) - CRITICAL STEP
[12:35:51] INFO: Step 112: Confirming Mudkip selection
[12:36:00] INFO: Step 116-130: First battle sequence (Poochyena)
[12:36:15] INFO: Step 131-170: Post-battle sequence
[12:36:25] INFO: Step 171: Checking if new game initialization is complete...
[12:36:25] INFO: ✓ NEW GAME INITIALIZATION COMPLETE!
[12:36:25] INFO:   Party count: 1
[12:36:25] INFO:   Game is ready for autonomous play
[12:36:26] INFO: State: TITLE_SCREEN -> OVERWORLD
```

## Known Limitations

1. **Timing Dependent**: Delays are tuned for BizHawk at normal speed. Speedup may break flow.
2. **Name Entry**: Currently accepts default name instead of entering "DEKU" manually (complex input)
3. **Manual Intervention**: If flow gets stuck, manual A presses can help advance
4. **Battle Takeover**: Once first battle starts, battle AI takes over automatically

## Next Steps After Testing

1. Post results in #deku-bakugo-sync
2. If issues found, capture logs and screenshots
3. Note which step the bot gets stuck at (if any)
4. Report starter Pokemon obtained (MUST be Mudkip)
5. Confirm game reaches autonomous play state

## Contact

Post all results, issues, or questions in **#deku-bakugo-sync**

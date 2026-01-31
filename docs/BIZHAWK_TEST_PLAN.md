# BizHawk Live Test Plan

## Prerequisites
- Windows machine with BizHawk 2.6.2+ installed
- Pokemon Emerald ROM (USA)
- Python 3.10+ with project dependencies
- Network connectivity between machines (if running Python on Linux)

## Setup Steps
1. Load Pokemon Emerald in BizHawk
2. Open Lua Console (Tools → Lua Console)
3. Load `scripts/bizhawk/bizhawk_bridge_v2.lua`
4. On the Python side: `python -m src.main --strategy aggressive`

## Test Sequence

### Phase 1: Connection
- [ ] Python TCP server starts on port 51055
- [ ] BizHawk Lua connects successfully
- [ ] HELLO handshake received
- [ ] PING/PONG verified
- [ ] Connection survives 60+ seconds idle

### Phase 2: Memory Reading
- [ ] `read8`, `read16`, `read32` return correct values
- [ ] `read_range` returns correct byte sequences
- [ ] Cross-reference: read player name from known offset, verify matches in-game
- [ ] `GETSTATE` bulk read returns all expected keys
- [ ] Memory reads during battle match visible game state

### Phase 3: State Detection
- [ ] Detect overworld state correctly
- [ ] Detect wild battle start
- [ ] Detect trainer battle start
- [ ] Read player Pokemon stats (HP, level, moves) — verify against Summary screen
- [ ] Read enemy Pokemon stats — verify against visible info
- [ ] Detect battle end (win/lose/flee)
- [ ] Weather detection in battle

### Phase 4: Input Control
- [ ] `TAP A` registers correctly
- [ ] `TAP B` registers correctly
- [ ] D-pad directions work
- [ ] `HOLD` for multiple frames works
- [ ] `PRESS` (multiple buttons) works
- [ ] Inputs don't desync with emulator timing

### Phase 5: Battle Loop
- [ ] AI correctly selects moves in wild battle
- [ ] AI correctly handles trainer battle
- [ ] AI uses super effective moves when available
- [ ] AI switches Pokemon when appropriate (safe strategy)
- [ ] AI flees from wild battles (speedrun strategy)
- [ ] Battle decisions execute within 1 frame window

### Phase 6: Stress Testing
- [ ] Run AI through 10 consecutive wild battles
- [ ] Run AI through a gym leader fight
- [ ] Measure average decision latency
- [ ] Check for memory leaks / socket issues over extended run
- [ ] Verify no desyncs between emulator and AI state

## Memory Address Validation

Key addresses to verify (from `memory_map.py`):
```
BATTLE_TYPE_FLAGS  - Should show correct battle type
BATTLE_MONS        - Player/enemy data at expected offsets
BATTLE_WEATHER     - Weather bits match in-game weather
PARTY_DATA         - Party Pokemon readable outside battle
```

If addresses are wrong, check ROM version header (should be "POKEMON EMER" / "BPEE").

## Cross-Machine Setup (Linux Python ↔ Windows BizHawk)
- Modify `DEFAULT_HOST` in socket client to `0.0.0.0`
- Modify Lua bridge to connect to Linux machine's IP
- Ensure firewall allows TCP port 51055
- Test latency: should be <5ms on local network

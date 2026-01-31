# Emerald AI — Project Status

**Last updated:** 2025-07-09

## Current State

### ✅ Complete (works offline)
- **Socket bridge** (`bizhawk_socket_client.py`): TCP server with length-prefixed protocol, bulk GETSTATE, ~1-2ms latency
- **Battle AI** (`battle_ai.py`): Multi-strategy decision engine (aggressive/safe/speedrun/grind/catch)
- **Damage calculator**: Full Gen 3 formula with abilities, weather, STAB, type chart
- **Battle simulator**: Offline multi-turn battle simulation with mock memory
- **Move database**: All 354 Gen 3 moves with type/power/accuracy/flags
- **Species database**: Species name lookup
- **Test suite**: 73 tests passing — socket client, battle AI, data, e2e battles, simulator, survival

### 🔧 Needs Live Testing (requires BizHawk on Windows)
- Socket bridge ↔ BizHawk Lua script handshake
- Memory address validation (offsets may vary by ROM version)
- Real-time state reading performance
- Input controller (button presses via socket)
- Full game loop: detect state → decide → act → repeat

### 📋 Not Yet Built
- Overworld navigation AI (movement, menu interaction)
- Item usage in battle (potions, Poké Balls)
- Party management (ordering, healing decisions)
- Progress tracking integration with battle loop
- Double battle target selection logic

## Architecture

```
BizHawk (Windows) + Lua Bridge
    ↕ TCP Socket (port 51055)
BizHawkSocketClient (Python, can run on Linux)
    ↕
StateDetector → reads game state from memory
    ↕
BattleAI → strategic decisions
    ↕
InputController → sends button presses back
```

## Test Results (2025-07-09)
```
tests/test_battle_ai.py        26 passed
tests/test_data.py              14 passed
tests/test_e2e_battle.py        13 passed
tests/test_simulator.py          6 passed
tests/test_socket_client.py     12 passed
tests/test_survival.py           2 passed
─────────────────────────────────
Total: 73 passed in 0.78s
```

## Simulation Results
| Scenario | Result | Turns | Notes |
|----------|--------|-------|-------|
| Mudkip vs Poochyena | WIN | 3 | Easy early game, Tackle spam |
| Blaziken vs Flygon | LOSE | 2 | Outsped + OHKO'd by Earthquake — legit bad matchup |
| Swampert vs Wailord (Rain) | WIN | 3 | Earthquake 2HKOs despite rain-boosted enemy Surf |

## Known Issues & Improvement Opportunities

### Battle AI Improvements (can do now, no BizHawk needed)

1. **Stat boost awareness**: AI doesn't factor in stat stage changes (+1 Attack = 1.5x, etc.)
2. **Setup move intelligence**: Swords Dance/Calm Mind scored generically, should evaluate if safe to set up
3. **Recoil damage tracking**: Double-Edge recoil not factored into move scoring
4. **Multi-hit move calculation**: Moves like Double Kick scored at single-hit power
5. **Fixed damage moves**: Sonic Boom (20 fixed), Dragon Rage (40 fixed) not handled
6. **Critical hit probability**: High-crit moves (Blaze Kick, Slash) not scored higher
7. **Pinch abilities**: Blaze/Torrent/Overgrow (+50% when HP < 1/3) not checked
8. **Held item effects**: Choice Band, Leftovers, etc. not considered
9. **Status move specificity**: All status moves scored the same — should distinguish sleep/para/toxic
10. **Trap moves**: Mean Look / Spider Web / trapping not considered for switching

### Simulator Improvements (can do now)
1. Enemy AI is trivial (always uses first damaging move) — add basic enemy strategy
2. No stat stage tracking across turns
3. No status damage (poison/burn per turn)
4. No critical hits in simulation
5. Add more scenarios: gym leaders, Elite Four, common wild encounters

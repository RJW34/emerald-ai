# Emerald AI — 100% Completion Spec (LOCKED)

_Agreed with Ryan on 2026-02-23 in #emerald-ai thread._

## Player
- **Name:** RYAN (all caps, typed explicitly by Lua script during intro)
- **Starter:** Mudkip
- **Everything else is AI's choice** — party, routing, catches, strategy

## Architecture
- **Execution:** Lua-native (mGBA internal Lua API), NOT xdotool
- **Dual mGBA instances:** Sandbox (experimentation, no save pressure) + Production (canonical save, OBS-captured, only runs validated scripts)
- **Promotion path:** `cp emerald_sandbox.lua emerald_prod.lua` → mGBA hot-reload
- **Learning loop:** Perception → Decision (inference call via Claude) → Execution → Learning → Lua codification
- **Brain:** MAGNETON (Claude Opus) ↔ control_server.py on ubunztu (port 8778) — reads state, decides action, sends input
- **No hardcoded strategies.** AI learns by doing. A-spam is dead.

## 100% Definition

### Core Completion
- Main story through E4 + Champion (credits)
- Steven Stone postgame fight
- All postgame legendaries: Rayquaza, Regis trio, Lati@s (if no event ticket needed), Terra/Marine cave legendary

### Pokédex
- All single-player obtainable species in Emerald (catch/evolve)
- No trades with other carts, no events, no cheats
- **Trade evos:** bot gets to pre-trade stage (2× Machoke, Haunter, Graveler, Kadabra) — Ryan handles cart trades manually

### Items & Collection
- All ground items (visible + hidden) — picked up naturally during all phases, NOT a discrete phase
- All TMs/HMs obtainable in single player (gym leaders, game corner, shops, ground pickups)
- All in-game trades (let AI discover traded EXP boost naturally)
- Shoal Cave items — tide-dependent, **opportunistic only** (don't soft-lock waiting for tides)
- Lottery corner — daily passive when passing through Lilycove
- All single-player obtainable Secret Base decorations (feasibility TBD — DEKU owes research)
- TMs: collect all, use wisely (Lua script must not waste them)

### Facilities & Challenges
- Contests: all 5 categories × 4 ranks (Normal→Hyper) — postgame priority, requires Pokéblock prep
- Trainer Hill — natural late-game checkpoint, slotted before contests
- Battle Frontier: **stopping point / terminal goal** — explore facilities, attempt runs, gold symbols are ceiling not requirement

### Berries
- Replanting: opportunistic if in-game clock works, skip if broken
- Not a hard requirement (infinite resource)

### Priority Order (postgame)
1. Legendaries + Steven
2. Pokédex grind (catching/evolving, picking up items on routes visited)
3. Trainer Hill
4. Contests (Pokéblock making → condition maxing → appeals)
5. Cleanup sweep (any missed ground items, hidden items, remaining TMs, undone in-game trades)
6. Shoal Cave / lottery (opportunistic throughout all phases)
7. Battle Frontier (terminal)

Items are a **passive layer** across all phases, not a discrete step. The cleanup sweep is just the final "did we miss anything" pass.

### General Principle
If it's achievable in a single Emerald cartridge without cheats/glitches, it's in scope. Postgame tasks sorted by "easiest to accomplish right now" — greedy optimization, no rigid order.

## Infrastructure Audit (2026-02-23)

### What exists on ubunztu
| Component | Status | Issue |
|-----------|--------|-------|
| mGBA-qt PID 135675 (window 56623110) | Running | At NEW GAME menu, not being played |
| mGBA-qt PID 685997 (window 62914566) | Running | In-game overworld (green grass area) |
| src_v2/main.py (PID 632522) | Running | **Embedded mGBA** — plays invisible game in a void, pos stuck at (8,3), save blank |
| game_state_server.py (port 8776) | Running | Reads PID 135675 only (title screen) — wrong PID for in-game instance |
| control_server.py (port 8778) | Running | Uses `xdotool key --window` — mGBA ignores synthetic events |
| emerald_ai_loop.py | Dead | Ran 176 presses on Feb 22 08:04, then stopped. Never restarted |
| mgba_xdotool_controller.py | Available | Same `--window` bug as control_server |
| BizHawk Lua scripts (scripts/bizhawk/) | Available | Wrong emulator but shows Lua approach was started |
| PKsinew parser (src_v2/pksinew_parser/) | Available | Reads badges/party/boxes from .sav files |

### 4 Critical Fixes Needed
1. **xdotool input method** — both control_server.py and mgba_xdotool_controller.py use `--window` flag. Must switch to `windowactivate --sync WID` then key without `--window`
2. **game_state_server PID target** — currently reads PID 135675 (title screen). Needs to read PID 685997 (in-game instance)
3. **emerald_ai_loop.py** — dead, needs restart with fixed input method
4. **src_v2/main.py** — playing invisible embedded game. Kill it; it's not connected to anything visible

### Long-term Architecture Migration
- Current: Python xdotool loop → mGBA-qt window
- Target: Lua script running inside mGBA-qt + inference calls to MAGNETON
- BizHawk Lua scripts at scripts/bizhawk/ are prior art for the socket bridge approach

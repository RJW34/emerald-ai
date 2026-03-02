# Emerald AI — 100% Completion Spec (LOCKED)

_Agreed with Ryan on 2026-02-23 in #emerald-ai thread._

## Player
- **Name:** RYAN (all caps, typed explicitly by Lua script during intro)
- **Starter:** Mudkip
- **Everything else is AI's choice** — party, routing, catches, strategy

## Architecture (LOCKED)
- **Execution:** Lua-native (mGBA internal Lua API), NOT xdotool
- **Dual mGBA instances:** Sandbox (experimentation, no save pressure) + Production (canonical save, OBS-captured, only runs validated scripts)
- **Promotion path:** `cp emerald_sandbox.lua emerald_prod.lua` → mGBA hot-reload
- **Learning loop:** Perception → Decision (inference call via Claude) → Execution → Learning → Lua codification
- **Brain:** MAGNETON (Claude Opus) ↔ Lua HTTP bridge on ubunztu — reads state from Lua, decides action, sends commands back
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

## Infrastructure Reality (updated 2026-02-23 06:30 UTC)

### Current State
- **Two mGBA-qt instances running** — BOTH in overworld, player name "AAAAAAA" (ai_loop A-spammed through intro)
  - PID 135675 (window 56623110): overworld, menu open. Memory scanner works (384KB region, valid SB ptrs) but SB data is all zeros
  - PID 685997 (window 62914566): overworld, no menu. Memory scanner FAILS (no 384KB region)
- **Neither instance has a proper save or player name RYAN** — both were created by blind A-spam through the intro
- **systemd user services running** (emerald-ai, emerald-control, emerald-ai-loop) with xdotool fix applied
- **src_v2/main.py (embedded invisible mGBA) killed** — no longer running
- **xdotool fix applied** in both control_server.py and mgba_xdotool_controller.py (windowactivate --sync, then key without --window)

### What's broken
1. **Game state classification** — reports "title_screen" for an overworld game because SB data reads as all zeros despite valid pointers
2. **ai_loop thinks it's on title screen** — spamming A in the overworld with menu open
3. **Player name is AAAAAAA not RYAN** — intro was A-spammed, not properly navigated
4. **No Lua scripts exist** — the agreed architecture is Lua-native but zero Lua code has been written for mGBA

### What works
- xdotool input method (windowactivate + key) — buttons DO reach the game
- systemd services auto-restart on crash
- control_server.py /press, /screenshot, /lua endpoints
- BizHawk Lua socket bridge scripts exist as prior art (wrong emulator but right pattern)

### Decision: Fresh Start Required
Both mGBA instances are polluted (wrong player name, uncertain state). The right move is:
1. Kill both instances
2. Start ONE fresh mGBA-qt with the ROM
3. Write a Lua script that runs inside it — handles intro (types RYAN), reads game state natively (no /proc/mem hacks), and exposes an HTTP endpoint for the brain
4. The brain (on MAGNETON or via control_server) reads state from Lua and sends decisions back
5. After intro is complete and game is in overworld with proper save, start the second instance as sandbox

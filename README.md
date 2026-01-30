# Emerald AI

Autonomous Pokemon Emerald player. Connects to BizHawk emulator via Lua bridge, reads game state from memory, and makes intelligent battle/navigation decisions.

## Architecture

```
BizHawk + Lua Bridge  ←→  BizHawkClient (File IPC)  ←→  EmeraldAI
                                                           ├── StateDetector (game state from memory)
                                                           ├── BattleAI (strategic combat)
                                                           ├── CompletionTracker (progress monitoring)
                                                           └── InputController (button presses)
```

## Quick Start

```bash
# 1. Start BizHawk with Pokemon Emerald ROM
# 2. Load scripts/bizhawk/bizhawk_bridge_v2.lua in Lua Console
# 3. Run the AI
python -m src.main --strategy aggressive

# Run tests
pytest tests/ -v
```

## Battle Strategies

| Strategy | Behavior |
|----------|----------|
| `aggressive` | KO as fast as possible, smart move selection |
| `safe` | Preserve HP, switch out of bad matchups |
| `speedrun` | Flee wilds, fastest kills for trainers |
| `grind` | Fight everything for XP |
| `catch` | Weaken then attempt capture |

## Components

- **BizHawk Bridge** (`scripts/bizhawk/`): Lua script for emulator communication
- **Battle AI** (`src/ai/battle_ai.py`): Strategic decision engine with kill threshold analysis, speed tier awareness, type/ability/weather considerations
- **Completion Tracker** (`src/tracking/completion_tracker.py`): Reads event flags, badges, Pokedex, party state for progress monitoring
- **State Detector** (`src/games/pokemon_gen3/`): Memory reading for game state (battle, overworld, dialogue detection)

## Lineage

Evolved from `REALCLAUDEEMERALD`, which ported Gen3 code from `GBOperatorHelper` and memory maps from `EmeraldMapInterfaceTool`.

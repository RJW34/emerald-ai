# Emerald AI - Autonomous Pokemon Emerald Player

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start BizHawk with Emerald ROM loaded
# 3. Load the Lua bridge script in BizHawk: Tools > Lua Console > scripts/bizhawk/bizhawk_bridge.lua
# 4. Run the AI
python -m src.main --strategy aggressive
```

## Architecture

```
src/
  main.py                          # Main game loop (EmeraldAI class)
  input_controller.py              # Button input abstraction (tap, hold, walk, stop_walking)
  obs_bridge.py                    # OBS overlay updates

  brain/
    __init__.py                        # GameBrain — LLM decision entry point (OpenRouter)
    llm_client.py                      # OpenRouter API wrapper
    config.py                          # Model tiers, rate limits, env var loading
    state_formatter.py                 # Game state → compact LLM prompt
    prompts.py                        # System prompts (game-specific variants)
    decision_cache.py                  # TTL-based decision cache
    decision_log.py                    # JSONL decision logging
    replay_compiler.py                 # Decision logs → Lua replay script

  emulator/
    bizhawk_client.py              # File-based IPC with BizHawk (command.txt/response.txt)
    bizhawk_socket_client.py       # WebSocket-based BizHawk client (alternative)
    mock_client.py                 # Mock client for testing without emulator
    battle_simulator.py            # Battle simulation for AI testing

  games/pokemon_gen3/
    memory_map.py                  # GBA memory addresses (DMA pointer chasing required)
    state_detector.py              # Game state detection (overworld/battle/menu/dialogue)
    battle_handler.py              # Battle state reading and action execution
    data_types.py                  # Pokemon, Move, Party data structures
    map_data.py                    # Map metadata
    overworld_handler.py           # Navigation with pathfinding + coordinate learning
    run_config.py                  # Game-specific configuration
    exceptions.py                  # Custom exceptions

  ai/
    battle_ai.py                   # Battle strategy engine (aggressive/safe/speedrun/grind/catch)

  learning/                        # Autonomous learning module (~2500 lines)
    autonomous_loop.py             # Orchestrator - ties all learning systems together
    stuck_detector.py              # Position/movement/oscillation/state-loop detection
    coordinate_learner.py          # Discovers warps, NPCs, obstacles through gameplay
    pathfinder.py                  # A* pathfinding with learned obstacle avoidance
    database.py                    # SQLite persistent storage (data/learning.db)
    error_recovery.py              # Escalating recovery strategies
    vision_analyzer.py             # Claude Vision API fallback for stuck states

  data/
    move_data.py                   # Gen 3 move database
    species_data.py                # Gen 3 species database
    map_loader.py                  # Loads pre-parsed map JSON from data/maps/

  tracking/
    completion_tracker.py          # Progress monitoring (badges, pokedex, playtime)

data/
  maps/*.json                      # Pre-seeded map data (warps, NPCs, triggers)
  reference/                       # Speedrun guides and RNG manipulation docs
  progress.json                    # Completion tracking state

scripts/bizhawk/
  bizhawk_bridge.lua               # Lua script that runs inside BizHawk
```

## Key Design Decisions

- **DMA Pointer Chasing**: Gen 3 GBA games relocate save data in RAM. All reads go through Save Block 1/2 pointers (see memory_map.py).
- **File-Based IPC**: BizHawk communicates via command.txt/response.txt files. The Lua script polls for commands and writes responses.
- **Learning Module**: Self-improving navigation. The bot learns obstacle positions, warp locations, and successful paths through gameplay. All data persists in SQLite (data/learning.db).
- **Vision Fallback**: When stuck and all other recovery strategies fail, the system can screenshot the game and ask Claude Vision API for help.

## Game Configuration

- **ROM**: Pokemon Emerald (USA) - Game code BPEE
- **Player Name**: RYAN
- **Starter**: Mudkip
- **Target**: 100% completion (see SPEC.md and CHECKLIST.md)

## Memory Map Reference

Key addresses (Emerald USA / BPEE):
- Save Block 1 pointer: `0x03005D8C`
- Save Block 2 pointer: `0x03005D90`
- Game state callback: `0x0300500C`
- Party data: SB1 + `0x0234` (6 Pokemon x 100 bytes)
- Player position: SB1 + `0x0000` (x/y as u16)
- Map location: SB1 + `0x0004` (group/num as u8)
- Badges: SB2 + `0x0096` (bitmask)

## Testing

```bash
# Run tests
pytest tests/

# Syntax check all source
python -c "import compileall; compileall.compile_dir('src', quiet=1)"
```

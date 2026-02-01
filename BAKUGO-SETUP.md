# Emerald AI - BAKUGO Setup Guide

**Deployment Status:** ✅ Code deployed, ⏳ Emulator needed

---

## What's Already Done

- ✅ Project files deployed to `D:\Projects with Claude\BAKUGO\emerald-ai`
- ✅ Python venv created
- ✅ Dependencies installed

---

## What You Need

### 1. BizHawk Emulator

**Download:** https://tasvideos.org/Bizhawk/ReleaseHistory

**Install to:** `D:\Emulators\BizHawk\`

**Why BizHawk:**
- Lua scripting support (required for memory reading)
- GBA emulation (Pokemon Emerald)
- Save state support
- Frame-by-frame control

### 2. Pokemon Emerald ROM

**File:** `Pokemon - Emerald Version (USA).gba`

**Place in:** `D:\ROMs\GBA\` (or anywhere accessible)

**Legal:** You must own a physical copy of Pokemon Emerald

---

## How to Run

### First Time Setup

1. **Install BizHawk** to `D:\Emulators\BizHawk\`

2. **Get Pokemon Emerald ROM**

3. **Create ROM directory:**
   ```powershell
   New-Item -ItemType Directory -Path "D:\ROMs\GBA" -Force
   ```

4. **Place ROM in directory**

### Running the AI

1. **Start BizHawk**
   ```powershell
   cd "D:\Emulators\BizHawk"
   .\EmuHawk.exe
   ```

2. **Load Pokemon Emerald ROM**
   - File → Open ROM
   - Navigate to `D:\ROMs\GBA\Pokemon - Emerald Version (USA).gba`

3. **Load Lua Bridge**
   - Tools → Lua Console
   - Script → Open Script
   - Navigate to `D:\Projects with Claude\BAKUGO\emerald-ai\scripts\bizhawk\bizhawk_bridge_v2.lua`
   - Click "Run"

4. **Start the AI** (in new terminal)
   ```powershell
   cd "D:\Projects with Claude\BAKUGO\emerald-ai"
   .\venv\Scripts\Activate.ps1
   python -m src.main --strategy aggressive
   ```

---

## Strategies

| Strategy | Behavior |
|----------|----------|
| `aggressive` | KO enemies fast, smart move selection |
| `safe` | Preserve HP, switch out of bad matchups |
| `speedrun` | Flee wilds, fastest trainer kills |
| `grind` | Fight everything for XP |
| `catch` | Weaken + catch Pokemon |

---

## Architecture

```
BizHawk (mGBA core)
  ↓ (memory access)
Lua Bridge Script (bizhawk_bridge_v2.lua)
  ↓ (file-based IPC: state.json, input.json)
EmeraldAI (Python)
  ├── StateDetector (reads game memory)
  ├── BattleAI (makes decisions)
  ├── CompletionTracker (tracks progress)
  └── InputController (sends button presses)
```

---

## Troubleshooting

### "Can't find BizHawk"

Check path: `D:\Emulators\BizHawk\EmuHawk.exe`

If installed elsewhere, update paths in scripts.

### "Lua script error"

Make sure you're using `bizhawk_bridge_v2.lua` (not v1).

### "No state.json file"

Lua bridge creates this. Make sure it's running in BizHawk Lua Console.

### "AI not responding"

Check that:
1. BizHawk is running
2. ROM is loaded
3. Lua script is running (green in Lua Console)
4. Python AI is running

---

## What BAKUGO Provides

- **Windows environment** (BizHawk is Windows-only)
- **GPU acceleration** (better emulator performance)
- **Background execution** (can run while you're doing other things)
- **Persistent sessions** (doesn't depend on DEKU being online)

---

## Future: 1-Click Startup

Once BizHawk + ROM are set up, we can create a batch file that:
1. Starts BizHawk
2. Loads ROM
3. Loads Lua script
4. Starts Python AI

**Coming soon:** `Start Emerald AI.lnk` on desktop

---

**Status:** Code ready, waiting for emulator + ROM setup

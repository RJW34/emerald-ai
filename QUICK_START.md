# Emerald AI - Quick Start Guide

## Current Status
- ✅ BizHawk running (PID 35552)
- ✅ Python environment ready
- ✅ OBS feed configured
- ⚠️ **Lua bridge needs to be loaded**

---

## Step 1: Load Lua Bridge in BizHawk

**In BizHawk (the window that's currently open):**

1. **Tools** menu → **Lua Console**
2. In Lua Console: **Script** menu → **Open Script...**
3. Navigate to: `C:\Users\Ryan\projects\emerald-ai\scripts\bizhawk\`
4. Select: **`bizhawk_socket_bridge.lua`** (recommended)
5. The script should auto-run. You'll see output in the Lua Console:
   ```
   === BizHawk Socket Bridge v1.0 ===
   TCP Server listening on 127.0.0.1:51055
   Waiting for Python client to connect...
   ```

**Alternative scripts** (if socket fails):
- `bizhawk_bridge_v2.lua` - Socket with file fallback (port 52422)
- `bizhawk_bridge.lua` - File-based only (slower but simpler)

---

## Step 2: Start the AI

**In PowerShell:**

```powershell
cd C:\Users\Ryan\projects\emerald-ai
.\start_emerald_ai.ps1
```

This script will:
- ✅ Check if BizHawk is running
- ✅ Check if Lua bridge is active
- ✅ Start the Python AI with "aggressive" strategy

**Or manually:**

```powershell
cd C:\Users\Ryan\projects\emerald-ai
.\venv\Scripts\Activate.ps1
python -m src.main --strategy aggressive
```

---

## Step 3: Watch in OBS

The BizHawk window is already captured in OBS as "BizHawk Emerald AI" source in the "Active Battles" scene.

**Check OBS Studio Monitor**: You should see the Pokemon Emerald game feed.

---

## Strategies Available

| Strategy | Behavior |
|----------|----------|
| `aggressive` | KO enemies fast, smart move selection |
| `safe` | Preserve HP, switch out of bad matchups |
| `speedrun` | Flee wilds, fastest trainer kills |
| `grind` | Fight everything for XP |
| `catch` | Weaken + catch Pokemon |

Change strategy:
```powershell
python -m src.main --strategy speedrun
```

---

## Troubleshooting

### "Lua bridge not detected"
→ Make sure the Lua script is loaded and running in BizHawk's Lua Console (green indicator)

### "BizHawk is not running"
→ BizHawk process (PID 35552) may have crashed. Restart it and load the ROM again.

### "Python module not found"
→ Make sure virtual environment is activated:
```powershell
.\venv\Scripts\Activate.ps1
```

### Black screen / stuck
→ The bot previously got stuck after intro dialogue. The fix mentioned was:
> "Lua bridge reads IWRAM addrs (0x03XXXXXX) via EWRAM domain → returns 0"

If this happens again after loading the new Lua script, check the Python console output for memory read errors.

---

## Background Execution (After Testing)

Once verified working, run in background:

```powershell
Start-Process -FilePath "C:\Users\Ryan\projects\emerald-ai\venv\Scripts\python.exe" `
              -ArgumentList "-m", "src.main", "--strategy", "aggressive" `
              -WorkingDirectory "C:\Users\Ryan\projects\emerald-ai" `
              -WindowStyle Hidden
```

To stop:
```powershell
Get-Process -Name "python" | Where-Object {$_.MainWindowTitle -like "*emerald*"} | Stop-Process
```

Or just kill all Python processes:
```powershell
Stop-Process -Name "python" -Force
```

---

## What the Bot Does

1. **Reads game state** from BizHawk memory (player position, battle status, party info)
2. **Detects context** (overworld, battle, menu, dialogue)
3. **Makes decisions** based on strategy
4. **Sends inputs** (button presses) back to BizHawk
5. **Tracks progress** (badges, HM moves, story flags)

**Example battle flow:**
```
[Battle Start] → Wild Lv.3 Poochyena
[AI] → Select "Fight"
[AI] → Choose "Pound" (2x effective vs Poochyena)
[Enemy] → Poochyena uses Tackle
[AI] → Choose "Pound" again
[Victory] → +42 EXP
```

---

## Next Steps

Once the bot is running successfully:
1. Let it play for 10-15 minutes to verify stability
2. Check for any errors in console output
3. Monitor OBS stream to confirm video feed is working
4. If stable, switch to background execution
5. Consider adding a watchdog to auto-restart if it crashes

**Note**: Save states are recommended. The bot can get stuck in rare edge cases (e.g., wrong warp tiles, soft locks). Having a save state lets you quickly recover.

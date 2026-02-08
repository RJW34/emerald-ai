# Start BizHawk with Lua Script Auto-loaded
# Use this for future sessions (not for current PID 35552)

$ErrorActionPreference = "Stop"

$BIZHAWK_PATH = "C:\Users\Ryan\BizHawk\EmuHawk.exe"
$LUA_SCRIPT = "C:\Users\Ryan\projects\emerald-ai\scripts\bizhawk\bizhawk_socket_bridge.lua"
$ROM_PATH = "C:\Users\Ryan\BizHawk\Pokemon - Emerald Version (USA).gba"  # Update if different

# Check if already running
$existing = Get-Process -Name "EmuHawk" -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[WARN] BizHawk is already running (PID: $($existing.Id))" -ForegroundColor Yellow
    Write-Host "Close it first or load the Lua script manually:" -ForegroundColor Yellow
    Write-Host "  1. Tools -> Lua Console" -ForegroundColor White
    Write-Host "  2. Script -> Open Script -> $LUA_SCRIPT" -ForegroundColor White
    exit 0
}

Write-Host "Starting BizHawk with Lua bridge..." -ForegroundColor Cyan
Write-Host "  ROM: $ROM_PATH" -ForegroundColor Gray
Write-Host "  Lua: $LUA_SCRIPT" -ForegroundColor Gray
Write-Host ""

# Start BizHawk with Lua script and Lua Console
& $BIZHAWK_PATH `
    --lua $LUA_SCRIPT `
    --luaconsole `
    $ROM_PATH

Write-Host "BizHawk launched!" -ForegroundColor Green
Write-Host "The Lua Console should open automatically with the script loaded." -ForegroundColor White

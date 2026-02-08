# Start Emerald AI - Pokemon Bot for BizHawk
# Prerequisites: BizHawk running with Lua bridge loaded

$ErrorActionPreference = "Stop"
$PROJECT_DIR = "C:\Users\Ryan\projects\emerald-ai"

Write-Host "=== Emerald AI Startup ===" -ForegroundColor Cyan

# Check if BizHawk is running
$bizhawk = Get-Process -Name "EmuHawk" -ErrorAction SilentlyContinue
if (-not $bizhawk) {
    Write-Host "[ERROR] BizHawk is not running!" -ForegroundColor Red
    Write-Host "Please start BizHawk and load Pokemon Emerald ROM first." -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] BizHawk is running (PID: $($bizhawk.Id))" -ForegroundColor Green

# Check if venv exists
if (-not (Test-Path "$PROJECT_DIR\venv\Scripts\activate.ps1")) {
    Write-Host "[ERROR] Virtual environment not found!" -ForegroundColor Red
    Write-Host "Run: python -m venv venv" -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] Virtual environment found" -ForegroundColor Green

# Check if Lua bridge is active (look for socket connection or IPC files)
$ipcActive = $false
if (Test-Path "$PROJECT_DIR\scripts\bizhawk\state.json") {
    $ipcActive = $true
    Write-Host "[OK] File-based IPC detected (state.json exists)" -ForegroundColor Green
} else {
    Write-Host "[WARN] No IPC files detected - testing socket connection..." -ForegroundColor Yellow
    
    # Quick socket test (5 second timeout)
    $socketTest = Start-Job -ScriptBlock {
        cd "C:\Users\Ryan\projects\emerald-ai"
        & ".\venv\Scripts\python.exe" -c @"
import socket
import time
for port in [51055, 52422]:
    try:
        sock = socket.socket()
        sock.settimeout(2)
        sock.connect(('127.0.0.1', port))
        print(f'CONNECTED:{port}')
        sock.close()
        exit(0)
    except:
        pass
print('NO_CONNECTION')
exit(1)
"@
    }
    
    Wait-Job $socketTest -Timeout 5 | Out-Null
    $result = Receive-Job $socketTest
    Remove-Job $socketTest -Force
    
    if ($result -like "CONNECTED:*") {
        $port = $result.Split(':')[1]
        $ipcActive = $true
        Write-Host "[OK] Socket bridge detected on port $port" -ForegroundColor Green
    }
}

if (-not $ipcActive) {
    Write-Host ""
    Write-Host "[ERROR] Lua bridge not detected!" -ForegroundColor Red
    Write-Host "In BizHawk:" -ForegroundColor Yellow
    Write-Host "  1. Tools -> Lua Console" -ForegroundColor Yellow
    Write-Host "  2. Script -> Open Script" -ForegroundColor Yellow
    Write-Host "  3. Load: $PROJECT_DIR\scripts\bizhawk\bizhawk_socket_bridge.lua" -ForegroundColor Yellow
    Write-Host "  4. Click 'Run'" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Then run this script again." -ForegroundColor Cyan
    exit 1
}

# Start the AI
Write-Host ""
Write-Host "Starting Emerald AI..." -ForegroundColor Cyan
Write-Host "Strategy: aggressive" -ForegroundColor White
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

Set-Location $PROJECT_DIR
& ".\venv\Scripts\activate.ps1"
& ".\venv\Scripts\python.exe" -m src.main --strategy aggressive

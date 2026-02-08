# Verify Emerald AI Setup
# Checks all prerequisites before starting the AI

$ErrorActionPreference = "Stop"
$PROJECT_DIR = "C:\Users\Ryan\projects\emerald-ai"

Write-Host ""
Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  Emerald AI Setup Verification" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

$allGood = $true

# 1. Check BizHawk process
Write-Host "[1/6] Checking BizHawk process..." -NoNewline
$bizhawk = Get-Process -Name "EmuHawk" -ErrorAction SilentlyContinue
if ($bizhawk) {
    Write-Host " OK (PID $($bizhawk.Id))" -ForegroundColor Green
} else {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host "      BizHawk is not running. Start it first." -ForegroundColor Yellow
    $allGood = $false
}

# 2. Check virtual environment
Write-Host "[2/6] Checking virtual environment..." -NoNewline
if (Test-Path "$PROJECT_DIR\venv\Scripts\python.exe") {
    Write-Host " OK" -ForegroundColor Green
} else {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host "      Run: python -m venv venv" -ForegroundColor Yellow
    $allGood = $false
}

# 3. Check Python AI code
Write-Host "[3/6] Checking Python AI code..." -NoNewline
if (Test-Path "$PROJECT_DIR\src\main.py") {
    Write-Host " OK" -ForegroundColor Green
} else {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host "      main.py not found at $PROJECT_DIR\src\" -ForegroundColor Yellow
    $allGood = $false
}

# 4. Check Lua scripts
Write-Host "[4/6] Checking Lua scripts..." -NoNewline
$luaScripts = @(
    "bizhawk_socket_bridge.lua",
    "bizhawk_bridge_v2.lua",
    "bizhawk_bridge.lua"
)
$foundLua = $false
foreach ($script in $luaScripts) {
    if (Test-Path "$PROJECT_DIR\scripts\bizhawk\$script") {
        $foundLua = $true
        break
    }
}
if ($foundLua) {
    Write-Host " OK" -ForegroundColor Green
} else {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host "      No Lua scripts found at $PROJECT_DIR\scripts\bizhawk\" -ForegroundColor Yellow
    $allGood = $false
}

# 5. Check OBS WebSocket
Write-Host "[5/6] Checking OBS WebSocket..." -NoNewline
try {
    $test = New-Object System.Net.Sockets.TcpClient
    $test.Connect("127.0.0.1", 4455)
    $test.Close()
    Write-Host " OK" -ForegroundColor Green
} catch {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host "      OBS WebSocket not accessible at ws://127.0.0.1:4455" -ForegroundColor Yellow
    Write-Host "      (Non-critical - OBS may not be running)" -ForegroundColor Gray
    # Don't fail overall check for OBS
}

# 6. Check Lua bridge active
Write-Host "[6/6] Checking Lua bridge status..." -NoNewline

# Check for IPC files
$ipcFiles = @(
    "$PROJECT_DIR\scripts\bizhawk\state.json",
    "$PROJECT_DIR\scripts\bizhawk\command.txt",
    "$PROJECT_DIR\scripts\bizhawk\input.json"
)
$foundIPC = $false
foreach ($file in $ipcFiles) {
    if (Test-Path $file) {
        $foundIPC = $true
        break
    }
}

if ($foundIPC) {
    Write-Host " OK (File-based IPC detected)" -ForegroundColor Green
} else {
    # Test socket ports
    $socketPorts = @(51055, 52422)
    $socketActive = $false
    
    foreach ($port in $socketPorts) {
        try {
            $test = New-Object System.Net.Sockets.TcpClient
            $test.Connect("127.0.0.1", $port)
            $test.Close()
            $socketActive = $true
            Write-Host " OK (Socket bridge active on port $port)" -ForegroundColor Green
            break
        } catch {
            # Port not open, try next
        }
    }
    
    if (-not $socketActive) {
        Write-Host " NOT ACTIVE" -ForegroundColor Red
        Write-Host "      Lua bridge not detected. Load script in BizHawk:" -ForegroundColor Yellow
        Write-Host "      1. Tools -> Lua Console" -ForegroundColor Gray
        Write-Host "      2. Script -> Open Script" -ForegroundColor Gray
        Write-Host "      3. Select: $PROJECT_DIR\scripts\bizhawk\bizhawk_socket_bridge.lua" -ForegroundColor Gray
        Write-Host "      4. Click 'Run'" -ForegroundColor Gray
        $allGood = $false
    }
}

Write-Host ""
Write-Host "==================================" -ForegroundColor Cyan

if ($allGood) {
    Write-Host "  All checks passed! Ready to run." -ForegroundColor Green
    Write-Host "==================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Start the AI with:" -ForegroundColor White
    Write-Host "  .\start_emerald_ai.ps1" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Or manually:" -ForegroundColor White
    Write-Host "  .\venv\Scripts\Activate.ps1" -ForegroundColor Gray
    Write-Host "  python -m src.main --strategy aggressive" -ForegroundColor Gray
    Write-Host ""
    exit 0
} else {
    Write-Host "  Setup incomplete. Fix issues above." -ForegroundColor Red
    Write-Host "==================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "See QUICK_START.md for detailed instructions." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# deploy_to_bakugo.ps1

$baseUrl = "http://192.168.1.40:8765/emerald-ai"
$targetDir = "D:\Projects with Claude\BAKUGO\emerald-ai"
$ProgressPreference = 'SilentlyContinue'

Write-Host "=== Emerald AI Deployment ===" -ForegroundColor Cyan

$files = @(
    "README.md",
    "requirements.txt",
    "check.py",
    "poc_socket_connection.py",
    "src/__init__.py",
    "src/main.py",
    "src/input_controller.py",
    "src/ai/__init__.py",
    "src/ai/battle_ai.py",
    "src/tracking/__init__.py",
    "src/tracking/completion_tracker.py",
    "src/emulator/__init__.py",
    "src/emulator/bizhawk_client.py",
    "src/emulator/bizhawk_socket_client.py",
    "src/emulator/battle_simulator.py",
    "src/emulator/mock_client.py",
    "src/games/__init__.py",
    "src/games/pokemon_gen3/__init__.py",
    "src/games/pokemon_gen3/state_detector.py",
    "src/games/pokemon_gen3/memory_map.py",
    "src/games/pokemon_gen3/battle_handler.py",
    "src/games/pokemon_gen3/data_types.py",
    "src/games/pokemon_gen3/exceptions.py",
    "scripts/bizhawk/bizhawk_bridge.lua",
    "scripts/bizhawk/bizhawk_socket_bridge.lua",
    "scripts/bizhawk/bizhawk_bridge_v2.lua",
    "docs/STATUS.md",
    "docs/BIZHAWK_TEST_PLAN.md"
)

$downloaded = 0
foreach ($file in $files) {
    $url = "$baseUrl/$file"
    $outPath = Join-Path $targetDir $file
    $outDir = Split-Path $outPath -Parent
    
    if (!(Test-Path $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }
    
    try {
        Invoke-WebRequest -Uri $url -OutFile $outPath -ErrorAction Stop
        Write-Host "  OK: $file" -ForegroundColor Gray
        $downloaded++
    } catch {
        Write-Host "  SKIP: $file" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "Downloaded: $downloaded files" -ForegroundColor Green

#!/usr/bin/env python3
"""Quick project health check — run with: python3 check.py"""

import subprocess, sys, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=" * 50)
print("EMERALD AI — Project Health Check")
print("=" * 50)

# Run tests
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
    capture_output=True, text=True
)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr)
    print("❌ TESTS FAILED")
else:
    print("✅ ALL TESTS PASS")

# Count lines
print("\n📊 Code Stats:")
for d in ["src/", "tests/", "scripts/"]:
    count = 0
    for root, _, files in os.walk(d):
        for f in files:
            if f.endswith(('.py', '.lua')):
                with open(os.path.join(root, f)) as fh:
                    count += sum(1 for _ in fh)
    print(f"  {d:<12} {count:>5} lines")

# List components
print("\n🧩 Components:")
components = {
    "BizHawk Bridge": "scripts/bizhawk/bizhawk_bridge.lua",
    "BizHawk Client": "src/emulator/bizhawk_client.py",
    "Mock Client":    "src/emulator/mock_client.py",
    "Battle Simulator": "src/emulator/battle_simulator.py",
    "State Detector":  "src/games/pokemon_gen3/state_detector.py",
    "Battle Handler":  "src/games/pokemon_gen3/battle_handler.py",
    "Battle AI":       "src/ai/battle_ai.py",
    "Move Database":   "src/data/move_data.py",
    "Species Database":"src/data/species_data.py",
    "Completion Tracker": "src/tracking/completion_tracker.py",
    "Game Loop":       "src/main.py",
}
for name, path in components.items():
    exists = "✅" if os.path.exists(path) else "❌"
    print(f"  {exists} {name:<20} {path}")

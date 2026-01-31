#!/usr/bin/env python3
"""
Proof of Concept: BizHawk Socket Connection

Demonstrates reading live game state from a running BizHawk emulator
via TCP socket communication. This replaces the file-based IPC with
sub-frame latency socket calls.

Usage:
    1. Start this script:    python poc_socket_connection.py
    2. In BizHawk, load:     scripts/bizhawk/bizhawk_socket_bridge.lua
    3. Watch live game state stream to console

The script will:
    - Start a TCP server on port 51055
    - Wait for BizHawk to connect
    - Read game state every 0.5 seconds
    - Display player position, battle state, party info
    - Demonstrate the bulk GETSTATE command
"""

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.emulator.bizhawk_socket_client import BizHawkSocketClient
from src.games.pokemon_gen3.memory_map import PokemonGen3Memory as Mem
from src.data.species_data import get_species_name

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def format_battle_info(state: dict) -> str:
    """Format battle information from bulk state."""
    if state.get("bf", 0) == 0:
        return "  Not in battle"

    lines = []
    bf = state["bf"]

    # Battle type
    types = []
    if bf & 0x0004:
        types.append("WILD")
    if bf & 0x0008:
        types.append("TRAINER")
    if bf & 0x0001:
        types.append("DOUBLE")
    if bf & 0x0080:
        types.append("SAFARI")
    if bf & 0x2000:
        types.append("LEGENDARY")
    lines.append(f"  Battle Type: {' | '.join(types) or 'UNKNOWN'}")

    # Weather
    weather_names = {0: "None", 1: "Rain", 2: "Sandstorm", 3: "Sun", 4: "Hail"}
    weather = state.get("weather", 0)
    lines.append(f"  Weather: {weather_names.get(weather, f'0x{weather:04X}')}")

    # Player Pokemon
    ps = state.get("ps", 0)
    if ps:
        name = get_species_name(ps) or f"#{ps}"
        php = state.get("php", 0)
        pmhp = state.get("pmhp", 0)
        plv = state.get("plv", 0)
        hp_pct = (php / pmhp * 100) if pmhp > 0 else 0
        lines.append(f"  Player: Lv.{plv} {name} ({php}/{pmhp} HP, {hp_pct:.0f}%)")

    # Enemy Pokemon
    es = state.get("es", 0)
    if es:
        name = get_species_name(es) or f"#{es}"
        ehp = state.get("ehp", 0)
        emhp = state.get("emhp", 0)
        elv = state.get("elv", 0)
        hp_pct = (ehp / emhp * 100) if emhp > 0 else 0
        lines.append(f"  Enemy:  Lv.{elv} {name} ({ehp}/{emhp} HP, {hp_pct:.0f}%)")

    return "\n".join(lines)


def main():
    print("=" * 60)
    print("  BizHawk Socket Connection - Proof of Concept")
    print("=" * 60)
    print()
    print("Starting TCP server on 127.0.0.1:51055...")
    print("Now load bizhawk_socket_bridge.lua in BizHawk's Lua Console.")
    print()

    client = BizHawkSocketClient()

    if not client.start_server():
        print("ERROR: Failed to start server")
        return

    print("Waiting for BizHawk to connect (timeout: 60s)...")
    if not client.wait_for_connection(timeout=60):
        print("ERROR: BizHawk did not connect. Make sure the Lua script is loaded.")
        client.close()
        return

    # Verify connection
    print("\nVerifying connection...")
    title = client.get_game_title()
    code = client.get_game_code()
    frame = client.get_frame_count()

    print(f"  Game: {title}")
    print(f"  Code: {code}")
    print(f"  Frame: {frame}")

    if code and code != "BPEE":
        print(f"  WARNING: Expected Emerald (BPEE), got {code}")

    # Performance test
    print("\nRunning latency test (100 PINGs)...")
    start = time.time()
    for _ in range(100):
        client._send_command("PING")
    elapsed = time.time() - start
    avg_ms = (elapsed / 100) * 1000
    print(f"  Average round-trip: {avg_ms:.2f}ms ({100/elapsed:.0f} commands/sec)")

    # Compare bulk vs individual reads
    print("\nComparing bulk GETSTATE vs individual reads...")
    start = time.time()
    for _ in range(50):
        client.get_state()
    bulk_elapsed = time.time() - start
    bulk_avg = (bulk_elapsed / 50) * 1000

    start = time.time()
    for _ in range(50):
        client.read32(Mem.SAVE_BLOCK_1_PTR)
        client.read32(Mem.SAVE_BLOCK_2_PTR)
        client.read32(Mem.BATTLE_TYPE_FLAGS)
        client.read32(Mem.CALLBACK1)
        client.read32(Mem.CALLBACK2)
    individual_elapsed = time.time() - start
    individual_avg = (individual_elapsed / 50) * 1000

    print(f"  Bulk GETSTATE:    {bulk_avg:.2f}ms per call")
    print(f"  5x Individual:    {individual_avg:.2f}ms per call")
    print(f"  Speedup:          {individual_avg/bulk_avg:.1f}x faster with bulk")

    # Live state monitoring loop
    print("\n" + "=" * 60)
    print("  Live Game State Monitor (Ctrl+C to stop)")
    print("=" * 60)

    try:
        tick = 0
        while True:
            tick += 1
            state = client.get_state()

            if not state:
                print("  [Lost connection]")
                break

            # Header
            frame = state.get("frame", 0)
            print(f"\n--- Tick {tick} | Frame {frame} ---")

            # Save block pointers
            sb1 = state.get("sb1", 0)
            sb2 = state.get("sb2", 0)
            if 0x02000000 <= sb1 <= 0x0203FFFF:
                print(f"  Save Blocks: SB1=0x{sb1:08X} SB2=0x{sb2:08X} (valid)")
            else:
                print(f"  Save Blocks: INVALID (title screen?)")

            # Player position
            px = state.get("px", 0)
            py = state.get("py", 0)
            mg = state.get("mg", 0)
            mn = state.get("mn", 0)
            print(f"  Position: ({px}, {py}) on map ({mg}, {mn})")

            # Callbacks (game state indicator)
            cb1 = state.get("cb1", 0)
            cb2 = state.get("cb2", 0)
            if cb1 == 0 and cb2 == 0:
                print(f"  State: TRANSITION (callbacks null)")
            else:
                print(f"  State: ACTIVE (cb1=0x{cb1:08X} cb2=0x{cb2:08X})")

            # Battle info
            print(format_battle_info(state))

            # Read party count (demonstrates individual read still works)
            if 0x02000000 <= sb1 <= 0x0203FFFF:
                party_count = client.read8(sb1 + Mem.PARTY_COUNT_OFFSET)
                print(f"  Party: {party_count} Pokemon")

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\nStopping...")
    finally:
        client.close()
        print("Connection closed.")


if __name__ == "__main__":
    main()

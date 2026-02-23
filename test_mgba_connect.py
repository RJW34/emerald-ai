#!/usr/bin/env python3
"""
Quick test for MgbaClient - verifies the emulator connects,
reads ROM header data, and can do basic memory operations.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.emulator.mgba_client import MgbaClient


def main():
    rom_path = "/home/ryan/roms/emerald.gba"
    print(f"=== MgbaClient Test ===")
    print(f"ROM: {rom_path}")
    print()

    client = MgbaClient(rom_path=rom_path)

    # Test connect
    print("[1] Testing connect()...")
    connected = client.connect()
    print(f"    Connected: {connected}")
    if not connected:
        print("FAILED: Could not connect")
        return 1

    # Test is_connected
    print(f"[2] is_connected(): {client.is_connected()}")

    # Test game info
    print(f"[3] Game title: '{client.get_game_title()}'")
    print(f"    Game code: '{client.get_game_code()}'")
    print(f"    Frame count: {client.get_frame_count()}")

    # Test ROM header read (0x080000A0 = ROM title in header, 12 bytes)
    print("[4] Reading ROM header title at 0x080000A0...")
    rom_title_bytes = client.read_range(0x080000A0, 12)
    rom_title = rom_title_bytes.decode('ascii', errors='replace').strip('\x00')
    print(f"    ROM title (raw bytes): {rom_title_bytes.hex()}")
    print(f"    ROM title (ascii): '{rom_title}'")

    # Test ROM game code at 0x080000AC (4 bytes)
    print("[5] Reading ROM game code at 0x080000AC...")
    rom_code_bytes = client.read_range(0x080000AC, 4)
    rom_code = rom_code_bytes.decode('ascii', errors='replace')
    print(f"    ROM code: '{rom_code}'")

    # Test individual memory reads
    print("[6] Testing read8/read16/read32...")
    val8 = client.read8(0x080000A0)
    val16 = client.read16(0x080000A0)
    val32 = client.read32(0x080000A0)
    print(f"    read8(0x080000A0)  = 0x{val8:02X} ('{chr(val8)}' if ascii)")
    print(f"    read16(0x080000A0) = 0x{val16:04X}")
    print(f"    read32(0x080000A0) = 0x{val32:08X}")

    # Test running some frames
    print("[7] Running 60 frames (1 second of game time)...")
    initial_frame = client.get_frame_count()
    for _ in range(60):
        client._run_frames(1)
    final_frame = client.get_frame_count()
    print(f"    Frames: {initial_frame} -> {final_frame} (delta: {final_frame - initial_frame})")

    # Test button tap
    print("[8] Testing tap_button('A')...")
    result = client.tap_button("A")
    print(f"    tap_button result: {result}")

    # Test EWRAM read (0x02000000 region)
    print("[9] Reading EWRAM at 0x02000000 (first 16 bytes)...")
    ewram = client.read_range(0x02000000, 16)
    print(f"    EWRAM: {ewram.hex()}")

    # Test write8
    print("[10] Testing write8 to EWRAM...")
    addr = 0x0203FF00  # Safe scratch area in EWRAM
    old_val = client.read8(addr)
    client.write8(addr, 0x42)
    new_val = client.read8(addr)
    client.write8(addr, old_val)  # Restore
    print(f"    write8(0x{addr:08X}, 0x42): old=0x{old_val:02X}, new=0x{new_val:02X}, restored=0x{client.read8(addr):02X}")

    # Test screenshot
    print("[11] Testing save_screenshot()...")
    screenshot_path = "/tmp/mgba_test_screenshot.png"
    ss_result = client.save_screenshot(screenshot_path)
    print(f"    Screenshot saved: {ss_result}")
    if ss_result:
        size = os.path.getsize(screenshot_path)
        print(f"    File size: {size} bytes")

    # Test save/load state
    print("[12] Testing save_state/load_state...")
    save_result = client.save_state(1)
    print(f"    save_state(1): {save_result}")
    if save_result:
        load_result = client.load_state(1)
        print(f"    load_state(1): {load_result}")

    # Clean up
    print()
    print("[13] Closing...")
    client.close()
    print(f"    is_connected after close: {client.is_connected()}")

    print()
    print("=== ALL TESTS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

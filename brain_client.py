#!/usr/bin/env python3
"""
Emerald Brain Client — test harness for the Lua-native mGBA bridge.

Connects to the TCP server running inside mGBA (port 8785) and
sends JSON-line commands. This is the test client; the real brain
will live on MAGNETON and call this remotely.

Usage:
    python3 brain_client.py                  # run full test suite
    python3 brain_client.py --host 127.0.0.1 # specify host
    python3 brain_client.py --loop           # continuous state polling
"""

import argparse
import json
import socket
import sys
import time


class EmeraldBridge:
    """TCP client for the mGBA Lua bridge."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8785, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.recv_buffer = ""

    def connect(self) -> bool:
        """Connect to the Lua bridge. Returns True on success."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.host, self.port))
            print(f"[+] Connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"[-] Connection failed: {e}")
            self.sock = None
            return False

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send_command(self, cmd: dict, timeout: float | None = None) -> dict | None:
        """Send a JSON command and wait for the response line."""
        if not self.sock:
            print("[-] Not connected")
            return None

        try:
            # Send JSON + newline
            payload = json.dumps(cmd, separators=(",", ":")) + "\n"
            self.sock.sendall(payload.encode("utf-8"))

            # Read response (newline-terminated JSON)
            old_timeout = self.sock.gettimeout()
            if timeout is not None:
                self.sock.settimeout(timeout)

            while "\n" not in self.recv_buffer:
                chunk = self.sock.recv(8192)
                if not chunk:
                    print("[-] Connection closed by server")
                    self.sock = None
                    return None
                self.recv_buffer += chunk.decode("utf-8", errors="replace")

            if timeout is not None:
                self.sock.settimeout(old_timeout)

            # Extract first complete line
            newline_idx = self.recv_buffer.index("\n")
            line = self.recv_buffer[:newline_idx]
            self.recv_buffer = self.recv_buffer[newline_idx + 1:]

            return json.loads(line)

        except socket.timeout:
            print("[-] Timeout waiting for response")
            return None
        except Exception as e:
            print(f"[-] Error: {e}")
            self.close()
            return None

    # ── Convenience methods ──────────────────────────────────

    def ping(self) -> dict | None:
        return self.send_command({"cmd": "ping"})

    def get_state(self) -> dict | None:
        return self.send_command({"cmd": "state"})

    def press(self, key: str, frames: int = 6) -> dict | None:
        return self.send_command({"cmd": "press", "key": key, "frames": frames})

    def screenshot(self, path: str = "/tmp/emerald_screen.png") -> dict | None:
        return self.send_command({"cmd": "screenshot", "path": path})

    def read_mem(self, addr: int, size: int = 8) -> dict | None:
        cmd = "read8" if size <= 8 else ("read16" if size <= 16 else "read32")
        return self.send_command({"cmd": cmd, "addr": addr})


def format_state(state: dict) -> str:
    """Pretty-print a game state response."""
    lines = []
    lines.append(f"  Scene: {state.get('scene', '?')}")
    lines.append(f"  Frame: {state.get('frame', '?')}")

    name = state.get("player_name")
    if name:
        lines.append(f"  Player: {name}")
    
    if "pos_x" in state:
        lines.append(f"  Position: ({state['pos_x']}, {state['pos_y']}) map {state.get('map_group','?')}.{state.get('map_num','?')}")

    if "play_hours" in state:
        lines.append(f"  Play time: {state['play_hours']}h {state['play_minutes']}m {state['play_seconds']}s")

    if "badge_count" in state:
        lines.append(f"  Badges: {state['badge_count']}/8")

    if "money" in state:
        lines.append(f"  Money: ${state['money']}")

    party = state.get("party", [])
    if party:
        lines.append(f"  Party ({state.get('party_count', len(party))}):")
        for i, mon in enumerate(party):
            species = mon.get("species", "?")
            nick = mon.get("nickname", "?")
            level = mon.get("level", "?")
            hp = mon.get("hp", "?")
            max_hp = mon.get("max_hp", "?")
            lines.append(f"    [{i+1}] {nick} (sp:{species}) Lv{level}  HP: {hp}/{max_hp}")

    if state.get("error"):
        lines.append(f"  ⚠ Error: {state['error']}")

    return "\n".join(lines)


def run_test_suite(bridge: EmeraldBridge):
    """Run a basic test of all commands."""
    print("\n=== Emerald Brain Client — Test Suite ===\n")

    # 1. Ping
    print("[TEST] Ping...")
    resp = bridge.ping()
    if resp and resp.get("ok"):
        print(f"  ✓ Pong! Frame: {resp.get('frame', '?')}")
    else:
        print(f"  ✗ Ping failed: {resp}")
        return

    # 2. State
    print("\n[TEST] Game state...")
    state = bridge.get_state()
    if state:
        print(format_state(state))
    else:
        print("  ✗ No state returned")

    # 3. Screenshot
    print("\n[TEST] Screenshot...")
    resp = bridge.screenshot("/tmp/emerald_brain_test.png")
    if resp and resp.get("ok"):
        print(f"  ✓ Saved to {resp.get('path')}")
    else:
        print(f"  ✗ Screenshot failed: {resp}")

    # 4. Press A
    print("\n[TEST] Press A (6 frames)...")
    resp = bridge.press("A", 6)
    if resp and resp.get("ok"):
        print(f"  ✓ Queued. Queue length: {resp.get('queue_len')}")
    else:
        print(f"  ✗ Press failed: {resp}")

    # 5. Wait and re-read state to see if press took effect
    time.sleep(0.5)
    print("\n[TEST] State after A press...")
    state = bridge.get_state()
    if state:
        print(format_state(state))

    print("\n=== Tests complete ===\n")


def run_loop(bridge: EmeraldBridge, interval: float = 1.0):
    """Continuously poll state and print it."""
    print("\n=== Continuous State Polling (Ctrl+C to stop) ===\n")
    try:
        while True:
            state = bridge.get_state()
            if state:
                ts = time.strftime("%H:%M:%S")
                scene = state.get("scene", "?")
                frame = state.get("frame", "?")
                name = state.get("player_name", "")
                pos = ""
                if "pos_x" in state:
                    pos = f" pos=({state['pos_x']},{state['pos_y']})"
                party_str = ""
                if state.get("party_count", 0) > 0:
                    party_str = f" party={state['party_count']}"
                print(f"[{ts}] frame={frame} scene={scene} player={name}{pos}{party_str} badges={state.get('badge_count', 0)}")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] No response (disconnected?)")
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    parser = argparse.ArgumentParser(description="Emerald Brain Client")
    parser.add_argument("--host", default="127.0.0.1", help="Lua bridge host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8785, help="Lua bridge port (default: 8785)")
    parser.add_argument("--loop", action="store_true", help="Continuous state polling mode")
    parser.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds (with --loop)")
    args = parser.parse_args()

    bridge = EmeraldBridge(host=args.host, port=args.port)
    if not bridge.connect():
        sys.exit(1)

    try:
        if args.loop:
            run_loop(bridge, args.interval)
        else:
            run_test_suite(bridge)
    finally:
        bridge.close()


if __name__ == "__main__":
    main()

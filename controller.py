#!/usr/bin/env python3
"""
Emerald Controller — Python client for the mGBA Lua bridge.

Connects to the TCP socket server running inside mGBA (port 8779)
and provides high-level methods for controlling the game.

Usage:
    from controller import EmeraldController
    ctrl = EmeraldController()
    ctrl.connect()
    ctrl.press("A")
    ctrl.walk("Up", 5)
    state = ctrl.get_state()
"""

from __future__ import annotations

import json
import logging
import socket
import time
from typing import Optional

log = logging.getLogger("emerald-controller")

# GBA runs at ~59.7275 FPS
GBA_FPS = 59.7275
FRAME_DURATION = 1.0 / GBA_FPS  # ~16.74ms


class EmeraldController:
    """High-level controller for Pokemon Emerald via the mGBA Lua bridge."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8779, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.recv_buffer = ""
        self._connected = False

    def connect(self) -> bool:
        """Connect to the Lua bridge. Returns True on success."""
        try:
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass

            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.host, self.port))
            self.recv_buffer = ""
            self._connected = True
            log.info(f"Connected to mGBA bridge at {self.host}:{self.port}")
            return True
        except Exception as e:
            log.warning(f"Connection failed: {e}")
            self.sock = None
            self._connected = False
            return False

    def disconnect(self):
        """Close the connection."""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        self._connected = False

    def is_connected(self) -> bool:
        """Check if connected to the bridge."""
        return self._connected and self.sock is not None

    def _reconnect(self) -> bool:
        """Attempt to reconnect if disconnected."""
        if self.is_connected():
            return True
        log.info("Attempting reconnection...")
        return self.connect()

    def _send_command(self, cmd: dict, timeout: Optional[float] = None) -> Optional[dict]:
        """Send a JSON command and read the response. Auto-reconnects on failure."""
        if not self._reconnect():
            return None

        try:
            payload = json.dumps(cmd, separators=(",", ":")) + "\n"
            self.sock.sendall(payload.encode("utf-8"))

            old_timeout = self.sock.gettimeout()
            if timeout is not None:
                self.sock.settimeout(timeout)

            while "\n" not in self.recv_buffer:
                chunk = self.sock.recv(8192)
                if not chunk:
                    log.warning("Connection closed by bridge")
                    self._connected = False
                    self.sock = None
                    return None
                self.recv_buffer += chunk.decode("utf-8", errors="replace")

            if timeout is not None:
                self.sock.settimeout(old_timeout)

            nl = self.recv_buffer.index("\n")
            line = self.recv_buffer[:nl]
            self.recv_buffer = self.recv_buffer[nl + 1:]

            return json.loads(line)

        except socket.timeout:
            log.warning("Timeout waiting for response")
            return None
        except (ConnectionError, BrokenPipeError, OSError) as e:
            log.warning(f"Connection error: {e}")
            self._connected = False
            self.sock = None
            return None

    # ── Core actions ─────────────────────────────────────────

    def ping(self) -> Optional[dict]:
        """Test connection to the bridge."""
        return self._send_command({"action": "ping"})

    def health_check(self) -> bool:
        """Returns True if the bridge is responding."""
        resp = self.ping()
        return resp is not None and resp.get("ok", False)

    def get_state(self) -> Optional[dict]:
        """Read full game state from mGBA memory."""
        return self._send_command({"action": "state"})

    def press(self, button: str, frames: int = 6) -> Optional[dict]:
        """Press a button for N frames (default 6 = ~100ms).

        Args:
            button: A, B, Start, Select, Up, Down, Left, Right, L, R
            frames: How many frames to hold (6 ≈ 100ms, 1 frame ≈ 16.7ms)
        """
        return self._send_command({
            "action": "press",
            "button": button,
            "frames": frames,
        })

    def hold(self, button: str, frames: Optional[int] = None) -> Optional[dict]:
        """Hold a button for N frames, or indefinitely if frames is None.

        Args:
            button: A, B, Start, Select, Up, Down, Left, Right, L, R
            frames: Frame count (None = hold until release() is called)
        """
        cmd = {"action": "hold", "button": button}
        if frames is not None:
            cmd["frames"] = frames
        return self._send_command(cmd)

    def release(self, button: str) -> Optional[dict]:
        """Release a held button."""
        return self._send_command({"action": "release", "button": button})

    def screenshot(self, path: str = "/tmp/emerald_screen.png") -> Optional[dict]:
        """Save a screenshot from mGBA."""
        return self._send_command({"action": "screenshot", "path": path})

    def input_state(self) -> Optional[dict]:
        """Get the current input queue status."""
        return self._send_command({"action": "input_state"})

    # ── High-level helpers ───────────────────────────────────

    def walk(self, direction: str, steps: int = 1, frames_per_step: int = 16) -> bool:
        """Walk in a direction for N steps.

        Each step is ~16 frames of holding a direction key.
        In Pokemon Emerald overworld, one tile = ~16 frames of walking.

        Args:
            direction: Up, Down, Left, Right
            steps: Number of tiles to walk
            frames_per_step: Frames per step (16 = standard walk speed)
        """
        direction = direction.capitalize()
        if direction not in ("Up", "Down", "Left", "Right"):
            log.error(f"Invalid direction: {direction}")
            return False

        for step in range(steps):
            resp = self.hold(direction, frames=frames_per_step)
            if resp is None or resp.get("error"):
                log.error(f"Walk failed at step {step + 1}: {resp}")
                return False
            # Wait for the frames to play out
            time.sleep(frames_per_step * FRAME_DURATION + 0.02)

        return True

    def mash_a(self, count: int = 5, delay_frames: int = 10) -> bool:
        """Rapidly press A multiple times (good for text/dialog).

        Args:
            count: Number of A presses
            delay_frames: Frames between presses (10 ≈ 167ms)
        """
        for i in range(count):
            resp = self.press("A", frames=4)
            if resp is None or resp.get("error"):
                log.error(f"Mash A failed at press {i + 1}: {resp}")
                return False
            time.sleep(delay_frames * FRAME_DURATION)
        return True

    def press_sequence(self, buttons: list[str], delay_frames: int = 10) -> bool:
        """Press a sequence of buttons with delay between each.

        Args:
            buttons: List of button names, e.g. ["A", "Up", "Up", "A"]
            delay_frames: Frames between presses
        """
        for i, button in enumerate(buttons):
            resp = self.press(button, frames=6)
            if resp is None or resp.get("error"):
                log.error(f"Sequence failed at button {i + 1} ({button}): {resp}")
                return False
            time.sleep(delay_frames * FRAME_DURATION)
        return True

    def wait_frames(self, frames: int):
        """Wait for a given number of frames to pass."""
        time.sleep(frames * FRAME_DURATION)


# ── CLI test mode ────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    ctrl = EmeraldController()
    if not ctrl.connect():
        print("Failed to connect to mGBA bridge on port 8779")
        print("Make sure the Lua script is loaded in mGBA first!")
        sys.exit(1)

    print("\n=== Emerald Controller Test ===\n")

    # Ping
    print("[1] Ping...")
    resp = ctrl.ping()
    if resp and resp.get("ok"):
        print(f"    ✓ Connected! Frame: {resp.get('frame', '?')}")
    else:
        print(f"    ✗ Ping failed: {resp}")
        sys.exit(1)

    # State
    print("\n[2] Game state...")
    state = ctrl.get_state()
    if state:
        scene = state.get("scene", "?")
        name = state.get("player_name", "?")
        loc = state.get("location", "?")
        pos = f"({state.get('pos_x', '?')}, {state.get('pos_y', '?')})"
        badges = state.get("badge_count", 0)
        party_count = state.get("party_count", 0)
        print(f"    Scene: {scene}")
        print(f"    Player: {name}")
        print(f"    Location: {loc} {pos}")
        print(f"    Badges: {badges}/8")
        print(f"    Party: {party_count} Pokemon")
        if state.get("party"):
            for i, mon in enumerate(state["party"]):
                sp = mon.get("species", f"#{mon.get('species_id', '?')}")
                print(f"      [{i+1}] {mon.get('nickname', '?')} ({sp}) Lv{mon.get('level', '?')} HP:{mon.get('hp', '?')}/{mon.get('max_hp', '?')}")
    else:
        print("    ✗ No state returned")

    # Health check
    print(f"\n[3] Health check: {'✓ PASS' if ctrl.health_check() else '✗ FAIL'}")

    print("\n=== Test complete ===")
    ctrl.disconnect()

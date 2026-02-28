#!/usr/bin/env python3
"""
mGBA xdotool Controller

Sends button presses to a running mGBA instance via xdotool.
Also provides game state polling via the game_state_server HTTP API.

mGBA default keybindings:
  A=X, B=Z, Start=Enter, Select=Backspace,
  D-pad=Arrow keys, L=A, R=S
"""

import json
import os
import subprocess
import time
import urllib.request
import urllib.error
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Window ID for the running mGBA instance — auto-detected if not set
WINDOW_ID: Optional[int] = None

# mGBA default key mappings (GBA button -> X11 key name)
KEY_MAP = {
    "a": "x",
    "b": "z",
    "start": "Return",
    "select": "BackSpace",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "l": "a",
    "r": "s",
}

GAME_STATE_URL = "http://localhost:8776/state"
XDOTOOL_ENV = {**os.environ, "DISPLAY": ":0"}


def _find_mgba_window() -> int:
    """Auto-detect the mGBA main window ID via xdotool (or MGBA_WINDOW_ID env var)."""
    env_wid = os.environ.get("MGBA_WINDOW_ID")
    if env_wid:
        return int(env_wid)
    result = subprocess.run(
        ["xdotool", "search", "--name", "mGBA - Pokemon"],
        capture_output=True, text=True, env=XDOTOOL_ENV,
    )
    if result.returncode == 0 and result.stdout.strip():
        wid = int(result.stdout.strip().splitlines()[0])
        return wid
    # Fallback: search by class
    result = subprocess.run(
        ["xdotool", "search", "--class", "mgba-qt"],
        capture_output=True, text=True, env=XDOTOOL_ENV,
    )
    if result.returncode == 0 and result.stdout.strip():
        wid = int(result.stdout.strip().splitlines()[0])
        return wid
    raise RuntimeError("Could not find mGBA window")


class MGBAController:
    """Send GBA inputs to a running mGBA via xdotool."""

    def __init__(self, window_id: Optional[int] = None):
        self.window_id = window_id or WINDOW_ID or _find_mgba_window()
        self._env = XDOTOOL_ENV

    # ---- low-level ----

    def _send_key(self, x11_key: str):
        """Send a single key press event to the mGBA window."""
        subprocess.run(
            ["xdotool", "windowactivate", "--sync", str(self.window_id)],
            env=self._env,
            timeout=5,
        )
        subprocess.run(
            ["xdotool", "key", x11_key],
            env=self._env,
            timeout=5,
        )

    def _send_keydown(self, x11_key: str):
        subprocess.run(
            ["xdotool", "windowactivate", "--sync", str(self.window_id)],
            env=self._env,
            timeout=5,
        )
        subprocess.run(
            ["xdotool", "keydown", x11_key],
            env=self._env,
            timeout=5,
        )

    def _send_keyup(self, x11_key: str):
        subprocess.run(
            ["xdotool", "windowactivate", "--sync", str(self.window_id)],
            env=self._env,
            timeout=5,
        )
        subprocess.run(
            ["xdotool", "keyup", x11_key],
            env=self._env,
            timeout=5,
        )

    # ---- button methods ----

    def press_a(self):
        self._send_key(KEY_MAP["a"])

    def press_b(self):
        self._send_key(KEY_MAP["b"])

    def press_start(self):
        self._send_key(KEY_MAP["start"])

    def press_select(self):
        self._send_key(KEY_MAP["select"])

    def dpad_up(self):
        self._send_key(KEY_MAP["up"])

    def dpad_down(self):
        self._send_key(KEY_MAP["down"])

    def dpad_left(self):
        self._send_key(KEY_MAP["left"])

    def dpad_right(self):
        self._send_key(KEY_MAP["right"])

    def press_l(self):
        self._send_key(KEY_MAP["l"])

    def press_r(self):
        self._send_key(KEY_MAP["r"])

    # ---- combo helpers ----

    def press_and_hold(self, button: str, ms: int):
        """Hold a GBA button for `ms` milliseconds."""
        x11_key = KEY_MAP.get(button)
        if not x11_key:
            raise ValueError(f"Unknown button: {button}")
        self._send_keydown(x11_key)
        time.sleep(ms / 1000.0)
        self._send_keyup(x11_key)

    def sequence(self, buttons: list[str], delay_ms: int = 100):
        """Press a sequence of GBA buttons with a delay between each."""
        for btn in buttons:
            x11_key = KEY_MAP.get(btn)
            if not x11_key:
                raise ValueError(f"Unknown button: {btn}")
            self._send_key(x11_key)
            time.sleep(delay_ms / 1000.0)

    def press_button(self, button: str):
        """Press a GBA button by name (a, b, start, select, up, down, left, right, l, r)."""
        x11_key = KEY_MAP.get(button)
        if not x11_key:
            raise ValueError(f"Unknown button: {button}")
        self._send_key(x11_key)

    # ---- game state ----

    @staticmethod
    def get_game_state() -> dict:
        """Fetch current game state from the game state server."""
        try:
            req = urllib.request.Request(GAME_STATE_URL, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
            return {"status": "error", "error": str(e)}

    def wait_for_state_change(self, field: str, timeout_s: float = 5.0) -> Optional[dict]:
        """
        Poll game state until `field` changes from its current value.
        Returns the new state, or None on timeout.
        """
        initial = self.get_game_state()
        initial_val = initial.get(field)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            time.sleep(0.2)
            state = self.get_game_state()
            if state.get(field) != initial_val:
                return state
        return None


if __name__ == "__main__":
    ctrl = MGBAController()
    print(f"Connected to mGBA window {ctrl.window_id}")
    state = ctrl.get_game_state()
    print(f"Game state: {json.dumps(state, indent=2)}")
    print("Pressing A...")
    ctrl.press_a()
    print("Done.")

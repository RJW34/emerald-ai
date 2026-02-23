"""
MgbaClient — embedded mGBA emulator via mgba-python.

Does NOT call autoload_save() — state is loaded explicitly via load_state_file()
so we can drop straight into an existing save (e.g., Route 101 slot 1).
"""

import logging
from pathlib import Path
from typing import Optional

import mgba.core
import mgba.image
from mgba.gba import GBA

log = logging.getLogger(__name__)

_BUTTON_MAP = {
    "A": GBA.KEY_A,
    "B": GBA.KEY_B,
    "Start": GBA.KEY_START,
    "Select": GBA.KEY_SELECT,
    "Up": GBA.KEY_UP,
    "Down": GBA.KEY_DOWN,
    "Left": GBA.KEY_LEFT,
    "Right": GBA.KEY_RIGHT,
    "L": GBA.KEY_L,
    "R": GBA.KEY_R,
}


class MgbaClient:
    def __init__(self, rom_path: str):
        self.rom_path = rom_path
        self._core: Optional[GBA] = None
        self._screen = None
        self._ok = False

    def connect(self) -> bool:
        try:
            if not Path(self.rom_path).exists():
                log.error(f"ROM not found: {self.rom_path}")
                return False
            self._core = mgba.core.load_path(self.rom_path)
            if not self._core:
                log.error("mgba.core.load_path returned None")
                return False
            w, h = self._core.desired_video_dimensions()
            self._screen = mgba.image.Image(w, h)
            self._core.set_video_buffer(self._screen)
            # NOTE: no autoload_save() — fresh boot every time
            self._core.reset()
            self._ok = True
            log.info(f"mGBA ready: {self._core.game_title} ({self.game_code})")
            return True
        except Exception as e:
            log.error(f"connect failed: {e}")
            return False

    @property
    def game_code(self) -> str:
        if not self._ok:
            return ""
        try:
            c = self._core.game_code.strip("\x00").strip()
            return c[4:] if c.startswith("AGB-") else c
        except Exception:
            return ""

    # ── frames ────────────────────────────────────────────────────────────────

    def run(self, n: int = 1):
        """Advance n frames."""
        for _ in range(n):
            self._core.run_frame()

    # ── input ─────────────────────────────────────────────────────────────────

    def tap(self, button: str, hold: int = 2, gap: int = 2):
        """Press and release a button."""
        key = _BUTTON_MAP[button]
        self._core.set_keys(raw=1 << key)
        self.run(hold)
        self._core.set_keys(raw=0)
        self.run(gap)

    def hold(self, button: str, frames: int):
        """Hold a button for exactly `frames` frames."""
        key = _BUTTON_MAP[button]
        self._core.set_keys(raw=1 << key)
        self.run(frames)
        self._core.set_keys(raw=0)
        self.run(2)

    # ── memory ────────────────────────────────────────────────────────────────

    def r8(self, addr: int) -> int:
        try:
            return self._core.memory.u8[addr]
        except Exception:
            return 0

    def r16(self, addr: int) -> int:
        try:
            return self._core.memory.u16[addr]
        except Exception:
            return 0

    def r32(self, addr: int) -> int:
        try:
            return self._core.memory.u32[addr]
        except Exception:
            return 0

    def w8(self, addr: int, val: int) -> bool:
        try:
            self._core.memory.u8[addr] = val & 0xFF
            return True
        except Exception as e:
            log.error(f"w8 @ 0x{addr:08X}: {e}")
            return False

    def w16(self, addr: int, val: int) -> bool:
        try:
            self._core.memory.u16[addr] = val & 0xFFFF
            return True
        except Exception as e:
            log.error(f"w16 @ 0x{addr:08X}: {e}")
            return False

    # ── screenshot ────────────────────────────────────────────────────────────

    def screenshot(self, path: str) -> bool:
        if not self._ok or not self._screen:
            return False
        try:
            with open(path, "wb") as f:
                return bool(self._screen.save_png(f))
        except Exception as e:
            log.error(f"screenshot failed: {e}")
            return False

    def load_state_file(self, path: str) -> bool:
        """Load a .state file directly, dropping the game to that point.

        mgba-python exposes load_raw_state(bytes) — reads the raw mGBA
        save-state blob.  Older method names (load_state / load_state_file)
        do not exist in the installed version.
        """
        if not self._ok:
            return False
        try:
            with open(path, "rb") as f:
                data = f.read()
            ok = self._core.load_raw_state(data)
            if ok:
                log.info(f"Save state loaded: {path}")
                return True
            log.error(f"load_raw_state returned False for {path}")
        except Exception as e:
            log.error(f"load_state_file failed: {e}")
        return False

    def close(self):
        self._core = None
        self._screen = None
        self._ok = False

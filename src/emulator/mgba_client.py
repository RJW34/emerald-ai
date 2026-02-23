"""
mGBA Client - Embedded mGBA emulator interface via mgba-python.

This module provides a Python interface to mGBA using the official
mgba-python bindings (built from mGBA source, CFFI-based).
It implements the same API as BizHawkClient for drop-in replacement.

Prerequisites:
    1. libmgba shared library installed (libmgba0.10 package)
    2. mgba Python module built from source and installed in venv
    3. A GBA ROM file (e.g., Pokemon Emerald)
"""

import logging
import struct
from pathlib import Path
from typing import Optional

import mgba.core
import mgba.image
from mgba.gba import GBA

logger = logging.getLogger(__name__)


class MgbaClient:
    """Embedded mGBA emulator client using mgba-python bindings."""

    # Valid button names for GBA
    VALID_BUTTONS = {"A", "B", "Start", "Select", "Up", "Down", "Left", "Right", "L", "R"}

    # Button name to GBA key constant mapping
    _BUTTON_MAP = {
        "A": GBA.KEY_A,
        "B": GBA.KEY_B,
        "Select": GBA.KEY_SELECT,
        "Start": GBA.KEY_START,
        "Right": GBA.KEY_RIGHT,
        "Left": GBA.KEY_LEFT,
        "Up": GBA.KEY_UP,
        "Down": GBA.KEY_DOWN,
        "R": GBA.KEY_R,
        "L": GBA.KEY_L,
    }

    def __init__(self, rom_path: str, save_path: Optional[str] = None):
        """
        Initialize the mGBA client.

        Args:
            rom_path: Path to the GBA ROM file.
            save_path: Optional path to save file. If None, uses ROM path with .sav extension.
        """
        self.rom_path = str(rom_path)
        self.save_path = save_path
        self._core: Optional[GBA] = None
        self._screen = None
        self._connected = False
        self._frame_count = 0

    def connect(self) -> bool:
        """
        Load the ROM and initialize the emulator core.

        Returns:
            True if connection (ROM load + reset) successful.
        """
        try:
            rom = Path(self.rom_path)
            if not rom.exists():
                logger.error(f"ROM not found: {self.rom_path}")
                return False

            self._core = mgba.core.load_path(self.rom_path)
            if self._core is None:
                logger.error(f"Failed to load ROM: {self.rom_path}")
                return False

            # Set up video buffer for screenshots
            width, height = self._core.desired_video_dimensions()
            self._screen = mgba.image.Image(width, height)
            self._core.set_video_buffer(self._screen)

            # Auto-load save file if it exists
            self._core.autoload_save()

            # Reset the core (required before any operations)
            self._core.reset()

            self._connected = True
            self._frame_count = 0

            title = self.get_game_title()
            code = self.get_game_code()
            logger.info(f"Connected to mGBA: {title} ({code})")
            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._connected = False
            return False

    def is_connected(self) -> bool:
        """Check if the emulator core is loaded and ready."""
        return self._connected and self._core is not None

    def close(self) -> None:
        """Clean up the emulator core."""
        if self._core is not None:
            try:
                self._core = None
            except Exception:
                pass
        self._connected = False
        self._screen = None

    # -------------------------------------------------------------------------
    # Memory Read Methods
    # -------------------------------------------------------------------------

    def read8(self, address: int) -> int:
        """Read a single byte from memory."""
        if not self.is_connected():
            return 0
        try:
            return self._core.memory.u8[address]
        except (IndexError, Exception) as e:
            logger.debug(f"read8 failed at 0x{address:08X}: {e}")
            return 0

    def read16(self, address: int) -> int:
        """Read 2 bytes from memory (little-endian)."""
        if not self.is_connected():
            return 0
        try:
            return self._core.memory.u16[address]
        except (IndexError, Exception) as e:
            logger.debug(f"read16 failed at 0x{address:08X}: {e}")
            return 0

    def read32(self, address: int) -> int:
        """Read 4 bytes from memory (little-endian)."""
        if not self.is_connected():
            return 0
        try:
            return self._core.memory.u32[address]
        except (IndexError, Exception) as e:
            logger.debug(f"read32 failed at 0x{address:08X}: {e}")
            return 0

    def read_range(self, address: int, length: int) -> bytes:
        """Read a range of bytes from memory."""
        if not self.is_connected():
            return bytes(length)
        try:
            return bytes(self._core.memory[address:address + length])
        except (IndexError, Exception) as e:
            logger.debug(f"read_range failed at 0x{address:08X} len={length}: {e}")
            return bytes(length)

    def write8(self, address: int, value: int) -> bool:
        """Write a single byte to memory."""
        if not self.is_connected():
            return False
        try:
            self._core.memory.u8[address] = value & 0xFF
            return True
        except (IndexError, Exception) as e:
            logger.error(f"write8 failed at 0x{address:08X}: {e}")
            return False

    # -------------------------------------------------------------------------
    # Button Input Methods
    # -------------------------------------------------------------------------

    def _run_frames(self, n: int = 1):
        """Advance the emulator by n frames."""
        for _ in range(n):
            self._core.run_frame()
            self._frame_count += 1

    def tap_button(self, button: str) -> bool:
        """Press and release a button (single frame tap)."""
        if button not in self.VALID_BUTTONS:
            raise ValueError(f"Invalid button: {button}. Valid: {self.VALID_BUTTONS}")
        if not self.is_connected():
            return False
        try:
            key = self._BUTTON_MAP[button]
            self._core.set_keys(raw=1 << key)
            self._run_frames(1)
            self._core.set_keys(raw=0)
            self._run_frames(1)
            return True
        except Exception as e:
            logger.error(f"tap_button failed for {button}: {e}")
            return False

    def hold_button(self, button: str, frames: int) -> bool:
        """Hold a button for a specified number of frames."""
        if button not in self.VALID_BUTTONS:
            raise ValueError(f"Invalid button: {button}. Valid: {self.VALID_BUTTONS}")
        if not self.is_connected():
            return False
        try:
            key = self._BUTTON_MAP[button]
            self._core.set_keys(raw=1 << key)
            self._run_frames(frames)
            self._core.set_keys(raw=0)
            self._run_frames(1)
            return True
        except Exception as e:
            logger.error(f"hold_button failed for {button}: {e}")
            return False

    def press_buttons(self, buttons: list[str], frames: int = 1) -> bool:
        """Press multiple buttons simultaneously for a number of frames."""
        for button in buttons:
            if button not in self.VALID_BUTTONS:
                raise ValueError(f"Invalid button: {button}. Valid: {self.VALID_BUTTONS}")
        if not self.is_connected():
            return False
        try:
            mask = 0
            for button in buttons:
                key = self._BUTTON_MAP[button]
                mask |= (1 << key)
            self._core.set_keys(raw=mask)
            self._run_frames(frames)
            self._core.set_keys(raw=0)
            self._run_frames(1)
            return True
        except Exception as e:
            logger.error(f"press_buttons failed: {e}")
            return False

    # -------------------------------------------------------------------------
    # Screenshot Methods
    # -------------------------------------------------------------------------

    def save_screenshot(self, filepath: str) -> bool:
        """Capture and save the current frame to a PNG file."""
        if not self.is_connected() or self._screen is None:
            return False
        try:
            # Run a frame to ensure the screen buffer is current
            self._core.run_frame()
            self._frame_count += 1

            with open(filepath, "wb") as f:
                success = self._screen.save_png(f)
            if success:
                logger.info(f"Screenshot saved to: {filepath}")
            return success
        except Exception as e:
            logger.error(f"save_screenshot failed: {e}")
            return False

    # -------------------------------------------------------------------------
    # State Management Methods
    # -------------------------------------------------------------------------

    def save_state(self, slot: int) -> bool:
        """Save current state to a raw state buffer (slot 1-10)."""
        if not 1 <= slot <= 10:
            raise ValueError(f"Slot must be 1-10, got {slot}")
        if not self.is_connected():
            return False
        try:
            state = self._core.save_raw_state()
            if state is None:
                logger.error("Failed to save state")
                return False
            state_dir = Path(self.rom_path).parent / "states"
            state_dir.mkdir(exist_ok=True)
            state_path = state_dir / f"emerald_slot{slot}.state"
            with open(str(state_path), "wb") as f:
                f.write(bytes(state))
            logger.info(f"State saved to slot {slot}: {state_path}")
            return True
        except Exception as e:
            logger.error(f"save_state failed for slot {slot}: {e}")
            return False

    def load_state(self, slot: int) -> bool:
        """Load state from a raw state file (slot 1-10)."""
        if not 1 <= slot <= 10:
            raise ValueError(f"Slot must be 1-10, got {slot}")
        if not self.is_connected():
            return False
        try:
            state_path = Path(self.rom_path).parent / "states" / f"emerald_slot{slot}.state"
            if not state_path.exists():
                logger.error(f"No state file for slot {slot}: {state_path}")
                return False
            with open(str(state_path), "rb") as f:
                state_data = f.read()
            success = self._core.load_raw_state(state_data)
            if success:
                logger.info(f"State loaded from slot {slot}")
            return success
        except Exception as e:
            logger.error(f"load_state failed for slot {slot}: {e}")
            return False

    # -------------------------------------------------------------------------
    # Game Info Methods
    # -------------------------------------------------------------------------

    def get_game_title(self) -> str:
        """Get the title of the currently loaded ROM."""
        if not self.is_connected():
            return ""
        try:
            return self._core.game_title.strip('\x00').strip()
        except Exception:
            return ""

    def get_game_code(self) -> str:
        """Get the game code (e.g., BPEE for Emerald)."""
        if not self.is_connected():
            return ""
        try:
            code = self._core.game_code.strip('\x00').strip()
            # mGBA returns "AGB-BPEE", extract just "BPEE" for compatibility
            if code.startswith("AGB-"):
                code = code[4:]
            return code
        except Exception:
            return ""

    def get_frame_count(self) -> int:
        """Get current emulator frame count."""
        if not self.is_connected():
            return 0
        try:
            return self._core.frame_counter
        except Exception:
            return self._frame_count

    # -------------------------------------------------------------------------
    # Context Manager Support
    # -------------------------------------------------------------------------

    def __enter__(self) -> "MgbaClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

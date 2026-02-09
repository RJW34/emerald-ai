"""
BizHawk Client - File-based IPC communication with BizHawk emulator.

This module provides a Python interface to BizHawk via file-based IPC.
The companion Lua script reads commands from command.txt and writes
responses to response.txt.

Prerequisites:
    1. BizHawk running with a GBA ROM loaded
    2. The companion Lua script (bizhawk_bridge.lua) loaded via Tools → Lua Console
"""

import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default IPC directory (same as Lua script location)
# Resolves to: emerald-ai/scripts/bizhawk/
DEFAULT_IPC_DIR = Path(os.environ.get("BIZHAWK_IPC_DIR", str(Path(__file__).resolve().parent.parent.parent / "scripts" / "bizhawk")))


class BizHawkClient:
    """File-based IPC client for communicating with BizHawk via Lua bridge."""

    # Valid button names for GBA
    VALID_BUTTONS = {"A", "B", "Start", "Select", "Up", "Down", "Left", "Right", "L", "R"}

    def __init__(
        self,
        ipc_dir: Optional[Path] = None,
        timeout: float = 5.0,
        poll_interval: float = 0.016,  # ~60fps
    ):
        """
        Initialize the BizHawk client.

        Args:
            ipc_dir: Directory containing command.txt and response.txt
            timeout: Maximum time to wait for response in seconds
            poll_interval: How often to check for response
        """
        self.ipc_dir = Path(ipc_dir) if ipc_dir else DEFAULT_IPC_DIR
        self.timeout = timeout
        self.poll_interval = poll_interval

        self.command_file = self.ipc_dir / "command.txt"
        self.response_file = self.ipc_dir / "response.txt"
        self.lock_file = self.ipc_dir / "lock.txt"

    def connect(self) -> bool:
        """
        Test connection to BizHawk by sending a PING command.

        Returns:
            True if connection successful
        """
        try:
            response = self._send_command("PING")
            if response and "PONG" in response:
                logger.info("Connected to BizHawk via file IPC")
                return True
            logger.error(f"Unexpected PING response: {response}")
            return False
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    def is_connected(self) -> bool:
        """Check if connected to BizHawk."""
        try:
            response = self._send_command("PING")
            return response is not None and "PONG" in response
        except:
            return False

    def _send_command(self, command: str) -> Optional[str]:
        """
        Send a command to BizHawk and wait for response.

        Args:
            command: Command string to send

        Returns:
            Response string or None on error/timeout
        """
        # Generate unique command ID
        cmd_id = str(uuid.uuid4())[:8]

        # Write command file with retry (Lua may have file open for reading)
        written = False
        for attempt in range(20):  # ~1s total retry window
            try:
                # Wait for Lua lock to clear
                if self.lock_file.exists():
                    time.sleep(self.poll_interval)
                    continue
                
                with open(self.command_file, "w") as f:
                    f.write(f"{cmd_id}:{command}")
                written = True
                break
            except (PermissionError, OSError):
                time.sleep(0.05)  # Brief pause before retry
        
        if not written:
            logger.warning(f"Could not write command after retries: {command}")
            return None

        # Wait for response
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            try:
                # Wait for lock to be released before reading
                if self.lock_file.exists():
                    time.sleep(self.poll_interval)
                    continue
                    
                if self.response_file.exists():
                    with open(self.response_file, "r") as f:
                        content = f.read().strip()

                    # Check if this is our response
                    if content.startswith(f"{cmd_id}:"):
                        response = content[len(cmd_id) + 1:]
                        # Clean up response file
                        try:
                            self.response_file.unlink()
                        except:
                            pass
                        return response
            except Exception as e:
                logger.debug(f"Error reading response: {e}")

            time.sleep(self.poll_interval)

        logger.warning(f"Timeout waiting for response to: {command}")
        return None

    def _parse_response(self, response: Optional[str]) -> Optional[int]:
        """Parse an OK response into an integer value."""
        if response is None:
            return None
        if response.startswith("OK "):
            try:
                return int(response[3:])
            except ValueError:
                logger.error(f"Invalid response value: {response}")
                return None
        elif response.startswith("ERROR"):
            logger.error(f"BizHawk error: {response}")
            return None
        return None

    # -------------------------------------------------------------------------
    # Memory Read Methods
    # -------------------------------------------------------------------------

    def read8(self, address: int) -> int:
        """Read a single byte from memory."""
        response = self._send_command(f"READ8 {address}")
        result = self._parse_response(response)
        return result if result is not None else 0

    def read16(self, address: int) -> int:
        """Read 2 bytes from memory (little-endian)."""
        response = self._send_command(f"READ16 {address}")
        result = self._parse_response(response)
        return result if result is not None else 0

    def read32(self, address: int) -> int:
        """Read 4 bytes from memory (little-endian)."""
        response = self._send_command(f"READ32 {address}")
        result = self._parse_response(response)
        return result if result is not None else 0

    def read_range(self, address: int, length: int) -> bytes:
        """Read a range of bytes from memory."""
        response = self._send_command(f"READRANGE {address} {length}")
        if response and response.startswith("OK "):
            hex_data = response[3:]
            try:
                return bytes.fromhex(hex_data)
            except ValueError:
                logger.error(f"Invalid hex data in response: {hex_data}")
        return bytes(length)

    def write8(self, address: int, value: int) -> bool:
        """Write a single byte to memory."""
        response = self._send_command(f"WRITE8 {address} {value}")
        return response is not None and response.startswith("OK")

    # -------------------------------------------------------------------------
    # Button Input Methods
    # -------------------------------------------------------------------------

    def tap_button(self, button: str) -> bool:
        """Press and release a button (single tap)."""
        if button not in self.VALID_BUTTONS:
            raise ValueError(f"Invalid button: {button}. Valid: {self.VALID_BUTTONS}")
        response = self._send_command(f"TAP {button}")
        return response is not None and response.startswith("OK")

    def hold_button(self, button: str, frames: int) -> bool:
        """Hold a button for a specified number of frames."""
        if button not in self.VALID_BUTTONS:
            raise ValueError(f"Invalid button: {button}. Valid: {self.VALID_BUTTONS}")
        response = self._send_command(f"HOLD {button} {frames}")
        return response is not None and response.startswith("OK")

    def press_buttons(self, buttons: list[str], frames: int = 1) -> bool:
        """Press multiple buttons simultaneously."""
        for button in buttons:
            if button not in self.VALID_BUTTONS:
                raise ValueError(f"Invalid button: {button}. Valid: {self.VALID_BUTTONS}")
        buttons_str = ",".join(buttons)
        response = self._send_command(f"PRESS {buttons_str} {frames}")
        return response is not None and response.startswith("OK")

    # -------------------------------------------------------------------------
    # Screenshot Methods
    # -------------------------------------------------------------------------

    def save_screenshot(self, filepath: str) -> bool:
        """Capture and save the current frame to a file."""
        abs_path = str(Path(filepath).resolve())
        response = self._send_command(f"SCREENSHOT {abs_path}")
        if response and response.startswith("OK"):
            logger.info(f"Screenshot saved to: {abs_path}")
            return True
        return False

    # -------------------------------------------------------------------------
    # State Management Methods
    # -------------------------------------------------------------------------

    def save_state(self, slot: int) -> bool:
        """Save current state to a slot (1-10)."""
        if not 1 <= slot <= 10:
            raise ValueError(f"Slot must be 1-10, got {slot}")
        response = self._send_command(f"SAVESTATE {slot}")
        return response is not None and response.startswith("OK")

    def load_state(self, slot: int) -> bool:
        """Load state from a slot (1-10)."""
        if not 1 <= slot <= 10:
            raise ValueError(f"Slot must be 1-10, got {slot}")
        response = self._send_command(f"LOADSTATE {slot}")
        return response is not None and response.startswith("OK")

    # -------------------------------------------------------------------------
    # Game Info Methods
    # -------------------------------------------------------------------------

    def get_game_title(self) -> str:
        """Get the title of the currently loaded ROM."""
        response = self._send_command("GAMETITLE")
        if response and response.startswith("OK "):
            return response[3:]
        return ""

    def get_game_code(self) -> str:
        """Get the game code (e.g., BPEE for Emerald)."""
        response = self._send_command("GAMECODE")
        if response and response.startswith("OK "):
            return response[3:]
        return ""

    def get_frame_count(self) -> int:
        """Get current emulator frame count."""
        response = self._send_command("FRAMECOUNT")
        result = self._parse_response(response)
        return result if result is not None else 0

    # -------------------------------------------------------------------------
    # Context Manager Support
    # -------------------------------------------------------------------------

    def __enter__(self) -> "BizHawkClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        """Clean up (no-op for file IPC, but maintains interface)."""
        pass

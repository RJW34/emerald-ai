"""
mGBA Network Client — TCP JSON-lines communication with mGBA Lua bridge.

Connects to the emerald_brain.lua script running inside mGBA on a remote
(or local) machine. Speaks the JSON-lines protocol over TCP.

Protocol:
    Send:    {"action": "state"}\n
    Receive: {"frame": 12345, "scene": "overworld", ...}\n

Usage:
    client = mGBAClient(host="192.168.1.40", port=8785)
    client.connect()
    state = client.get_state()
    client.press("A")
    value = client.read32(0x03005D8C)
"""

import json
import logging
import socket
import time
from typing import Optional

logger = logging.getLogger(__name__)


class mGBAClient:
    """TCP client for communicating with mGBA via the Lua bridge."""

    VALID_BUTTONS = {"A", "B", "Start", "Select", "Up", "Down", "Left", "Right", "L", "R"}

    def __init__(
        self,
        host: str = "192.168.1.40",
        port: int = 8785,
        timeout: float = 5.0,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._recv_buffer = ""

    # -------------------------------------------------------------------------
    # Connection
    # -------------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to the mGBA Lua bridge."""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            logger.info(f"Connected to mGBA at {self.host}:{self.port}")

            # Verify with ping
            resp = self._send({"action": "ping"})
            if resp and resp.get("ok"):
                logger.info(f"mGBA bridge alive, frame={resp.get('frame')}")
                return True
            else:
                logger.error(f"Ping failed: {resp}")
                return False
        except Exception as e:
            logger.error(f"Connection failed to {self.host}:{self.port}: {e}")
            self._sock = None
            return False

    def is_connected(self) -> bool:
        """Check if connected."""
        if not self._sock:
            return False
        try:
            resp = self._send({"action": "ping"})
            return resp is not None and resp.get("ok")
        except Exception:
            return False

    def close(self):
        """Close the connection."""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    # -------------------------------------------------------------------------
    # Core Protocol
    # -------------------------------------------------------------------------

    def _send(self, cmd: dict) -> Optional[dict]:
        """Send a JSON command and receive the JSON response."""
        if not self._sock:
            raise ConnectionError("Not connected to mGBA")

        line = json.dumps(cmd) + "\n"
        try:
            self._sock.sendall(line.encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            logger.error(f"Send failed: {e}")
            self._sock = None
            raise ConnectionError(f"Send failed: {e}")

        return self._recv_line()

    def _recv_line(self) -> Optional[dict]:
        """Receive one newline-terminated JSON response."""
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            nl = self._recv_buffer.find("\n")
            if nl >= 0:
                line = self._recv_buffer[:nl]
                self._recv_buffer = self._recv_buffer[nl + 1:]
                if line.strip():
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON from mGBA: {e}")
                        return None
                continue

            try:
                remaining = max(0.1, deadline - time.time())
                self._sock.settimeout(remaining)
                data = self._sock.recv(4096)
                if not data:
                    logger.error("mGBA connection closed")
                    self._sock = None
                    return None
                self._recv_buffer += data.decode("utf-8")
            except socket.timeout:
                break
            except (ConnectionResetError, OSError) as e:
                logger.error(f"Recv failed: {e}")
                self._sock = None
                return None

        logger.warning("Timeout waiting for mGBA response")
        return None

    # -------------------------------------------------------------------------
    # Game State
    # -------------------------------------------------------------------------

    def get_state(self) -> Optional[dict]:
        """Read the full game state from the Lua bridge."""
        return self._send({"action": "state"})

    # -------------------------------------------------------------------------
    # Input
    # -------------------------------------------------------------------------

    def press(self, button: str, frames: int = 6) -> bool:
        """Press a button for N frames (default 6 = ~100ms)."""
        if button not in self.VALID_BUTTONS:
            raise ValueError(f"Invalid button: {button}. Valid: {self.VALID_BUTTONS}")
        resp = self._send({"action": "press", "button": button, "frames": frames})
        return resp is not None and resp.get("ok", False)

    def hold(self, button: str, frames: Optional[int] = None) -> bool:
        """Hold a button for N frames, or indefinitely if frames is None."""
        if button not in self.VALID_BUTTONS:
            raise ValueError(f"Invalid button: {button}. Valid: {self.VALID_BUTTONS}")
        cmd = {"action": "hold", "button": button}
        if frames is not None:
            cmd["frames"] = frames
        resp = self._send(cmd)
        return resp is not None and resp.get("ok", False)

    def release(self, button: str) -> bool:
        """Release a held button."""
        if button not in self.VALID_BUTTONS:
            raise ValueError(f"Invalid button: {button}. Valid: {self.VALID_BUTTONS}")
        resp = self._send({"action": "release", "button": button})
        return resp is not None and resp.get("ok", False)

    # Aliases for compatibility with InputController
    def tap_button(self, button: str) -> bool:
        return self.press(button)

    def hold_button(self, button: str, frames: int) -> bool:
        return self.hold(button, frames)

    def hold_start(self, button: str) -> bool:
        """Start holding a button indefinitely (until hold_stop)."""
        return self.hold(button)

    def hold_stop(self, button: str) -> bool:
        """Stop holding a button."""
        return self.release(button)

    # -------------------------------------------------------------------------
    # Memory Access
    # -------------------------------------------------------------------------

    def read8(self, address: int) -> int:
        """Read a single byte from GBA memory."""
        resp = self._send({"action": "read8", "addr": address})
        if resp and "value" in resp:
            return resp["value"]
        return 0

    def read16(self, address: int) -> int:
        """Read 2 bytes (little-endian u16) from GBA memory."""
        resp = self._send({"action": "read16", "addr": address})
        if resp and "value" in resp:
            return resp["value"]
        return 0

    def read32(self, address: int) -> int:
        """Read 4 bytes (little-endian u32) from GBA memory."""
        resp = self._send({"action": "read32", "addr": address})
        if resp and "value" in resp:
            return resp["value"]
        return 0

    def read_range(self, address: int, length: int) -> bytes:
        """Read a range of bytes from GBA memory.

        Uses the Lua bridge's readrange action for efficiency (single round trip).
        Falls back to individual read32 calls if not supported.
        """
        resp = self._send({"action": "readrange", "addr": address, "length": length})
        if resp and "data" in resp:
            try:
                return bytes.fromhex(resp["data"])
            except ValueError:
                pass

        # Fallback: read 4 bytes at a time
        result = bytearray(length)
        for offset in range(0, length, 4):
            remaining = min(4, length - offset)
            val = self.read32(address + offset)
            chunk = val.to_bytes(4, "little")
            result[offset:offset + remaining] = chunk[:remaining]
        return bytes(result)

    # -------------------------------------------------------------------------
    # Screenshots
    # -------------------------------------------------------------------------

    def screenshot(self, path: str = "emerald_screen.png") -> bool:
        """Save a screenshot on the remote machine."""
        resp = self._send({"action": "screenshot", "path": path})
        return resp is not None and resp.get("ok", False)

    def screenshot_b64(self) -> Optional[str]:
        """Take a screenshot and return it as a base64-encoded PNG string.

        Uses the Lua bridge to save a screenshot to a temp file,
        then reads it back via the readfile action and encodes as base64.
        Returns None on failure.
        """
        import base64 as _b64
        temp_path = "/tmp/_mgba_screenshot_b64.png"
        # Take screenshot to temp file
        resp = self._send({"action": "screenshot", "path": temp_path})
        if not resp or not resp.get("ok"):
            return None
        # Read the file back as hex
        file_resp = self._send({"action": "readfile", "path": temp_path})
        if not file_resp or not file_resp.get("data"):
            return None
        try:
            file_bytes = bytes.fromhex(file_resp["data"])
            return _b64.b64encode(file_bytes).decode("ascii")
        except (ValueError, TypeError):
            return None

    # -------------------------------------------------------------------------
    # Convenience
    # -------------------------------------------------------------------------

    def get_game_code(self) -> str:
        """Get game code from state."""
        return "BPEE"  # Assumed for Emerald

    def get_frame_count(self) -> int:
        """Get current frame count."""
        resp = self._send({"action": "ping"})
        if resp and "frame" in resp:
            return resp["frame"]
        return 0

    def get_input_state(self) -> Optional[dict]:
        """Get current input queue and held keys."""
        return self._send({"action": "input_state"})

    def save_state(self, slot: int = 0) -> bool:
        """Stub — mGBA Lua bridge does not support save states over TCP.
        Returns False silently so callers that checkpoint via save_state don't crash.
        """
        logger.debug("save_state(%d) called — not supported over Lua bridge, skipping", slot)
        return False

    def load_state(self, slot: int = 0) -> bool:
        """Stub — mGBA Lua bridge does not support load states over TCP.
        Returns False silently.
        """
        logger.debug("load_state(%d) called — not supported over Lua bridge, skipping", slot)
        return False

    # -------------------------------------------------------------------------
    # Context Manager
    # -------------------------------------------------------------------------

    def __enter__(self) -> "mGBAClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

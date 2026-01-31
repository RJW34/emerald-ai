"""
BizHawk Socket Client - TCP socket communication with BizHawk emulator.

Uses BizHawk's built-in comm.socketServer API for low-latency communication.
Python runs a TCP server; BizHawk Lua connects as a client.

Architecture:
    Python (this) = TCP Server (listens on port)
    BizHawk Lua   = TCP Client (connects to us)

Protocol (BizHawk 2.6.2+):
    Messages are length-prefixed: "{length} {message}"
    Example: "4 PONG" means message is 4 bytes: "PONG"

Performance vs File IPC:
    - File IPC: ~16ms per command (1 frame at 60fps)
    - Socket:   ~1-2ms per command (sub-frame)
    - Bulk GETSTATE: Single call replaces 5-10 individual reads
"""

import logging
import re
import socket
import struct
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 51055


class BizHawkSocketClient:
    """
    TCP socket server that BizHawk connects to via comm.socketServer*.

    Drop-in replacement for BizHawkClient (file-based IPC) with the same
    public API, but uses TCP sockets for much lower latency.
    """

    VALID_BUTTONS = {"A", "B", "Start", "Select", "Up", "Down", "Left", "Right", "L", "R"}

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = 5.0,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout

        self._server_socket: Optional[socket.socket] = None
        self._client_socket: Optional[socket.socket] = None
        self._connected = False
        self._lock = threading.Lock()

    # -------------------------------------------------------------------------
    # Connection Management
    # -------------------------------------------------------------------------

    def start_server(self) -> bool:
        """Start TCP server and wait for BizHawk to connect."""
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.settimeout(self.timeout)
            self._server_socket.bind((self.host, self.port))
            self._server_socket.listen(1)
            logger.info(f"Socket server listening on {self.host}:{self.port}")
            logger.info("Waiting for BizHawk to connect (load the socket bridge Lua script)...")
            return True
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return False

    def wait_for_connection(self, timeout: float = 30.0) -> bool:
        """Wait for BizHawk Lua script to connect."""
        if not self._server_socket:
            if not self.start_server():
                return False

        self._server_socket.settimeout(timeout)
        try:
            self._client_socket, addr = self._server_socket.accept()
            self._client_socket.settimeout(self.timeout)
            # Disable Nagle's algorithm for low latency
            self._client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            logger.info(f"BizHawk connected from {addr}")

            # Read the initial HELLO message from Lua
            hello = self._recv_message()
            if hello:
                logger.info(f"Received handshake: {hello}")

            self._connected = True
            return True
        except socket.timeout:
            logger.warning(f"No connection from BizHawk within {timeout}s")
            return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    def connect(self) -> bool:
        """
        Start server and wait for BizHawk connection.
        Compatible with BizHawkClient.connect() API.
        """
        if not self.start_server():
            return False
        if not self.wait_for_connection():
            return False

        # Verify with PING
        response = self._send_command("PING")
        if response and "PONG" in response:
            logger.info("Connection verified with PING/PONG")
            return True

        logger.error(f"PING failed, got: {response}")
        return False

    def is_connected(self) -> bool:
        """Check if BizHawk is connected."""
        if not self._connected:
            return False
        try:
            response = self._send_command("PING")
            return response is not None and "PONG" in response
        except:
            self._connected = False
            return False

    def close(self):
        """Close all sockets."""
        self._connected = False
        if self._client_socket:
            try:
                self._client_socket.close()
            except:
                pass
            self._client_socket = None
        if self._server_socket:
            try:
                self._server_socket.close()
            except:
                pass
            self._server_socket = None

    # -------------------------------------------------------------------------
    # Protocol: Length-prefixed messages
    # -------------------------------------------------------------------------

    def _send_message(self, msg: str) -> bool:
        """Send a length-prefixed message to BizHawk."""
        if not self._client_socket:
            return False
        try:
            prefixed = f"{len(msg)} {msg}"
            self._client_socket.sendall(prefixed.encode('utf-8'))
            return True
        except Exception as e:
            logger.error(f"Send failed: {e}")
            self._connected = False
            return False

    def _recv_message(self) -> Optional[str]:
        """Receive a length-prefixed message from BizHawk."""
        if not self._client_socket:
            return None
        try:
            # Read until we get the full message
            # BizHawk sends: "{length} {message}"
            buf = b""
            while True:
                chunk = self._client_socket.recv(4096)
                if not chunk:
                    self._connected = False
                    return None
                buf += chunk

                # Try to parse length prefix
                text = buf.decode('utf-8', errors='replace')
                match = re.match(r'^(\d+)\s', text)
                if match:
                    msg_len = int(match.group(1))
                    prefix_len = len(match.group(0))
                    total_needed = prefix_len + msg_len
                    if len(buf) >= total_needed:
                        return text[prefix_len:prefix_len + msg_len]
                    # Need more data, continue reading
                elif len(buf) > 100:
                    # Fallback: return raw if no length prefix detected
                    return text.strip()

        except socket.timeout:
            return None
        except Exception as e:
            logger.error(f"Recv failed: {e}")
            self._connected = False
            return None

    def _send_command(self, command: str) -> Optional[str]:
        """Send a command and wait for response."""
        with self._lock:
            if not self._send_message(command):
                return None
            return self._recv_message()

    def _parse_response(self, response: Optional[str]) -> Optional[int]:
        """Parse an OK response into an integer value."""
        if response is None:
            return None
        if response.startswith("OK "):
            try:
                return int(response[3:])
            except ValueError:
                return None
        elif response.startswith("ERROR"):
            logger.error(f"BizHawk error: {response}")
            return None
        return None

    # -------------------------------------------------------------------------
    # Memory Read Methods (same API as BizHawkClient)
    # -------------------------------------------------------------------------

    def read8(self, address: int) -> int:
        response = self._send_command(f"READ8 {address}")
        result = self._parse_response(response)
        return result if result is not None else 0

    def read16(self, address: int) -> int:
        response = self._send_command(f"READ16 {address}")
        result = self._parse_response(response)
        return result if result is not None else 0

    def read32(self, address: int) -> int:
        response = self._send_command(f"READ32 {address}")
        result = self._parse_response(response)
        return result if result is not None else 0

    def read_range(self, address: int, length: int) -> bytes:
        response = self._send_command(f"READRANGE {address} {length}")
        if response and response.startswith("OK "):
            hex_data = response[3:]
            try:
                return bytes.fromhex(hex_data)
            except ValueError:
                logger.error(f"Invalid hex data: {hex_data[:40]}...")
        return bytes(length)

    # -------------------------------------------------------------------------
    # Bulk State Read (socket-only optimization)
    # -------------------------------------------------------------------------

    def get_state(self) -> Optional[dict]:
        """
        Read bulk game state in a single round-trip.

        Returns a dict with keys like:
            sb1, sb2, bf (battle_flags), cb1, cb2, frame,
            px, py, mg, mn (player pos, map),
            And if in battle: weather, ps/php/pmhp/plv (player),
            es/ehp/emhp/elv (enemy)

        This replaces 5-10 individual read calls with ONE socket round-trip.
        """
        response = self._send_command("GETSTATE")
        if not response or not response.startswith("OK "):
            return None

        data = response[3:]
        result = {}
        for pair in data.split():
            if "=" in pair:
                key, val = pair.split("=", 1)
                try:
                    result[key] = int(val)
                except ValueError:
                    result[key] = val

        return result

    # -------------------------------------------------------------------------
    # Button Input Methods
    # -------------------------------------------------------------------------

    def tap_button(self, button: str) -> bool:
        if button not in self.VALID_BUTTONS:
            raise ValueError(f"Invalid button: {button}")
        response = self._send_command(f"TAP {button}")
        return response is not None and response.startswith("OK")

    def hold_button(self, button: str, frames: int) -> bool:
        if button not in self.VALID_BUTTONS:
            raise ValueError(f"Invalid button: {button}")
        response = self._send_command(f"HOLD {button} {frames}")
        return response is not None and response.startswith("OK")

    def press_buttons(self, buttons: list[str], frames: int = 1) -> bool:
        for b in buttons:
            if b not in self.VALID_BUTTONS:
                raise ValueError(f"Invalid button: {b}")
        response = self._send_command(f"PRESS {','.join(buttons)} {frames}")
        return response is not None and response.startswith("OK")

    # -------------------------------------------------------------------------
    # Screenshot / State Methods
    # -------------------------------------------------------------------------

    def save_screenshot(self, filepath: str) -> bool:
        from pathlib import Path
        abs_path = str(Path(filepath).resolve())
        response = self._send_command(f"SCREENSHOT {abs_path}")
        return response is not None and response.startswith("OK")

    def save_state(self, slot: int) -> bool:
        if not 1 <= slot <= 10:
            raise ValueError(f"Slot must be 1-10, got {slot}")
        response = self._send_command(f"SAVESTATE {slot}")
        return response is not None and response.startswith("OK")

    def load_state(self, slot: int) -> bool:
        if not 1 <= slot <= 10:
            raise ValueError(f"Slot must be 1-10, got {slot}")
        response = self._send_command(f"LOADSTATE {slot}")
        return response is not None and response.startswith("OK")

    # -------------------------------------------------------------------------
    # Game Info Methods
    # -------------------------------------------------------------------------

    def get_game_title(self) -> str:
        response = self._send_command("GAMETITLE")
        if response and response.startswith("OK "):
            return response[3:]
        return ""

    def get_game_code(self) -> str:
        response = self._send_command("GAMECODE")
        if response and response.startswith("OK "):
            return response[3:]
        return ""

    def get_frame_count(self) -> int:
        response = self._send_command("FRAMECOUNT")
        result = self._parse_response(response)
        return result if result is not None else 0

    # -------------------------------------------------------------------------
    # Context Manager
    # -------------------------------------------------------------------------

    def __enter__(self) -> "BizHawkSocketClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

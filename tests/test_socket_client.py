"""
Tests for BizHawkSocketClient.

Tests the socket client in isolation using a mock server that
simulates BizHawk's comm.socketServer protocol.
"""

import socket
import threading
import time
import pytest

from src.emulator.bizhawk_socket_client import BizHawkSocketClient


class MockBizHawkLua:
    """Simulates BizHawk's Lua socket client behavior."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock = None
        self.running = False
        self._responses = {
            "PING": "PONG",
            "GAMETITLE": "OK Pokemon - Emerald Version (U)",
            "GAMECODE": "OK BPEE",
            "FRAMECOUNT": "OK 12345",
            "READ8 50331020": "OK 42",
            "READ16 50331020": "OK 1234",
            "READ32 50331020": "OK 305419896",
            "TAP A": "OK",
            "GETSTATE": "OK sb1=33627648 sb2=33619968 bf=0 cb1=134222388 cb2=134244984 frame=5000 px=10 py=20 mg=1 mn=3",
        }

    def connect_and_serve(self):
        """Connect to Python server and handle commands."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        try:
            self.sock.connect((self.host, self.port))
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            # Send HELLO handshake
            hello = "HELLO"
            self.sock.sendall(f"{len(hello)} {hello}".encode())

            self.running = True
            while self.running:
                try:
                    data = self.sock.recv(4096)
                    if not data:
                        break

                    text = data.decode('utf-8')
                    # Parse length-prefixed: "{len} {msg}"
                    import re
                    match = re.match(r'^(\d+)\s(.+)$', text)
                    if match:
                        cmd = match.group(2)
                    else:
                        cmd = text.strip()

                    # Look up response
                    response = self._responses.get(cmd, f"ERROR Unknown: {cmd}")

                    # Send length-prefixed response
                    self.sock.sendall(f"{len(response)} {response}".encode())

                except socket.timeout:
                    continue
                except Exception:
                    break
        finally:
            if self.sock:
                self.sock.close()

    def stop(self):
        self.running = False


@pytest.fixture
def socket_pair():
    """Create a connected client-server pair with mock BizHawk."""
    client = BizHawkSocketClient(host="127.0.0.1", port=0)  # port 0 = auto-assign

    # Start server on random port
    client._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    client._server_socket.bind(("127.0.0.1", 0))
    client._server_socket.listen(1)
    _, port = client._server_socket.getsockname()

    # Start mock BizHawk in background
    mock = MockBizHawkLua("127.0.0.1", port)
    thread = threading.Thread(target=mock.connect_and_serve, daemon=True)
    thread.start()

    # Accept connection
    client._server_socket.settimeout(5)
    client._client_socket, _ = client._server_socket.accept()
    client._client_socket.settimeout(5)
    client._client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    # Read HELLO
    hello = client._recv_message()
    client._connected = True

    yield client, mock

    mock.stop()
    client.close()


class TestSocketProtocol:
    """Test the length-prefixed message protocol."""

    def test_ping_pong(self, socket_pair):
        client, _ = socket_pair
        response = client._send_command("PING")
        assert response == "PONG"

    def test_game_title(self, socket_pair):
        client, _ = socket_pair
        title = client.get_game_title()
        assert "Emerald" in title

    def test_game_code(self, socket_pair):
        client, _ = socket_pair
        code = client.get_game_code()
        assert code == "BPEE"

    def test_frame_count(self, socket_pair):
        client, _ = socket_pair
        frame = client.get_frame_count()
        assert frame == 12345

    def test_read8(self, socket_pair):
        client, _ = socket_pair
        val = client.read8(50331020)
        assert val == 42

    def test_read16(self, socket_pair):
        client, _ = socket_pair
        val = client.read16(50331020)
        assert val == 1234

    def test_read32(self, socket_pair):
        client, _ = socket_pair
        val = client.read32(50331020)
        assert val == 305419896

    def test_tap_button(self, socket_pair):
        client, _ = socket_pair
        assert client.tap_button("A") is True

    def test_invalid_button(self, socket_pair):
        client, _ = socket_pair
        with pytest.raises(ValueError):
            client.tap_button("X")

    def test_get_state_bulk(self, socket_pair):
        client, _ = socket_pair
        state = client.get_state()
        assert state is not None
        assert state["sb1"] == 33627648
        assert state["frame"] == 5000
        assert state["px"] == 10
        assert state["py"] == 20
        assert state["bf"] == 0  # not in battle

    def test_is_connected(self, socket_pair):
        client, _ = socket_pair
        assert client.is_connected() is True


class TestSocketClientAPI:
    """Test that socket client has same API as file-based client."""

    def test_has_all_methods(self):
        """Ensure socket client is a drop-in replacement."""
        from src.emulator.bizhawk_client import BizHawkClient

        file_methods = {m for m in dir(BizHawkClient) if not m.startswith('_')}
        socket_methods = {m for m in dir(BizHawkSocketClient) if not m.startswith('_')}

        # Socket client should have all file client methods
        missing = file_methods - socket_methods
        # Filter out implementation details
        missing.discard('poll_interval')
        missing.discard('ipc_dir')
        missing.discard('command_file')
        missing.discard('response_file')

        assert len(missing) == 0, f"Socket client missing methods: {missing}"

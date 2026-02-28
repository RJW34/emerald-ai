#!/usr/bin/env python3
"""
Emerald Brain — Claude-powered decision loop for Pokemon Emerald.

Connects directly to the Lua TCP bridge running inside mGBA (port 8785).
Reads game state via {"cmd":"state"}, sends inputs via {"cmd":"press"}.
Asks Claude Haiku for decisions. Fully Lua-native — no xdotool, no /proc/mem.

Usage:
    python3 brain.py                  # run decision loop
    python3 brain.py --tick 2.5       # 2.5 second tick rate
    python3 brain.py --dry-run        # print decisions without executing
    python3 brain.py --once           # single decision then exit
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import socket
import sys
import time
from pathlib import Path
from typing import Optional

import urllib.request
import urllib.error

# ── Configuration ────────────────────────────────────────────

PROJECT_DIR = Path(__file__).parent
LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Lua bridge TCP connection
LUA_HOST = os.environ.get("LUA_HOST", "127.0.0.1")
LUA_PORT = int(os.environ.get("LUA_PORT", "8779"))

TICK_RATE = float(os.environ.get("TICK_RATE", "2.0"))

# API config
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-6-20250514")

HISTORY_DEPTH = 12

# Map names for Emerald
MAP_NAMES = {
    (0, 0): "Petalburg City", (0, 1): "Slateport City", (0, 2): "Mauville City",
    (0, 3): "Rustboro City", (0, 4): "Fortree City", (0, 5): "Lilycove City",
    (0, 6): "Mossdeep City", (0, 7): "Sootopolis City", (0, 8): "Ever Grande City",
    (0, 9): "Littleroot Town", (0, 10): "Oldale Town", (0, 11): "Dewford Town",
    (0, 12): "Lavaridge Town", (0, 13): "Fallarbor Town", (0, 14): "Verdanturf Town",
    (0, 15): "Pacifidlog Town",
    (0, 16): "Route 101", (0, 17): "Route 102", (0, 18): "Route 103",
    (0, 19): "Route 104", (0, 25): "Route 110", (0, 26): "Route 111",
    (0, 31): "Route 116", (0, 32): "Route 117", (0, 33): "Route 118",
    (24, 7): "Petalburg Woods", (24, 4): "Granite Cave 1F",
    (25, 0): "Pokemon League", (26, 0): "Player's House 1F",
    (26, 1): "Player's House 2F", (26, 3): "Birch's Lab",
}

SPECIES_NAMES = {
    258: "Mudkip", 259: "Marshtomp", 260: "Swampert",
    252: "Treecko", 253: "Grovyle", 254: "Sceptile",
    255: "Torchic", 256: "Combusken", 257: "Blaziken",
    261: "Poochyena", 262: "Mightyena", 263: "Zigzagoon", 264: "Linoone",
    265: "Wurmple", 270: "Lotad", 273: "Seedot", 276: "Taillow",
    278: "Wingull", 280: "Ralts", 285: "Shroomish", 287: "Slakoth",
    293: "Whismur", 296: "Makuhita", 300: "Skitty", 304: "Aron",
    318: "Carvanha", 322: "Numel", 324: "Torkoal", 328: "Trapinch",
    333: "Swablu", 339: "Barboach", 341: "Corphish", 343: "Baltoy",
    349: "Feebas", 352: "Kecleon", 359: "Absol", 371: "Bagon",
    374: "Beldum", 377: "Regirock", 378: "Regice", 379: "Registeel",
    380: "Latias", 381: "Latios", 382: "Kyogre", 383: "Groudon",
    384: "Rayquaza", 41: "Zubat", 63: "Abra", 66: "Machop",
    72: "Tentacool", 74: "Geodude", 81: "Magnemite", 129: "Magikarp",
    183: "Marill",
}


def _load_env_file(path: str):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and value and not os.environ.get(key):
                        os.environ[key] = value
    except FileNotFoundError:
        pass


_load_env_file(str(PROJECT_DIR / ".env"))
_load_env_file("/home/ryan/projects/emerald-ai/.env")

if not ANTHROPIC_API_KEY:
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Logging ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("emerald-brain")

brain_log_handler = logging.FileHandler(LOG_DIR / "brain.log")
brain_log_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))
log.addHandler(brain_log_handler)


# ── Lua Bridge Client ────────────────────────────────────────

class LuaBridge:
    """TCP client for the mGBA Lua bridge (port 8785).

    Uses connect-per-command pattern because mGBA's Lua socket callback
    only fires once per connection in some builds. Each command opens a
    fresh TCP connection, sends one JSON-line, reads the response, and closes.
    """

    def __init__(self, host: str = LUA_HOST, port: int = LUA_PORT):
        self.host = host
        self.port = port

    def send_command(self, cmd: dict, timeout: float = 5.0) -> Optional[dict]:
        """Connect, send one command, receive one response, disconnect."""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((self.host, self.port))

            payload = json.dumps(cmd, separators=(",", ":")) + "\n"
            sock.sendall(payload.encode("utf-8"))

            data = b""
            while b"\n" not in data:
                chunk = sock.recv(8192)
                if not chunk:
                    return None
                data += chunk

            nl = data.index(b"\n")
            return json.loads(data[:nl].decode("utf-8", errors="replace"))

        except socket.timeout:
            log.warning("Lua bridge timeout")
            return None
        except ConnectionRefusedError:
            log.warning("Lua bridge not available (connection refused)")
            return None
        except Exception as e:
            log.error(f"Lua bridge error: {e}")
            return None
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def connect(self) -> bool:
        """Test connectivity by sending a ping."""
        return self.ping()

    def close(self):
        pass  # No persistent connection to close

    def ping(self) -> bool:
        resp = self.send_command({"cmd": "ping"})
        return resp is not None and resp.get("ok", False)

    def get_state(self) -> Optional[dict]:
        return self.send_command({"cmd": "state"})

    def press(self, key: str, frames: int = 6) -> bool:
        resp = self.send_command({"cmd": "press", "key": key, "frames": frames})
        return resp is not None and resp.get("ok", False)

    def screenshot(self, path: str = "/tmp/emerald_screen.png") -> bool:
        resp = self.send_command({"cmd": "screenshot", "path": path})
        return resp is not None and resp.get("ok", False)


# ── Game State Formatting ────────────────────────────────────

def format_lua_state(state: dict) -> str:
    """Format Lua bridge state into readable text for Claude."""
    if not state:
        return "Game state: unavailable (Lua bridge not responding)"

    scene = state.get("scene", "unknown")
    if scene == "title_screen":
        return f"Game status: title_screen — {state.get('error', 'save blocks not initialized')}"

    player_name = state.get("player_name", "")
    if not player_name:
        return "Game status: title_screen — no player name set"

    lines = []
    lines.append(f"Status: {scene.upper()}")
    lines.append(f"Player: {player_name}")

    mg = state.get("map_group", 0)
    mn = state.get("map_num", 0)
    map_name = MAP_NAMES.get((mg, mn), f"Map ({mg},{mn})")
    lines.append(f"Location: {map_name}")

    px = state.get("pos_x", 0)
    py = state.get("pos_y", 0)
    lines.append(f"Position: ({px}, {py})")

    badge_count = state.get("badge_count", 0)
    lines.append(f"Badges: {badge_count}/8")

    money = state.get("money", 0)
    if money and money < 1000000:
        lines.append(f"Money: ${money:,}")

    ph = state.get("play_hours", 0)
    pm = state.get("play_minutes", 0)
    ps = state.get("play_seconds", 0)
    lines.append(f"Playtime: {ph}h {pm}m {ps}s")

    in_battle = scene == "battle"
    lines.append(f"In Battle: {in_battle}")

    party = state.get("party", [])
    party_count = state.get("party_count", len(party))
    if party:
        lines.append(f"Party ({party_count}):")
        for i, mon in enumerate(party):
            sp_id = mon.get("species", 0)
            sp_name = SPECIES_NAMES.get(sp_id, f"Pokemon #{sp_id}")
            nick = mon.get("nickname", "?")
            lv = mon.get("level", "?")
            hp = mon.get("hp", "?")
            max_hp = mon.get("max_hp", "?")
            lines.append(f"  [{i+1}] {nick} ({sp_name}) Lv{lv} HP:{hp}/{max_hp}")
    else:
        lines.append("Party: EMPTY — you have not received your starter yet!")

    return "\n".join(lines)


# ── System Prompt ────────────────────────────────────────────

SYSTEM_PROMPT = """You are an AI playing Pokemon Emerald on a GBA emulator. Your player name is RYAN and your starter is Mudkip. You control the game by issuing button presses.

## Available Buttons
A, B, START, SELECT, UP, DOWN, LEFT, RIGHT, L, R

## Action Format
Reply with ONLY a JSON object. No other text.

Single button:
{"action": "press", "key": "A"}

Walk a direction:
{"action": "walk", "direction": "UP", "steps": 5}

Mash A for dialogue:
{"action": "mash_a", "count": 8}

Button sequence:
{"action": "sequence", "keys": ["DOWN", "DOWN", "A"]}

## Game Knowledge

### Early Game Flow (Pre-Starter, party empty)
1. Start → NEW GAME → intro speech → name RYAN → arrive in truck
2. Exit truck (A through text, walk down)
3. Mom talks in house → go upstairs → set clock → go back down
4. Exit house, walk north out of Littleroot Town to Route 101
5. Birch chased by Zigzagoon → choose Mudkip from bag
6. Battle Zigzagoon → return to lab → get Pokedex

### Post-Starter (badges = 0)
1. Route 103 north → rival battle → back to lab → Pokedex
2. Route 102 west → Petalburg City → meet Dad/Wally
3. Route 104 → Petalburg Woods → Rustboro City
4. First gym: Roxanne (Rock type) — use Water Gun

### Navigation
- If position doesn't change after walking, you're hitting a wall — try another direction
- For dialogue: mash A to advance text
- For menus: UP/DOWN to navigate, A to select, B to back out
- If stuck for 3+ turns at same position, try something completely different

### Battle
- Select FIGHT then pick a move. Mudkip learns Water Gun at Lv6.
- Low HP? Use Potion from BAG in battle menu.
- Wild battles: fight to train, run from weak stuff if HP is low.

## Rules
1. Output ONLY JSON. No markdown, no explanation.
2. Watch your position — adapt if it doesn't change.
3. Don't repeat the same failing action.
4. Be strategic about leveling before gym battles."""


# ── Conversation History ─────────────────────────────────────

class ConversationHistory:
    def __init__(self, max_entries: int = HISTORY_DEPTH):
        self.entries: collections.deque = collections.deque(maxlen=max_entries)

    def add(self, state_summary: str, action: dict, position: tuple):
        self.entries.append({
            "state": state_summary,
            "action": action,
            "position": position,
        })

    def format_for_prompt(self) -> str:
        if not self.entries:
            return "No previous actions — first decision."

        lines = ["Recent history (oldest first):"]
        for i, entry in enumerate(self.entries):
            pos = entry["position"]
            act = json.dumps(entry["action"], separators=(",", ":"))
            lines.append(f"  Turn {i+1}: pos=({pos[0]},{pos[1]}) → {act}")

        if len(self.entries) >= 3:
            recent = [e["position"] for e in list(self.entries)[-3:]]
            if all(p == recent[0] for p in recent):
                lines.append("  *** STUCK: Position unchanged for 3+ turns! Try a completely different approach. ***")

        return "\n".join(lines)


# ── Claude API ───────────────────────────────────────────────

def call_claude(game_state_text: str, history: ConversationHistory) -> Optional[dict]:
    if not ANTHROPIC_API_KEY:
        log.error("No ANTHROPIC_API_KEY configured")
        return None

    user_message = (
        f"Current game state:\n{game_state_text}\n\n"
        f"{history.format_for_prompt()}\n\n"
        f"What is your next action? Reply with ONLY JSON."
    )

    try:
        body = json.dumps({
            "model": ANTHROPIC_MODEL,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_message}],
            "max_tokens": 200,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())

        content = data["content"][0]["text"].strip()
        return _parse_action(content)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if hasattr(e, "read") else ""
        log.error(f"Anthropic API {e.code}: {error_body[:300]}")
        return None
    except Exception as e:
        log.error(f"Claude call failed: {e}")
        return None


def _parse_action(content: str) -> Optional[dict]:
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines).strip()

    try:
        action = json.loads(content)
        if isinstance(action, dict) and "action" in action:
            return action
    except json.JSONDecodeError:
        pass

    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            action = json.loads(content[start:end])
            if isinstance(action, dict) and "action" in action:
                return action
        except json.JSONDecodeError:
            pass

    log.warning(f"Could not parse action: {content[:200]}")
    return None


# ── Action Executor ──────────────────────────────────────────

def execute_action(bridge: LuaBridge, action: dict) -> bool:
    action_type = action.get("action", "")

    try:
        if action_type == "press":
            key = action.get("key", "A")
            frames = action.get("frames", 6)
            return bridge.press(key, frames)

        elif action_type == "walk":
            direction = action.get("direction", "UP")
            steps = min(action.get("steps", 1), 15)
            for _ in range(steps):
                if not bridge.press(direction, 8):
                    return False
                time.sleep(0.15)
            return True

        elif action_type == "mash_a":
            count = min(action.get("count", 5), 25)
            for _ in range(count):
                if not bridge.press("A", 4):
                    return False
                time.sleep(0.1)
            return True

        elif action_type == "sequence":
            keys = action.get("keys", [])
            for key in keys[:20]:
                if not bridge.press(key, 6):
                    return False
                time.sleep(0.15)
            return True

        else:
            log.warning(f"Unknown action type: {action_type}")
            return False

    except Exception as e:
        log.error(f"Execution error: {e}")
        return False


# ── Main Loop ────────────────────────────────────────────────

def run_brain(tick_rate: float = 2.0, dry_run: bool = False, once: bool = False):
    log.info("=" * 50)
    log.info("Emerald Brain v3 (Lua-native) starting")
    log.info(f"  Bridge: {LUA_HOST}:{LUA_PORT}")
    log.info(f"  Model:  {ANTHROPIC_MODEL}")
    log.info(f"  Tick:   {tick_rate}s")
    log.info(f"  Dry:    {dry_run}")
    log.info("=" * 50)

    if not ANTHROPIC_API_KEY:
        log.error("No ANTHROPIC_API_KEY! Set it in .env or environment.")
        return

    bridge = LuaBridge()
    if not bridge.connect():
        log.error("Cannot connect to Lua bridge. Is mGBA running with the script?")
        return

    if bridge.ping():
        log.info("Lua bridge ping: OK")
    else:
        log.error("Lua bridge ping failed")
        return

    history = ConversationHistory(max_entries=HISTORY_DEPTH)
    decision_count = 0
    error_streak = 0

    try:
        while True:
            tick_start = time.time()
            decision_count += 1

            # 1. Fetch game state from Lua bridge
            state = bridge.get_state()
            if not state:
                log.warning(f"[#{decision_count}] No state from Lua bridge")
                error_streak += 1
                if error_streak >= 5:
                    log.info("Reconnecting to Lua bridge...")
                    bridge.close()
                    if not bridge.connect():
                        log.error("Reconnection failed, sleeping 10s")
                        time.sleep(10)
                    error_streak = 0
                time.sleep(tick_rate)
                continue

            scene = state.get("scene", "unknown")

            # Handle title screen — press A/START to advance
            if scene == "title_screen" or not state.get("player_name"):
                log.info(f"[#{decision_count}] Title screen — pressing A")
                if not dry_run:
                    bridge.press("A", 6)
                    time.sleep(0.5)
                    bridge.press("START", 6)
                time.sleep(tick_rate)
                continue

            # 2. Format state for Claude
            state_text = format_lua_state(state)
            px = state.get("pos_x", 0)
            py = state.get("pos_y", 0)
            current_pos = (px, py)

            mg = state.get("map_group", 0)
            mn = state.get("map_num", 0)
            map_name = MAP_NAMES.get((mg, mn), f"Map({mg},{mn})")

            log.info(f"[#{decision_count}] {map_name} pos={current_pos} "
                     f"badges={state.get('badge_count', 0)} "
                     f"party={state.get('party_count', 0)} "
                     f"scene={scene}")

            # 3. Ask Claude
            action = call_claude(state_text, history)
            if not action:
                log.warning(f"[#{decision_count}] No action from Claude")
                error_streak += 1
                time.sleep(tick_rate)
                continue

            log.info(f"[#{decision_count}] Action: {json.dumps(action, separators=(',', ':'))}")
            error_streak = 0

            # 4. Record history
            history.add(f"{map_name} pos={current_pos}", action, current_pos)

            # 5. Execute
            if dry_run:
                log.info(f"[#{decision_count}] DRY RUN — skipping")
            else:
                ok = execute_action(bridge, action)
                log.info(f"[#{decision_count}] Executed: {'OK' if ok else 'FAILED'}")

            if once:
                log.info("Single decision mode — done")
                break

            # 6. Sleep remaining tick time
            elapsed = time.time() - tick_start
            remaining = max(0, tick_rate - elapsed)
            if remaining > 0:
                time.sleep(remaining)

    except KeyboardInterrupt:
        log.info("Brain stopped by user")
    finally:
        bridge.close()
        log.info(f"Brain shut down after {decision_count} decisions")


def main():
    parser = argparse.ArgumentParser(description="Emerald Brain v3 — Lua-native Claude loop")
    parser.add_argument("--tick", type=float, default=TICK_RATE, help="Seconds between decisions")
    parser.add_argument("--dry-run", action="store_true", help="Print without executing")
    parser.add_argument("--once", action="store_true", help="One decision then exit")
    parser.add_argument("--host", default=LUA_HOST, help="Lua bridge host")
    parser.add_argument("--port", type=int, default=LUA_PORT, help="Lua bridge port")
    args = parser.parse_args()

    global LUA_HOST, LUA_PORT
    LUA_HOST = args.host
    LUA_PORT = args.port

    run_brain(tick_rate=args.tick, dry_run=args.dry_run, once=args.once)


if __name__ == "__main__":
    main()

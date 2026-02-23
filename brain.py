#!/usr/bin/env python3
"""
Emerald Brain v2 — Claude-powered decision loop for Pokemon Emerald.

Reads game state from game_state_server (port 8776), asks Claude Haiku
for the next action, and executes it via xdotool (MGBAController).

Usage:
    python3 brain.py                  # run decision loop
    python3 brain.py --tick 3.0       # 3 second tick rate
    python3 brain.py --dry-run        # print decisions without executing
    python3 brain.py --once           # single decision then exit
    python3 brain.py --dry-run --once # test: one decision, no execution
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import urllib.request
import urllib.error

# Add project root so we can import the xdotool controller
sys.path.insert(0, str(Path(__file__).parent))
from mgba_xdotool_controller import MGBAController

# ── Configuration ────────────────────────────────────────────

PROJECT_DIR = Path(__file__).parent
LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

GAME_STATE_URL = os.environ.get("GAME_STATE_URL", "http://localhost:8776/state")
TICK_RATE = float(os.environ.get("TICK_RATE", "2.0"))

# API config — prefer OpenRouter (Haiku is fast+cheap for game input)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def _load_env_file(path: str):
    """Load KEY=VALUE pairs from a file into os.environ."""
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
_load_env_file(os.path.expanduser("~/.config/zeroclaw/env"))

# Re-read after loading .env files
if not OPENROUTER_API_KEY:
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not ANTHROPIC_API_KEY:
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Model selection
OPENROUTER_MODEL = "anthropic/claude-haiku-4-5"
ANTHROPIC_MODEL = "claude-haiku-4-5-20250610"

# Conversation history depth
HISTORY_DEPTH = 10

# ── Logging ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("emerald-brain")

# File handler for brain.log
brain_log_handler = logging.FileHandler(LOG_DIR / "brain.log")
brain_log_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))
log.addHandler(brain_log_handler)


# ── Game State Reader ────────────────────────────────────────

def fetch_game_state() -> Optional[dict]:
    """Fetch game state from game_state_server."""
    try:
        req = urllib.request.Request(GAME_STATE_URL, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log.error(f"Failed to fetch game state: {e}")
        return None


def format_state_for_prompt(state: dict) -> str:
    """Format game state into a readable string for Claude."""
    if not state or state.get("status") in ("disconnected", "error", "title_screen"):
        return f"Game status: {state.get('status', 'unknown')} - {state.get('error', state.get('detail', 'N/A'))}"

    lines = []
    lines.append(f"Status: {'IN BATTLE' if state.get('in_battle') else 'Overworld'}")
    lines.append(f"Player: {state.get('player', '?')}")

    location = state.get("location", "?")
    map_group = state.get("map_group", "?")
    map_num = state.get("map_num", "?")
    lines.append(f"Location: {location} (group={map_group}, num={map_num})")

    pos = state.get("position", {})
    lines.append(f"Position: x={pos.get('x', '?')}, y={pos.get('y', '?')}")
    lines.append(f"Badges: {state.get('badges', 0)}/8")
    lines.append(f"Money: ${state.get('money', 0):,}")
    lines.append(f"Playtime: {state.get('playtime', '?')}")

    party = state.get("party", [])
    party_count = state.get("party_count", len(party))
    if party:
        lines.append(f"Party ({party_count} Pokemon):")
        for i, mon in enumerate(party):
            sp = mon.get("species", f"#{mon.get('species_id', '?')}")
            nick = mon.get("nickname", "?")
            lv = mon.get("level", "?")
            hp = mon.get("hp", "?")
            max_hp = mon.get("max_hp", "?")
            lines.append(f"  [{i+1}] {nick} ({sp}) Lv{lv} HP:{hp}/{max_hp}")
    else:
        lines.append(f"Party: EMPTY (0 Pokemon) — you have not received your starter yet!")

    return "\n".join(lines)


# ── System Prompt ────────────────────────────────────────────

SYSTEM_PROMPT = """You are an AI playing Pokemon Emerald on a GBA emulator. You control the game by issuing button presses via JSON commands.

## Available Buttons
A, B, Start, Select, Up, Down, Left, Right, L, R

## Action Format
Reply with ONLY a JSON object. No other text, no explanation, no markdown.

Single button press:
{"action": "press", "button": "A"}

Walk multiple steps in a direction:
{"action": "walk", "direction": "Up", "steps": 3}

Mash A to advance text/dialogue:
{"action": "mash_a", "count": 5}

Button sequence (for menus, complex navigation):
{"action": "sequence", "buttons": ["Down", "A"], "delay_ms": 150}

## Pokemon Emerald Early Game Walkthrough

### Phase 1: Pre-Starter (party_count = 0)
You start in Littleroot Town inside the moving truck. The game flow is:
1. Exit the moving truck (press A through dialogue, walk down to exit)
2. Mom talks to you inside the house — press A through her dialogue
3. Go upstairs, set the clock — press A, then Left/Right to set time, confirm with A
4. Go downstairs, Mom tells you to visit the neighbor — exit the house
5. Visit the house next door (Birch's house/lab area)
6. May/Brendan's room is upstairs — talk to them (or they may not be there)
7. **KEY: Walk NORTH out of Littleroot Town onto Route 101**
8. Professor Birch is being chased by a Zigzagoon — he yells for help
9. Walk to his bag on the ground and press A to open it
10. **Choose MUDKIP** (it's the first option — press A to select, A to confirm)
11. Battle the wild Zigzagoon with Mudkip (just use Tackle — press A repeatedly)
12. After winning, Birch takes you back to his lab

### Phase 2: Post-Starter (party_count >= 1, badges = 0)
1. Birch gives you the Mudkip permanently in the lab
2. Go to Route 101 → Route 103 (north)
3. Battle your Rival (May/Brendan) on Route 103
4. Return to Birch's lab — get the Pokedex
5. Mom gives you Running Shoes
6. Route 102 (west) → Petalburg City
7. Visit Petalburg Gym — meet Dad (Norman), see Wally catch a Ralts
8. Route 104 → Petalburg Woods → Route 104 north → Rustboro City
9. **First Gym: Rustboro City (Rock type, Leader Roxanne)**

### Map Reference
- Littleroot Town: Map group 1, map 4 — your starting town
- Route 101: North of Littleroot — connects to Oldale Town
- Oldale Town: North of Route 101
- Route 103: North of Oldale (rival battle location)
- Route 102: West of Oldale — connects to Petalburg City
- Petalburg City: West end of Route 102 (Dad's gym)

### Littleroot Town Layout (Map 1,4)
- Player's house: center area
- Birch's lab: south part of town
- Exit to Route 101: NORTH edge of town (walk UP to leave town)
- The town is small — just a few buildings

## Navigation Rules
- In the overworld, walk toward your current objective
- If you've been walking in one direction and hitting walls (position not changing), try a different direction
- When you see text/dialogue, mash A to advance through it
- In menus, use Up/Down to navigate, A to select, B to go back
- If stuck in a menu you don't want, press B to exit
- If party_count is 0: your ONLY goal is getting north to Route 101 for the Birch encounter
- If you're at the same position for multiple turns, you're stuck — try a different approach

## Battle Strategy
- Early game: just use your first move (Tackle for Mudkip) — press A to select Fight, A to select first move
- If HP is low, consider using a Potion (go to Bag in battle menu)
- Against rival: Mudkip's Water Gun (learned at level 6) is your best move

## Critical Rules
1. Output ONLY the JSON action. No explanation, no markdown code blocks.
2. Pay attention to your position coordinates — if they don't change after walking, you hit a wall.
3. When party is empty (0 Pokemon), go NORTH from Littleroot to Route 101.
4. Read the game state carefully each turn — adapt your plan based on what changed.
5. Don't keep repeating the same action if nothing is changing — try something different."""


# ── Conversation History ─────────────────────────────────────

class ConversationHistory:
    """Rolling window of recent decisions and their outcomes."""

    def __init__(self, max_entries: int = HISTORY_DEPTH):
        self.entries: collections.deque = collections.deque(maxlen=max_entries)
        self._last_position = None

    def add(self, state_summary: str, action: dict, position: tuple):
        """Record a decision and the game state when it was made."""
        entry = {
            "state": state_summary,
            "action": action,
            "position": position,
        }
        self.entries.append(entry)

    def format_for_prompt(self) -> str:
        """Format recent history for inclusion in the prompt."""
        if not self.entries:
            return "No previous actions yet — this is the first decision."

        lines = ["Recent action history (oldest first):"]
        for i, entry in enumerate(self.entries):
            pos = entry["position"]
            act = json.dumps(entry["action"])
            lines.append(f"  Turn {i+1}: At ({pos[0]},{pos[1]}) — did {act}")

        # Detect if stuck (same position for last 3+ turns)
        if len(self.entries) >= 3:
            recent_positions = [e["position"] for e in list(self.entries)[-3:]]
            if all(p == recent_positions[0] for p in recent_positions):
                lines.append("  ⚠ WARNING: Position has not changed for 3+ turns! You are STUCK. Try a completely different direction or action.")

        return "\n".join(lines)


# ── Claude API ───────────────────────────────────────────────

def call_claude(game_state_text: str, history: ConversationHistory) -> Optional[dict]:
    """Call Claude API to decide the next action."""

    history_text = history.format_for_prompt()

    user_message = (
        f"Current game state:\n{game_state_text}\n\n"
        f"{history_text}\n\n"
        f"What is your next action? Reply with ONLY a JSON object."
    )

    # Try OpenRouter first (Haiku via OpenRouter)
    if OPENROUTER_API_KEY:
        result = _call_openrouter(user_message)
        if result is not None:
            return result
        log.warning("OpenRouter call failed, trying direct Anthropic...")

    # Fallback to direct Anthropic
    if ANTHROPIC_API_KEY:
        result = _call_anthropic(user_message)
        if result is not None:
            return result
        log.warning("Direct Anthropic call also failed")

    log.error("All API providers failed")
    return None


def _call_openrouter(user_message: str) -> Optional[dict]:
    """Call Claude Haiku via OpenRouter."""
    try:
        body = json.dumps({
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 200,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://github.com/deku-emerald-ai",
                "X-Title": "Emerald AI Brain",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        content = data["choices"][0]["message"]["content"].strip()
        return _parse_action(content)

    except Exception as e:
        log.error(f"OpenRouter error: {e}")
        return None


def _call_anthropic(user_message: str) -> Optional[dict]:
    """Call Claude Haiku via direct Anthropic API."""
    try:
        body = json.dumps({
            "model": ANTHROPIC_MODEL,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": user_message},
            ],
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

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        content = data["content"][0]["text"].strip()
        return _parse_action(content)

    except Exception as e:
        log.error(f"Anthropic error: {e}")
        return None


def _parse_action(content: str) -> Optional[dict]:
    """Parse Claude's response into an action dict."""
    content = content.strip()

    # Remove markdown code blocks if present
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

    # Try to find JSON in the response
    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            action = json.loads(content[start:end])
            if isinstance(action, dict) and "action" in action:
                return action
        except json.JSONDecodeError:
            pass

    log.warning(f"Could not parse action from response: {content[:200]}")
    return None


# ── Action Executor ──────────────────────────────────────────

def execute_action(ctrl: MGBAController, action: dict) -> bool:
    """Execute a parsed action via the xdotool controller."""
    action_type = action.get("action", "")

    try:
        if action_type == "press":
            button = action.get("button", "A").lower()
            ctrl.press_button(button)
            return True

        elif action_type == "walk":
            direction = action.get("direction", "Up").lower()
            steps = min(action.get("steps", 1), 10)  # cap at 10 steps
            for _ in range(steps):
                ctrl.press_button(direction)
                time.sleep(0.15)  # small delay between steps
            return True

        elif action_type == "mash_a":
            count = min(action.get("count", 5), 20)  # cap at 20
            for _ in range(count):
                ctrl.press_a()
                time.sleep(0.1)
            return True

        elif action_type == "sequence":
            buttons = action.get("buttons", [])
            delay_ms = action.get("delay_ms", 150)
            if buttons:
                ctrl.sequence([b.lower() for b in buttons[:15]], delay_ms=delay_ms)
            return True

        elif action_type == "hold":
            button = action.get("button", "A").lower()
            ms = action.get("ms", 500)
            ctrl.press_and_hold(button, min(ms, 2000))
            return True

        else:
            log.warning(f"Unknown action type: {action_type}")
            return False

    except Exception as e:
        log.error(f"Action execution error: {e}")
        return False


# ── Main Loop ────────────────────────────────────────────────

def run_brain(tick_rate: float = 2.0, dry_run: bool = False, once: bool = False):
    """Main decision loop."""
    log.info("=" * 50)
    log.info("Emerald Brain v2 starting")
    log.info(f"  Tick rate: {tick_rate}s")
    log.info(f"  Game state: {GAME_STATE_URL}")
    log.info(f"  API: {'OpenRouter' if OPENROUTER_API_KEY else 'Anthropic' if ANTHROPIC_API_KEY else 'NONE'}")
    log.info(f"  Dry run: {dry_run}")
    log.info(f"  History depth: {HISTORY_DEPTH}")
    log.info("=" * 50)

    if not OPENROUTER_API_KEY and not ANTHROPIC_API_KEY:
        log.error("No API key configured! Set OPENROUTER_API_KEY or ANTHROPIC_API_KEY")
        log.error("Checked: .env, ~/.config/zeroclaw/env")
        return

    ctrl = None
    if not dry_run:
        try:
            ctrl = MGBAController()
            log.info(f"Connected to mGBA window {ctrl.window_id}")
        except RuntimeError as e:
            log.error(f"Cannot find mGBA window: {e}")
            log.error("Is mGBA running? Is MGBA_WINDOW_ID set?")
            return

    history = ConversationHistory(max_entries=HISTORY_DEPTH)
    decision_count = 0
    error_streak = 0
    MAX_ERROR_STREAK = 10

    try:
        while True:
            tick_start = time.time()
            decision_count += 1

            # 1. Fetch game state
            state = fetch_game_state()
            if not state:
                log.warning(f"[#{decision_count}] Could not fetch game state")
                error_streak += 1
                if error_streak >= MAX_ERROR_STREAK:
                    log.error(f"Too many consecutive errors ({error_streak}), sleeping 30s...")
                    time.sleep(30)
                    error_streak = 0
                else:
                    time.sleep(tick_rate)
                continue

            # Skip if not in a playable state
            status = state.get("status", "")
            if status in ("disconnected", "error"):
                log.info(f"[#{decision_count}] Not in game: {status} — waiting")
                time.sleep(tick_rate)
                continue

            # Handle title screen — mash A/Start to get through
            if status == "title_screen":
                log.info(f"[#{decision_count}] Title screen — mashing A")
                if ctrl:
                    ctrl.press_a()
                    time.sleep(0.3)
                    ctrl.press_start()
                time.sleep(tick_rate)
                continue

            # 2. Format state for Claude
            state_text = format_state_for_prompt(state)
            pos = state.get("position", {})
            current_pos = (pos.get("x", 0), pos.get("y", 0))

            log.info(f"[#{decision_count}] State: {state.get('location', '?')} "
                     f"pos={current_pos} badges={state.get('badges', 0)} "
                     f"party={state.get('party_count', 0)}")

            # 3. Ask Claude for next action
            action = call_claude(state_text, history)
            if not action:
                log.warning(f"[#{decision_count}] Claude returned no action")
                error_streak += 1
                time.sleep(tick_rate)
                continue

            log.info(f"[#{decision_count}] Decision: {json.dumps(action)}")
            error_streak = 0

            # 4. Record in history
            summary = f"{state.get('location', '?')} pos={current_pos} party={state.get('party_count', 0)}"
            history.add(summary, action, current_pos)

            # 5. Execute the action
            if dry_run:
                log.info(f"[#{decision_count}] DRY RUN — would execute: {action}")
            else:
                success = execute_action(ctrl, action)
                if success:
                    log.info(f"[#{decision_count}] Action executed successfully")
                else:
                    log.warning(f"[#{decision_count}] Action execution failed")

            if once:
                log.info("Single decision mode — exiting")
                break

            # 6. Sleep for remaining tick time
            elapsed = time.time() - tick_start
            sleep_time = max(0, tick_rate - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        log.info("Brain stopped by user")
    finally:
        log.info(f"Brain shut down after {decision_count} decisions")


# ── Entry point ──────────────────────────────────────────────

def main():
    global GAME_STATE_URL

    parser = argparse.ArgumentParser(description="Emerald Brain v2 — Claude decision loop")
    parser.add_argument("--tick", type=float, default=TICK_RATE,
                        help=f"Seconds between decisions (default: {TICK_RATE})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print decisions without executing (skip controller init)")
    parser.add_argument("--once", action="store_true",
                        help="Make one decision then exit")
    parser.add_argument("--state-url", default=GAME_STATE_URL,
                        help=f"Game state server URL (default: {GAME_STATE_URL})")
    args = parser.parse_args()

    GAME_STATE_URL = args.state_url

    run_brain(tick_rate=args.tick, dry_run=args.dry_run, once=args.once)


if __name__ == "__main__":
    main()

"""
Screenshot Reporter — Deterministic Discord screenshot posting for Pokemon AI

Posts screenshots to Discord when interesting game events happen.
ZERO AI token usage — pure state comparison logic.

Events detected:
    - new_map: First visit to a new map
    - badge_gained: Badge count increased
    - starter_obtained: First Pokemon obtained
    - battle_start: Entered battle
    - battle_end: Left battle
    - level_up: Party level sum increased
    - evolution: Species ID changed in party
    - blackout: Money decreased significantly after returning to overworld
    - gym_entered: Entered a map with "Gym" in its name

Usage:
    reporter = ScreenshotReporter(client, channel_id, token)
    # In game loop tick:
    reporter.check(state_dict)
"""

import base64
import json
import logging
import os
import time
from typing import Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore

logger = logging.getLogger(__name__)

# Global rate limit: minimum seconds between ANY Discord post
GLOBAL_COOLDOWN = 30.0

# Per-event cooldowns (seconds)
EVENT_COOLDOWNS = {
    "new_map": 0,
    "badge_gained": 0,
    "starter_obtained": 0,
    "battle_start": 10,
    "battle_end": 10,
    "level_up": 30,
    "evolution": 0,
    "blackout": 60,
    "gym_entered": 0,
}

# Priority order — higher priority events get posted first when multiple fire
EVENT_PRIORITY = [
    "badge_gained",
    "starter_obtained",
    "evolution",
    "gym_entered",
    "new_map",
    "blackout",
    "level_up",
    "battle_start",
    "battle_end",
]


class ScreenshotReporter:
    """Deterministic screenshot reporter — no AI calls, pure state comparison."""

    def __init__(
        self,
        client,
        channel_id: str,
        token: Optional[str] = None,
        game_name: str = "Pokemon",
        enabled: Optional[bool] = None,
    ):
        """
        Args:
            client: mGBAClient instance (must have screenshot_b64() method)
            channel_id: Discord channel ID to post screenshots to
            token: Discord bot token (None = disabled)
            game_name: Game name for log messages
            enabled: Override for enable/disable (default: read from env)
        """
        self.client = client
        self.channel_id = channel_id
        self.token = token
        self.game_name = game_name

        # Check enabled state
        if enabled is not None:
            self.enabled = enabled
        else:
            env_val = os.environ.get("SCREENSHOT_EVENTS_ENABLED", "true")
            self.enabled = env_val.lower() in ("true", "1", "yes")

        if not self.token:
            self.enabled = False
            logger.info("[Reporter] Disabled: no Discord bot token")
        elif not self.enabled:
            logger.info("[Reporter] Disabled via SCREENSHOT_EVENTS_ENABLED=false")
        elif requests is None:
            self.enabled = False
            logger.warning("[Reporter] Disabled: 'requests' library not installed")
        else:
            logger.info(f"[Reporter] Enabled for {game_name} -> channel {channel_id}")

        # State tracking
        self._last_state: dict = {}
        self._seen_maps: set = set()
        self._last_post_time: float = 0.0
        self._event_last_time: dict[str, float] = {}

        # Party tracking (for level_up / evolution detection)
        self._last_party_levels: list[int] = []
        self._last_party_species: list[int] = []
        self._last_money: Optional[int] = None

        # Startup grace period: skip events for the first few ticks
        self._tick_count = 0
        self._grace_ticks = 5

    def check(self, state: dict) -> None:
        """Check current game state for screenshot-worthy events.

        Called once per tick from the game loop. Compares current state
        against previous state to detect events deterministically.

        Args:
            state: Game state dict from client.get_state() with keys like
                   map_group, map_num, scene, party_count, party, badge_count,
                   money, player_name, etc.
        """
        if not self.enabled:
            return

        self._tick_count += 1

        # Skip events during startup grace period (avoids false triggers)
        if self._tick_count <= self._grace_ticks:
            self._update_tracking(state)
            return

        # Detect all events that fired this tick
        events = self._detect_events(state)

        if events:
            # Sort by priority
            events.sort(key=lambda e: EVENT_PRIORITY.index(e[0])
                        if e[0] in EVENT_PRIORITY else 99)

            # Try to post the highest-priority event
            for event_name, caption in events:
                if self._can_post(event_name):
                    self._post_event(event_name, caption)
                    break

        # Update tracking state for next tick
        self._update_tracking(state)

    def _detect_events(self, state: dict) -> list[tuple[str, str]]:
        """Detect all events that fired between last_state and state.

        Returns list of (event_name, caption) tuples.
        """
        events: list[tuple[str, str]] = []
        last = self._last_state

        # Need at least one previous state to compare
        if not last:
            return events

        # --- Map change ---
        current_map_id = self._get_map_id(state)
        last_map_id = self._get_map_id(last)
        map_name = self._get_map_name(state)
        map_changed = current_map_id is not None and current_map_id != last_map_id

        if map_changed:
            # Gym entered (check before new_map to avoid duplicate)
            if map_name and "gym" in map_name.lower():
                events.append(("gym_entered", f"🏟️ Entered {map_name}!"))
            # First visit to this map
            elif current_map_id not in self._seen_maps:
                events.append(("new_map", f"📍 Entered {map_name or f'Map {current_map_id}'}"))

        # --- Badge gained ---
        current_badges = state.get("badge_count", 0)
        last_badges = last.get("badge_count", 0)
        if isinstance(current_badges, int) and isinstance(last_badges, int):
            if current_badges > last_badges:
                events.append(("badge_gained", f"🏅 Badge #{current_badges} earned!"))

        # --- Starter obtained ---
        current_party = state.get("party_count", 0)
        last_party = last.get("party_count", 0)
        if isinstance(current_party, int) and isinstance(last_party, int):
            if last_party == 0 and current_party > 0:
                events.append(("starter_obtained",
                               f"🎮 Got our starter! Party size: {current_party}"))

        # --- Battle transitions ---
        current_scene = state.get("scene", "")
        last_scene = last.get("scene", "")

        if current_scene == "battle" and last_scene != "battle":
            events.append(("battle_start", "⚔️ Battle started!"))
        elif current_scene != "battle" and last_scene == "battle":
            events.append(("battle_end", "✅ Battle ended"))

        # --- Level up ---
        current_levels = self._get_party_levels(state)
        if current_levels and self._last_party_levels:
            current_sum = sum(current_levels)
            last_sum = sum(self._last_party_levels)
            if current_sum > last_sum:
                levels_str = ", ".join(str(lv) for lv in current_levels)
                events.append(("level_up", f"⬆️ Level up! Party levels: {levels_str}"))

        # --- Evolution ---
        current_species = self._get_party_species(state)
        if current_species and self._last_party_species:
            # Only check if party size hasn't changed (to avoid false positives from catching)
            if len(current_species) == len(self._last_party_species):
                for i, (curr, prev) in enumerate(zip(current_species, self._last_party_species)):
                    if curr != prev and curr != 0 and prev != 0:
                        events.append(("evolution", "✨ Evolution!"))
                        break

        # --- Blackout detection ---
        current_money = state.get("money")
        if (current_money is not None and self._last_money is not None
                and isinstance(current_money, (int, float))
                and isinstance(self._last_money, (int, float))):
            # Blackout: scene returned to overworld and money halved
            if (current_scene == "overworld" and last_scene == "battle"
                    and current_money < self._last_money * 0.6
                    and self._last_money > 0):
                events.append(("blackout", "💀 Blacked out..."))

        return events

    def _can_post(self, event_name: str) -> bool:
        """Check if we can post this event (global + per-event cooldowns)."""
        now = time.time()

        # Global cooldown
        if now - self._last_post_time < GLOBAL_COOLDOWN:
            return False

        # Per-event cooldown
        cooldown = EVENT_COOLDOWNS.get(event_name, 30)
        last_event_time = self._event_last_time.get(event_name, 0.0)
        if now - last_event_time < cooldown:
            return False

        return True

    def _post_event(self, event_name: str, caption: str) -> None:
        """Take a screenshot and post it to Discord."""
        now = time.time()

        # Take screenshot
        screenshot_b64 = self._take_screenshot()
        if not screenshot_b64:
            logger.warning(f"[Reporter] Failed to take screenshot for {event_name}")
            return

        # Post to Discord
        success = self._post_to_discord(screenshot_b64, caption)

        if success:
            self._last_post_time = now
            self._event_last_time[event_name] = now
            logger.info(f"[Reporter] Posted: {event_name} — {caption}")
        else:
            logger.warning(f"[Reporter] Discord post failed for {event_name}")

    def _take_screenshot(self) -> Optional[str]:
        """Request a screenshot from the emulator, return base64 PNG string."""
        try:
            # Try screenshot_b64 method first (returns base64 string directly)
            if hasattr(self.client, 'screenshot_b64'):
                result = self.client.screenshot_b64()
                if result:
                    return result

            # Fallback: screenshot to temp file + read via readfile
            if hasattr(self.client, '_send'):
                temp_path = "/tmp/_reporter_screenshot.png"
                resp = self.client._send({"action": "screenshot", "path": temp_path})
                if resp and resp.get("ok"):
                    # Try to read the file back via readfile action
                    file_resp = self.client._send({"action": "readfile", "path": temp_path})
                    if file_resp and file_resp.get("data"):
                        # Convert hex data to base64
                        file_bytes = bytes.fromhex(file_resp["data"])
                        return base64.b64encode(file_bytes).decode("ascii")

            logger.debug("[Reporter] No screenshot method available")
            return None
        except Exception as e:
            logger.warning(f"[Reporter] Screenshot error: {e}")
            return None

    def _post_to_discord(self, screenshot_b64: str, caption: str) -> bool:
        """Post a screenshot to Discord via direct HTTP API call."""
        if requests is None:
            return False

        try:
            image_bytes = base64.b64decode(screenshot_b64)
            response = requests.post(
                f"https://discord.com/api/v10/channels/{self.channel_id}/messages",
                headers={
                    "Authorization": f"Bot {self.token}",
                    "User-Agent": "DiscordBot (https://deku.dev, 1.0)",
                },
                files={"file": ("screenshot.png", image_bytes, "image/png")},
                data={"payload_json": json.dumps({"content": caption})},
                timeout=15,
            )

            if response.status_code in (200, 201):
                return True
            else:
                logger.warning(
                    f"[Reporter] Discord API returned {response.status_code}: "
                    f"{response.text[:200]}"
                )
                return False
        except requests.exceptions.Timeout:
            logger.warning("[Reporter] Discord post timed out")
            return False
        except Exception as e:
            logger.warning(f"[Reporter] Discord post error: {e}")
            return False

    # =========================================================================
    # State helpers
    # =========================================================================

    def _update_tracking(self, state: dict) -> None:
        """Update internal tracking state after processing a tick."""
        # Track seen maps
        map_id = self._get_map_id(state)
        if map_id is not None:
            self._seen_maps.add(map_id)

        # Track party levels and species
        levels = self._get_party_levels(state)
        if levels:
            self._last_party_levels = levels

        species = self._get_party_species(state)
        if species:
            self._last_party_species = species

        # Track money
        money = state.get("money")
        if money is not None and isinstance(money, (int, float)):
            self._last_money = money

        # Store full state for next comparison
        self._last_state = state.copy() if state else {}

    @staticmethod
    def _get_map_id(state: dict) -> Optional[tuple]:
        """Extract a unique map identifier from state."""
        if not state:
            return None

        # Try map_id first (some bridges provide this directly)
        if "map_id" in state:
            return state["map_id"]

        # Construct from map_group + map_num (standard Gen3 format)
        mg = state.get("map_group")
        mn = state.get("map_num")
        if mg is not None and mn is not None:
            return (mg, mn)

        return None

    @staticmethod
    def _get_map_name(state: dict) -> Optional[str]:
        """Extract a human-readable map name from state."""
        # Try direct map_name field
        if "map_name" in state:
            return state["map_name"]

        # Fall back to map ID representation
        mg = state.get("map_group")
        mn = state.get("map_num")
        if mg is not None and mn is not None:
            return f"Map ({mg}, {mn})"

        return None

    @staticmethod
    def _get_party_levels(state: dict) -> list[int]:
        """Extract party Pokemon levels from state."""
        party = state.get("party")
        if not party or not isinstance(party, (list, dict)):
            return []

        levels = []
        # Handle both list (Python) and dict with numeric keys (Lua JSON)
        if isinstance(party, dict):
            items = sorted(party.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0)
            party_list = [v for _, v in items]
        else:
            party_list = party

        for mon in party_list:
            if isinstance(mon, dict):
                lv = mon.get("level", 0)
                if isinstance(lv, (int, float)):
                    levels.append(int(lv))

        return levels

    @staticmethod
    def _get_party_species(state: dict) -> list[int]:
        """Extract party Pokemon species IDs from state."""
        party = state.get("party")
        if not party or not isinstance(party, (list, dict)):
            return []

        species = []
        if isinstance(party, dict):
            items = sorted(party.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0)
            party_list = [v for _, v in items]
        else:
            party_list = party

        for mon in party_list:
            if isinstance(mon, dict):
                sp = mon.get("species", 0)
                if isinstance(sp, (int, float)):
                    species.append(int(sp))

        return species

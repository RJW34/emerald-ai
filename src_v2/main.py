"""
Emerald AI v2 — autonomous Pokemon Emerald player.

Game loop:
  TITLE    → tap Start, then A (New Game), fall into INTRO
  INTRO    → spam A every 5 frames until OVERWORLD (handles Oak, naming, starter)
  OVERWORLD → apply fast-text options, walk north for encounters
  BATTLE   → spam A every 5 frames (advances all dialogue + selects Fight/Move1)

Usage:
  python -m src_v2.main [--rom PATH] [--verbose]
"""

import argparse
import logging
import os
import signal
import sys
import time

from . import save_reader
from .mgba_client import MgbaClient
from .state import State, StateDetector
from .memory_map import (
    SAVE_BLOCK_2_PTR,
    OPTIONS_OFFSET,
    OPTIONS_FAST,
    SAVE_BLOCK_1_PTR,
    PLAYER_X_OFFSET,
    PLAYER_Y_OFFSET,
    VALID_SAVE_PTR_MIN,
    VALID_SAVE_PTR_MAX,
)

DEFAULT_ROM   = "/home/ryan/roms/emerald.gba"
DEFAULT_STATE = "/home/ryan/roms/states/emerald_slot1.state"

# ── logging setup ─────────────────────────────────────────────────────────────

def _silence_c_stdout():
    """
    Redirect C-level file descriptor 1 (where mGBA writes its noise) to
    /dev/null, then rewire Python's sys.stdout to the old fd so the Python
    logging module still reaches the terminal / log file.
    """
    import os
    try:
        saved_fd = os.dup(1)                            # keep a copy of fd 1
        devnull  = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 1)                              # fd 1 → /dev/null
        os.close(devnull)
        sys.stdout = os.fdopen(saved_fd, "w", 1)        # Python stdout → old fd
    except Exception:
        pass  # if it fails, we still run — just with noisy output


def _setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    datefmt = "%H:%M:%S"
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, stream=sys.stdout)


log = logging.getLogger(__name__)

# ── navigation helpers ─────────────────────────────────────────────────────────

_NAV_DIRS = ["Up", "Right", "Left", "Down"]  # priority order for route walking


class Navigator:
    """
    Directed walk: prefer north, rotate direction when stuck.
    Reads player position via memory to detect if movement happened.
    """

    def __init__(self, client: MgbaClient):
        self._c = client
        self._dir_idx = 0       # index into _NAV_DIRS
        self._stuck_ticks = 0
        self._last_pos = (-1, -1)

    def _pos(self):
        sb1 = self._c.r32(SAVE_BLOCK_1_PTR)
        if not (VALID_SAVE_PTR_MIN <= sb1 < VALID_SAVE_PTR_MAX):
            return (-1, -1)
        x = self._c.r16(sb1 + PLAYER_X_OFFSET)
        y = self._c.r16(sb1 + PLAYER_Y_OFFSET)
        return (x, y)

    def step(self):
        direction = _NAV_DIRS[self._dir_idx]
        self._c.hold(direction, frames=8)
        self._c.run(4)

        pos = self._pos()
        if pos == self._last_pos:
            self._stuck_ticks += 1
            if self._stuck_ticks >= 5:
                self._dir_idx = (self._dir_idx + 1) % len(_NAV_DIRS)
                self._stuck_ticks = 0
                log.debug(f"Stuck — rotating to {_NAV_DIRS[self._dir_idx]}")
        else:
            self._stuck_ticks = 0
            self._dir_idx = 0   # reset to north on successful move

        self._last_pos = pos


# ── main AI ───────────────────────────────────────────────────────────────────

class EmeraldAI:
    def __init__(self, rom_path: str, state_path: str = ""):
        self.rom_path   = rom_path
        self.state_path = state_path
        self._client = MgbaClient(rom_path)
        self._detector = StateDetector(self._client)
        self._nav = Navigator(self._client)

        self._running = False
        self._tick = 0

        # Title screen state machine
        self._title_step = 0
        self._title_delay = 0

        # Options applied flag (set once per session on first OVERWORLD tick)
        self._options_applied = False
        self._options_recheck = 0   # countdown for periodic re-apply

        # State tracking
        self._state = State.TITLE
        self._prev_state = State.TITLE
        self._ticks_in_state = 0

        # Intro: spam A counter
        self._intro_spam = 0

        # Battle: spam A counter
        self._battle_spam = 0

        # Save file reader — detect .sav path
        if os.path.exists("/home/ryan/roms/emerald.sav"):
            self._sav_path = "/home/ryan/roms/emerald.sav"
        else:
            self._sav_path = "/home/ryan/roms/emerald.gba.sav"
        self._last_game_state = None
        self._save_cooldown = 0  # ticks until next save allowed

    # ── options ───────────────────────────────────────────────────────────────

    def _apply_options(self):
        """Write fast-text + no-animations byte directly to SaveBlock2."""
        sb2 = self._client.r32(SAVE_BLOCK_2_PTR)
        if not (VALID_SAVE_PTR_MIN <= sb2 < VALID_SAVE_PTR_MAX):
            log.warning("SaveBlock2 pointer invalid — cannot apply options yet")
            return
        addr = sb2 + OPTIONS_OFFSET
        current = self._client.r8(addr)
        if current != OPTIONS_FAST:
            self._client.w8(addr, OPTIONS_FAST)
            log.info(f"Options set → 0x{OPTIONS_FAST:02X} (fast text, no anims) at 0x{addr:08X}")
        self._options_applied = True

    # ── title screen ──────────────────────────────────────────────────────────

    def _handle_title(self):
        """
        Simple state machine:
          0 → wait for title to settle (30 frames)
          1 → tap Start
          2 → wait 15 frames for menu
          3 → tap A (selects New Game — no save loaded so it's the only option)
          4 → fall through to INTRO handling
        """
        if self._title_delay > 0:
            self._title_delay -= 1
            self._client.run(1)
            return

        if self._title_step == 0:
            log.info("Title screen — waiting for intro to settle...")
            self._title_delay = 30
            self._title_step = 1

        elif self._title_step == 1:
            log.info("Tapping Start")
            self._client.tap("Start", hold=3, gap=15)
            self._title_step = 2

        elif self._title_step == 2:
            log.info("Selecting New Game (tapping A)")
            self._client.tap("A", hold=3, gap=20)
            self._title_step = 3

        else:
            # Keep tapping A to advance any remaining title screen text
            self._client.tap("A", hold=2, gap=5)

    # ── intro spam ────────────────────────────────────────────────────────────

    def _handle_intro(self):
        """Spam A every 5 frames through Oak intro, naming, starter selection."""
        self._intro_spam += 1
        if self._intro_spam >= 5:
            self._client.tap("A", hold=2, gap=3)
            self._intro_spam = 0
        else:
            self._client.run(1)
        # Heartbeat every 600 ticks in intro state
        if self._ticks_in_state % 600 == 0 and self._ticks_in_state > 0:
            log.info(f"INTRO tick {self._tick} — still pressing A through intro")

    # ── overworld ─────────────────────────────────────────────────────────────

    def _handle_overworld(self):
        """Apply options on first entry, then walk north hunting encounters.
        Also presses A periodically to clear any lingering intro dialogue."""
        if not self._options_applied:
            self._apply_options()

        # Periodically re-apply options (every ~200 ticks)
        self._options_recheck -= 1
        if self._options_recheck <= 0:
            self._apply_options()
            self._options_recheck = 200

        # Heartbeat log every 600 ticks (~30s) so external watchers know we're alive
        if self._ticks_in_state % 600 == 0 and self._ticks_in_state > 0:
            pos = self._nav._pos()
            log.info(f"OVERWORLD tick {self._tick} — pos={pos}")

        # Periodic in-game save + parse (every 5000 overworld ticks)
        if self._save_cooldown > 0:
            self._save_cooldown -= 1
        if self._ticks_in_state > 0 and self._ticks_in_state % 5000 == 0 and self._save_cooldown <= 0:
            self._save_game()
            self._save_cooldown = 500  # prevent rapid re-saves after state transitions

        # Walk north to find wild encounters
        self._nav.step()

        # Every 15 ticks: press A once to advance any dialogue that might still
        # be open (lingering intro text, NPCs, yes/no prompts, etc.)
        if self._ticks_in_state % 15 == 0:
            self._client.tap("A", hold=2, gap=2)

    # ── battle ────────────────────────────────────────────────────────────────

    def _handle_battle(self):
        """
        Spam A every 5 frames.
        This advances all battle dialogue and selects:
          - FIGHT (already highlighted) with A
          - Move 1 (already highlighted) with A
        Works for early-game Treecko/Mudkip vs Route 101 Poochyena.
        """
        self._battle_spam += 1
        if self._battle_spam >= 5:
            self._client.tap("A", hold=2, gap=3)
            self._battle_spam = 0
        else:
            self._client.run(1)

    # ── save game & parse ────────────────────────────────────────────────────

    def _save_game(self):
        """
        Trigger an in-game save, wait for the .sav to be written,
        then parse it with PKsinew and store the result.
        Menu order: POKEDEX / POKEMON / BAG / POKEMON CONTEST / TRAINER CARD / SAVE
        So: Start → Down ×5 → A (select SAVE) → wait → A (confirm Yes) → wait.
        """
        log.info("Saving game...")
        c = self._client

        # Open menu
        c.tap("Start", hold=3, gap=20)

        # Navigate down 5 times to SAVE
        for _ in range(5):
            c.tap("Down", hold=2, gap=4)

        # Select SAVE
        c.tap("A", hold=3, gap=60)

        # Confirm "Yes" (already highlighted)
        c.tap("A", hold=3, gap=30)

        # Wait for save to write to disk (~120 frames)
        c.run(120)

        # Close any remaining save confirmation dialogue
        c.tap("A", hold=2, gap=10)
        c.tap("B", hold=2, gap=10)

        # Parse the .sav file
        result = save_reader.read_save(self._sav_path)
        if result:
            self._last_game_state = result
            trainer = result["trainer"]
            party_names = [f"{p['nickname']}(Lv{p['level']})" for p in result["party"]]
            log.info(
                f"Save parsed — {trainer['name']}, "
                f"badges: {trainer['badges_count']}/8 {trainer.get('badges', [])}, "
                f"party: {party_names}"
            )
            if result["trade_evos_ready"]:
                names = [f"{t['name']}({t['nickname']})" for t in result["trade_evos_ready"]]
                log.info(f"Trade evos ready: {names}")
        else:
            log.warning("Save file parse returned None (blank or missing .sav)")

    # ── main loop ─────────────────────────────────────────────────────────────

    def _on_state_change(self, new: State):
        log.info(f"State: {self._state.name} → {new.name}  (tick {self._tick})")
        if new == State.OVERWORLD and self._state != State.OVERWORLD:
            self._options_applied = False   # re-apply options on each overworld entry
        self._ticks_in_state = 0

    def run(self):
        if not self._client.connect():
            log.error("Failed to connect — check ROM path")
            return

        if self._client.game_code != "BPEE":
            log.warning(f"Expected BPEE, got {self._client.game_code!r}")

        log.info("=" * 50)
        log.info("Emerald AI v2 — starting")
        log.info("=" * 50)

        # Load save state if provided — drops game directly to Route 101 (or wherever
        # the state was saved), bypassing title screen and Oak intro entirely.
        if self.state_path:
            if self._client.load_state_file(self.state_path):
                # Let the emulator settle for a few frames after state load
                self._client.run(30)
                self._state = State.OVERWORLD
                self._prev_state = State.OVERWORLD
                log.info("State loaded — jumping straight to OVERWORLD")
            else:
                log.warning("State load failed — falling back to title screen flow")

        self._running = True

        def _stop(sig, frame):
            log.info("Stopping...")
            self._running = False

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        while self._running:
            new_state = self._detector.detect()

            if new_state != self._state:
                self._on_state_change(new_state)
                self._state = new_state

            self._ticks_in_state += 1
            self._tick += 1

            if self._state == State.TITLE:
                self._handle_title()
            elif self._state == State.INTRO:
                self._handle_intro()
            elif self._state == State.OVERWORLD:
                self._handle_overworld()
            elif self._state == State.BATTLE:
                self._handle_battle()

            # Brief sleep to avoid pegging CPU (optional — remove for max speed)
            time.sleep(0.05)

        self._client.close()
        log.info("Emerald AI stopped")


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Emerald AI v2")
    parser.add_argument("--rom",   default=DEFAULT_ROM,   help="Path to emerald.gba")
    parser.add_argument("--state", default=DEFAULT_STATE, help="Save state to load on boot (.state file), empty string to disable")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    _silence_c_stdout()      # redirect C fd 1 to /dev/null BEFORE logging setup
    _setup_logging(args.verbose)
    EmeraldAI(args.rom, state_path=args.state).run()


if __name__ == "__main__":
    main()

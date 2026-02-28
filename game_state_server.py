#!/usr/bin/env python3
"""
Emerald AI Game State Server

Reads live Pokemon Emerald game state from a running mGBA instance
via /proc/PID/mem and serves it as JSON on port 8776.

Also pushes updates to the stream server's /emerald-update endpoint
so the OBS Emerald Brain panel displays live game data.

Requirements:
  - kernel.yama.ptrace_scope = 0 (set via sysctl)
  - mGBA running Pokemon Emerald

Endpoints:
  GET /state  -> full game state JSON
  GET /health -> {"ok": true}

Architecture:
  mGBA maps GBA memory into a ~384KB anonymous rw-p region:
    - Offset 0x00000: EWRAM (256KB, GBA 0x02000000-0x0203FFFF)
    - Offset 0x58000: IWRAM (32KB, GBA 0x03000000-0x03007FFF)
  The ROM is in a separate 16MB region.
  We identify the correct region by finding IWRAM save block pointers
  at a known offset (0x5D8C from IWRAM base).
"""

from __future__ import annotations

import json
import logging
import os
import struct
import subprocess
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
import urllib.request
import urllib.error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("emerald-state")

PORT = int(os.environ.get("EMERALD_STATE_PORT", "8776"))
STREAM_SERVER_URL = os.environ.get(
    "STREAM_UPDATE_URL", "http://localhost:8777/emerald-update"
)
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "2.0"))

# ---------------------------------------------------------------------------
# Gen 3 Character Decoding
# ---------------------------------------------------------------------------
GEN3_CHARS: dict[int, str] = {
    0xBB: "A", 0xBC: "B", 0xBD: "C", 0xBE: "D", 0xBF: "E",
    0xC0: "F", 0xC1: "G", 0xC2: "H", 0xC3: "I", 0xC4: "J",
    0xC5: "K", 0xC6: "L", 0xC7: "M", 0xC8: "N", 0xC9: "O",
    0xCA: "P", 0xCB: "Q", 0xCC: "R", 0xCD: "S", 0xCE: "T",
    0xCF: "U", 0xD0: "V", 0xD1: "W", 0xD2: "X", 0xD3: "Y",
    0xD4: "Z", 0xD5: "a", 0xD6: "b", 0xD7: "c", 0xD8: "d",
    0xD9: "e", 0xDA: "f", 0xDB: "g", 0xDC: "h", 0xDD: "i",
    0xDE: "j", 0xDF: "k", 0xE0: "l", 0xE1: "m", 0xE2: "n",
    0xE3: "o", 0xE4: "p", 0xE5: "q", 0xE6: "r", 0xE7: "s",
    0xE8: "t", 0xE9: "u", 0xEA: "v", 0xEB: "w", 0xEC: "x",
    0xED: "y", 0xEE: "z", 0x00: " ",
    0xA1: "0", 0xA2: "1", 0xA3: "2", 0xA4: "3", 0xA5: "4",
    0xA6: "5", 0xA7: "6", 0xA8: "7", 0xA9: "8", 0xAA: "9",
    0xAB: "!", 0xAC: "?", 0xAD: ".", 0xAE: "-", 0xB4: "'",
}


def decode_gen3(data: bytes) -> str:
    out: list[str] = []
    for b in data:
        if b == 0xFF:
            break
        out.append(GEN3_CHARS.get(b, ""))
    return "".join(out).strip()


# ---------------------------------------------------------------------------
# Emerald Map Names (group, number) -> name
# ---------------------------------------------------------------------------
MAP_NAMES: dict[tuple[int, int], str] = {
    (0, 0): "Petalburg City", (0, 1): "Slateport City", (0, 2): "Mauville City",
    (0, 3): "Rustboro City", (0, 4): "Fortree City", (0, 5): "Lilycove City",
    (0, 6): "Mossdeep City", (0, 7): "Sootopolis City", (0, 8): "Ever Grande City",
    (0, 9): "Littleroot Town", (0, 10): "Oldale Town", (0, 11): "Dewford Town",
    (0, 12): "Lavaridge Town", (0, 13): "Fallarbor Town", (0, 14): "Verdanturf Town",
    (0, 15): "Pacifidlog Town",
    (0, 16): "Route 101", (0, 17): "Route 102", (0, 18): "Route 103",
    (0, 19): "Route 104", (0, 20): "Route 105", (0, 21): "Route 106",
    (0, 22): "Route 107", (0, 23): "Route 108", (0, 24): "Route 109",
    (0, 25): "Route 110", (0, 26): "Route 111", (0, 27): "Route 112",
    (0, 28): "Route 113", (0, 29): "Route 114", (0, 30): "Route 115",
    (0, 31): "Route 116", (0, 32): "Route 117", (0, 33): "Route 118",
    (0, 34): "Route 119", (0, 35): "Route 120", (0, 36): "Route 121",
    (0, 37): "Route 122", (0, 38): "Route 123", (0, 39): "Route 124",
    (0, 40): "Route 125", (0, 41): "Route 126", (0, 42): "Route 127",
    (0, 43): "Route 128", (0, 44): "Route 129", (0, 45): "Route 130",
    (0, 46): "Route 131", (0, 47): "Route 132", (0, 48): "Route 133",
    (0, 49): "Route 134",
    (24, 0): "Meteor Falls", (24, 2): "Rusturf Tunnel",
    (24, 4): "Granite Cave 1F", (24, 7): "Petalburg Woods",
    (24, 10): "Mt. Chimney", (24, 11): "Jagged Pass",
    (24, 15): "Fiery Path", (24, 22): "Seafloor Cavern",
    (24, 37): "Victory Road 1F", (24, 40): "Shoal Cave",
    (24, 44): "New Mauville", (24, 48): "Sky Pillar 1F",
    (25, 0): "Pokemon League",
    (25, 1): "Elite Four - Sidney", (25, 2): "Elite Four - Phoebe",
    (25, 3): "Elite Four - Glacia", (25, 4): "Elite Four - Drake",
    (25, 5): "Champion - Wallace",
    (26, 0): "Player's House 1F", (26, 1): "Player's House 2F",
    (26, 2): "Rival's House", (26, 3): "Birch's Lab",
}

SPECIES_NAMES: dict[int, str] = {
    1: "Bulbasaur", 2: "Ivysaur", 3: "Venusaur", 4: "Charmander",
    5: "Charmeleon", 6: "Charizard", 7: "Squirtle", 8: "Wartortle",
    9: "Blastoise", 25: "Pikachu", 26: "Raichu",
    150: "Mewtwo", 151: "Mew",
    252: "Treecko", 253: "Grovyle", 254: "Sceptile",
    255: "Torchic", 256: "Combusken", 257: "Blaziken",
    258: "Mudkip", 259: "Marshtomp", 260: "Swampert",
    261: "Poochyena", 262: "Mightyena", 263: "Zigzagoon", 264: "Linoone",
    265: "Wurmple", 266: "Silcoon", 267: "Beautifly",
    268: "Cascoon", 269: "Dustox", 270: "Lotad", 271: "Lombre",
    272: "Ludicolo", 273: "Seedot", 274: "Nuzleaf", 275: "Shiftry",
    276: "Taillow", 277: "Swellow", 278: "Wingull", 279: "Pelipper",
    280: "Ralts", 281: "Kirlia", 282: "Gardevoir",
    285: "Shroomish", 286: "Breloom", 287: "Slakoth", 288: "Vigoroth",
    289: "Slaking", 293: "Whismur", 294: "Loudred", 295: "Exploud",
    296: "Makuhita", 297: "Hariyama", 300: "Skitty", 302: "Sableye",
    303: "Mawile", 304: "Aron", 305: "Lairon", 306: "Aggron",
    309: "Electrike", 310: "Manectric", 315: "Roselia",
    318: "Carvanha", 319: "Sharpedo", 320: "Wailmer", 321: "Wailord",
    322: "Numel", 323: "Camerupt", 324: "Torkoal",
    328: "Trapinch", 329: "Vibrava", 330: "Flygon",
    333: "Swablu", 334: "Altaria", 335: "Zangoose", 336: "Seviper",
    339: "Barboach", 340: "Whiscash", 341: "Corphish", 342: "Crawdaunt",
    343: "Baltoy", 344: "Claydol", 349: "Feebas", 350: "Milotic",
    352: "Kecleon", 359: "Absol",
    371: "Bagon", 372: "Shelgon", 373: "Salamence",
    374: "Beldum", 375: "Metang", 376: "Metagross",
    377: "Regirock", 378: "Regice", 379: "Registeel",
    380: "Latias", 381: "Latios",
    382: "Kyogre", 383: "Groudon", 384: "Rayquaza",
    385: "Jirachi", 386: "Deoxys",
    41: "Zubat", 42: "Golbat", 43: "Oddish",
    63: "Abra", 64: "Kadabra", 65: "Alakazam",
    66: "Machop", 67: "Machoke", 68: "Machamp",
    72: "Tentacool", 73: "Tentacruel",
    74: "Geodude", 75: "Graveler", 76: "Golem",
    81: "Magnemite", 82: "Magneton",
    129: "Magikarp", 130: "Gyarados", 169: "Crobat",
    183: "Marill", 184: "Azumarill",
}

# Badge flag positions in event flags
BADGE_FLAGS = [0x807, 0x808, 0x809, 0x80A, 0x80B, 0x80C, 0x80D, 0x80E]
BADGE_NAMES = ["Stone", "Knuckle", "Dynamo", "Heat", "Balance", "Feather", "Mind", "Rain"]

# Memory layout constants
# Within the ~384KB GBA memory block:
EWRAM_OFFSET = 0x00000   # EWRAM starts at beginning (256KB)
IWRAM_OFFSET = 0x58000   # IWRAM starts at this offset (32KB)

# IWRAM offsets (from IWRAM base, i.e., GBA 0x03000000)
SAVE_BLOCK_1_PTR_OFF = 0x5D8C
SAVE_BLOCK_2_PTR_OFF = 0x5D90
POKEMON_STORAGE_PTR_OFF = 0x5D94
CALLBACK1_OFF = 0x22C0
CALLBACK2_OFF = 0x22C4

# Save Block 1 offsets (from SB1 pointer value)
SB1_PLAYER_X = 0x0
SB1_PLAYER_Y = 0x2
SB1_MAP_GROUP = 0x4
SB1_MAP_NUM = 0x5
SB1_PARTY_COUNT = 0x234
SB1_PARTY_DATA = 0x238
SB1_MONEY = 0x0490
SB1_SECURITY_KEY = 0x0AF8
SB1_EVENT_FLAGS = 0x1270

# Save Block 2 offsets
SB2_PLAYER_NAME = 0x0
SB2_PLAYER_GENDER = 0x8
SB2_PLAY_TIME = 0xE

# Battle RAM (EWRAM offsets, i.e., subtract 0x02000000)
BATTLE_TYPE_FLAGS_OFF = 0x22FEC
BATTLE_MONS_OFF = 0x24084
BATTLE_MON_SIZE = 88

# Party struct
PARTY_MON_SIZE = 100
PKM_NICKNAME = 0x8
PKM_LEVEL = 0x54
PKM_HP = 0x56
PKM_MAX_HP = 0x58


# ---------------------------------------------------------------------------
# mGBA Process Memory Reader
# ---------------------------------------------------------------------------
class MgbaMemoryReader:
    """Reads GBA memory from a running mGBA process via /proc/PID/mem."""

    def __init__(self):
        self.pid: Optional[int] = None
        self.gba_block_base: Optional[int] = None  # Host addr of the GBA memory block
        self.rom_base: Optional[int] = None
        self.enc_offset: int = 0  # SaveBlock encryption/relocation offset
        self._last_scan = 0.0
        self._scan_interval = 5.0

    @property
    def ewram_host(self) -> Optional[int]:
        return self.gba_block_base + EWRAM_OFFSET if self.gba_block_base else None

    @property
    def iwram_host(self) -> Optional[int]:
        iwram_off = getattr(self, "_iwram_offset", IWRAM_OFFSET)
        return self.gba_block_base + iwram_off if self.gba_block_base else None

    def _find_mgba_pids(self) -> list[int]:
        """Find all running mGBA-qt PIDs."""
        env_pid = os.environ.get("MGBA_PID")
        if env_pid:
            return [int(env_pid)]
        try:
            result = subprocess.run(
                ["pgrep", "-x", "mgba-qt"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split("\n")
                return [int(p) for p in pids if p.strip()]
        except Exception:
            pass
        return []

    def _find_mgba_pid(self) -> Optional[int]:
        """Compat wrapper — returns first PID found."""
        pids = self._find_mgba_pids()
        return pids[0] if pids else None

    def _raw_read(self, pid: int, addr: int, length: int) -> bytes:
        with open(f"/proc/{pid}/mem", "rb") as f:
            f.seek(addr)
            return f.read(length)

    def _scan_memory_regions(self, pid: int) -> bool:
        """Find the GBA memory block in mGBA's process memory.
        
        Strategy: Look for anonymous rw-p regions of 256KB-512KB where
        offset IWRAM_OFFSET + SAVE_BLOCK_1_PTR_OFF contains three
        consecutive pointers into the EWRAM range (0x02000000-0x0203FFFF).
        """
        try:
            with open(f"/proc/{pid}/maps") as f:
                lines = f.readlines()
        except (FileNotFoundError, PermissionError):
            return False

        candidates = []
        for line in lines:
            parts = line.split()
            if len(parts) < 5:
                continue
            perm = parts[1]
            if "rw" not in perm:
                continue
            addr_range = parts[0]
            start_s, end_s = addr_range.split("-")
            start = int(start_s, 16)
            end = int(end_s, 16)
            size = end - start
            label = " ".join(parts[5:]).strip() if len(parts) > 5 else ""

            # Look for the GBA memory block: anon rw-p
            # Two known layouts:
            #   ~384KB: EWRAM(256KB) + gap + IWRAM(32KB) at offset 0x58000
            #   ~288KB: EWRAM(256KB) + IWRAM(32KB) contiguous (no gap)
            if (270 * 1024 <= size <= 512 * 1024 and 
                    (not label or label == "[heap]") and
                    "rw" in perm):
                candidates.append((start, size))

            # Also find ROM
            if "emerald" in label.lower() and size >= 1024 * 1024:
                self.rom_base = start

        # Check each candidate for the IWRAM signature
        for start, size in candidates:
            # Layout A: IWRAM at offset 0x58000 (384KB block)
            # Layout B: IWRAM at offset 0x40000 (288KB block, EWRAM+IWRAM contiguous)
            for iwram_off in [IWRAM_OFFSET, 0x40000]:
                check_offset = iwram_off + SAVE_BLOCK_1_PTR_OFF
                if check_offset + 12 > size:
                    continue
                try:
                    data = self._raw_read(pid, start + check_offset, 12)
                    sb1, sb2, storage = struct.unpack("<III", data)
                    if (0x02000000 <= sb1 <= 0x0203FFFF and
                            0x02000000 <= sb2 <= 0x0203FFFF and
                            0x02000000 <= storage <= 0x0203FFFF):
                        # For layout B, adjust gba_block_base so EWRAM is at offset 0
                        if iwram_off == 0x40000:
                            # This is a 288KB block: EWRAM at start, IWRAM at start+0x40000
                            # Set gba_block_base = start (EWRAM base)
                            # But IWRAM_OFFSET is 0x58000, so we override via a flag
                            self.gba_block_base = start
                            self._iwram_offset = 0x40000  # Override for this layout
                        else:
                            self.gba_block_base = start
                            self._iwram_offset = IWRAM_OFFSET
                        log.info(
                            f"Found GBA memory block at 0x{start:x} ({size//1024}KB) "
                            f"layout={'288KB' if iwram_off==0x40000 else '384KB'} "
                            f"SB1=0x{sb1:08X} SB2=0x{sb2:08X}"
                        )
                        return True
                except Exception:
                    continue

        # Broader scan: check all rw regions 
        for line in lines:
            parts = line.split()
            if len(parts) < 5:
                continue
            perm = parts[1]
            if "rw" not in perm:
                continue
            addr_range = parts[0]
            start_s, end_s = addr_range.split("-")
            start = int(start_s, 16)
            end = int(end_s, 16)
            size = end - start
            label = " ".join(parts[5:]).strip() if len(parts) > 5 else ""

            if "i915" in label or ".so" in label:
                continue
            if size < 384 * 1024 or size > 4 * 1024 * 1024:
                continue

            # Try multiple IWRAM offsets (page-aligned)
            for iwram_off in range(0x40000, min(size - 0x8000, 0x100000), 0x1000):
                check_addr = start + iwram_off + SAVE_BLOCK_1_PTR_OFF
                try:
                    data = self._raw_read(pid, check_addr, 12)
                    sb1, sb2, storage = struct.unpack("<III", data)
                    if (0x02000000 <= sb1 <= 0x0203FFFF and
                            0x02000000 <= sb2 <= 0x0203FFFF and
                            0x02000000 <= storage <= 0x0203FFFF):
                        # Verify: EWRAM base would be at start + (iwram_off - IWRAM_OFFSET)
                        ewram_start = start + (iwram_off - IWRAM_OFFSET)
                        self.gba_block_base = ewram_start
                        log.info(
                            f"Found GBA memory (broad scan) at 0x{ewram_start:x} "
                            f"IWRAM at +0x{iwram_off:x} in region 0x{start:x} "
                            f"SB1=0x{sb1:08X} SB2=0x{sb2:08X}"
                        )
                        return True
                except Exception:
                    continue

        # Find ROM if not found yet
        if self.rom_base is None:
            for line in lines:
                parts = line.split()
                if len(parts) < 5:
                    continue
                addr_range = parts[0]
                start_s, end_s = addr_range.split("-")
                start = int(start_s, 16)
                end = int(end_s, 16)
                size = end - start
                perm = parts[1]
                if size == 16 * 1024 * 1024 and "rw" in perm:
                    try:
                        data = self._raw_read(pid, start + 0xA0, 16)
                        if b"BPEE" in data:
                            self.rom_base = start
                            log.info(f"Found ROM at 0x{start:x}")
                    except Exception:
                        pass

        return False

    def connect(self) -> bool:
        now = time.time()
        if now - self._last_scan < self._scan_interval:
            return self.is_connected()
        self._last_scan = now

        # If already connected and PID is alive, keep it
        if self.pid and self.gba_block_base is not None:
            try:
                os.kill(self.pid, 0)
                return True
            except OSError:
                self.pid = None
                self.gba_block_base = None
                self.enc_offset = 0

        # Try all mGBA PIDs and find one with valid game state (not title screen)
        pids = self._find_mgba_pids()
        if not pids:
            self.pid = None
            self.gba_block_base = None
            return False

        log.info(f"Found {len(pids)} mGBA PID(s): {pids}")

        best_pid = None
        for pid in pids:
            log.info(f"Trying PID {pid}...")
            if self._scan_memory_regions(pid):
                self.pid = pid
                # Quick check: is this a title screen or actual game?
                try:
                    state = self.read_game_state()
                    status = state.get("status", "")
                    player = state.get("player", "")
                    if status not in ("disconnected", "error", "title_screen") and player:
                        log.info(f"PID {pid}: in-game player={player} — using this instance")
                        return True
                    else:
                        log.info(f"PID {pid}: status={status} — skipping (not in-game)")
                        best_pid = best_pid or pid  # Keep as fallback
                except Exception as e:
                    log.warning(f"PID {pid}: state read error: {e}")
            else:
                log.warning(f"PID {pid}: could not find GBA memory regions")

        # Fallback: use any PID we could at least scan
        if best_pid:
            log.info(f"No in-game instance found, falling back to PID {best_pid}")
            self._scan_memory_regions(best_pid)
            self.pid = best_pid
            return True

        return False

    def is_connected(self) -> bool:
        if self.pid is None or self.gba_block_base is None:
            return False
        try:
            os.kill(self.pid, 0)
            return True
        except OSError:
            self.pid = None
            self.gba_block_base = None
            return False

    def _read(self, host_addr: int, length: int) -> bytes:
        if self.pid is None:
            raise RuntimeError("Not connected")
        return self._raw_read(self.pid, host_addr, length)

    def _read_ewram(self, ewram_offset: int, length: int) -> bytes:
        """Read from EWRAM by offset (0x00000-0x3FFFF)."""
        return self._read(self.ewram_host + ewram_offset, length)

    def _read_iwram(self, iwram_offset: int, length: int) -> bytes:
        """Read from IWRAM by offset (0x00000-0x07FFF)."""
        return self._read(self.iwram_host + iwram_offset, length)

    def _read_ewram_u8(self, off: int) -> int:
        return self._read_ewram(off, 1)[0]

    def _read_ewram_u16(self, off: int) -> int:
        return struct.unpack("<H", self._read_ewram(off, 2))[0]

    def _read_ewram_u32(self, off: int) -> int:
        return struct.unpack("<I", self._read_ewram(off, 4))[0]

    def _read_iwram_u32(self, off: int) -> int:
        return struct.unpack("<I", self._read_iwram(off, 4))[0]

    def read_game_state(self) -> dict:
        """Read full game state from mGBA."""
        if not self.is_connected():
            return {"status": "disconnected", "error": "mGBA not connected"}

        try:
            # Read save block pointers from IWRAM
            sb1_ptr = self._read_iwram_u32(SAVE_BLOCK_1_PTR_OFF)
            sb2_ptr = self._read_iwram_u32(SAVE_BLOCK_2_PTR_OFF)
            cb1 = self._read_iwram_u32(CALLBACK1_OFF)
            cb2 = self._read_iwram_u32(CALLBACK2_OFF)

            sb1_valid = 0x02000000 <= sb1_ptr <= 0x0203FFFF
            sb2_valid = 0x02000000 <= sb2_ptr <= 0x0203FFFF

            if not sb1_valid or not sb2_valid:
                return {
                    "status": "title_screen",
                    "game": "Pokemon Emerald",
                    "detail": "Save blocks not initialized",
                    "mgba_pid": self.pid,
                }

            # Resolve the SaveBlock encryption/relocation offset.
            # Emerald's SetSaveBlocksPointers() relocates SaveBlocks in the EWRAM
            # heap by a random offset. The IWRAM global pointers store the BASE
            # (pre-offset) addresses. We must scan EWRAM to find where the data
            # actually lives, then compute enc_offset = real_addr - base_addr.
            # We cache this offset; it only changes on game restart.
            enc_offset = self.enc_offset
            try:
                ewram_data = self._read_ewram(0, 0x40000)
                # Search for player name in EWRAM heap (upper half, 0x20000+)
                NAME_MIN = 3  # At least 3 consecutive valid Gen3 uppercase chars
                GEN3_UP = set(range(0xBB, 0xD5))  # A-Z
                for scan_start in range(0x20000, 0x3FFF8):
                    b = ewram_data[scan_start:scan_start+NAME_MIN]
                    if all(x in GEN3_UP for x in b):
                        # Find the terminator
                        end = scan_start + NAME_MIN
                        while end < scan_start + 10 and end < len(ewram_data):
                            if ewram_data[end] == 0xFF:
                                break
                            if ewram_data[end] not in GEN3_UP:
                                end = 0
                                break
                            end += 1
                        else:
                            end = 0
                        if not end:
                            continue
                        # Validate: check gender (0/1) and playtime (sane hours/mins/secs)
                        if scan_start + 0x12 >= len(ewram_data):
                            continue
                        gender = ewram_data[scan_start + 0x08]
                        hours = struct.unpack("<H", ewram_data[scan_start+0x0E:scan_start+0x10])[0]
                        mins = ewram_data[scan_start + 0x10]
                        secs = ewram_data[scan_start + 0x11]
                        if gender in (0, 1) and hours < 10000 and mins < 60 and secs < 60:
                            real_sb2_gba = scan_start + 0x02000000
                            enc_offset = real_sb2_gba - sb2_ptr
                            self.enc_offset = enc_offset
                            break
            except Exception:
                pass  # Use cached enc_offset

            # Convert GBA EWRAM addresses to host EWRAM offsets (with enc offset)
            sb1_off = (sb1_ptr + enc_offset) - 0x02000000
            sb2_off = (sb2_ptr + enc_offset) - 0x02000000

            # Bounds check
            if not (0 <= sb1_off < 0x40000 and 0 <= sb2_off < 0x40000):
                sb1_off = sb1_ptr - 0x02000000
                sb2_off = sb2_ptr - 0x02000000

            # Read player name from SB2
            name_data = self._read_ewram(sb2_off + SB2_PLAYER_NAME, 8)
            player_name = decode_gen3(name_data)

            # Read play time
            pt_data = self._read_ewram(sb2_off + SB2_PLAY_TIME, 5)
            hours = struct.unpack("<H", pt_data[0:2])[0]
            minutes = pt_data[2]
            seconds = pt_data[3]

            # Read gender
            gender_byte = self._read_ewram_u8(sb2_off + SB2_PLAYER_GENDER)
            gender = "Male" if gender_byte == 0 else "Female"

            # Check if game data is actually loaded
            # Title screen: callbacks may be non-zero but player name empty
            if not player_name.strip() and hours == 0 and minutes == 0:
                return {
                    "status": "title_screen",
                    "game": "Pokemon Emerald",
                    "detail": "No save loaded" if cb1 == 0 else "Title/intro sequence",
                    "mgba_pid": self.pid,
                    "callbacks": f"cb1=0x{cb1:08X} cb2=0x{cb2:08X}",
                }

            # Read position from SB1
            px = self._read_ewram_u16(sb1_off + SB1_PLAYER_X)
            py = self._read_ewram_u16(sb1_off + SB1_PLAYER_Y)
            map_group = self._read_ewram_u8(sb1_off + SB1_MAP_GROUP)
            map_num = self._read_ewram_u8(sb1_off + SB1_MAP_NUM)
            location = MAP_NAMES.get(
                (map_group, map_num), f"Map ({map_group}, {map_num})"
            )

            # Read party
            party_count = self._read_ewram_u8(sb1_off + SB1_PARTY_COUNT)
            party_count = min(party_count, 6)

            party = []
            for i in range(party_count):
                mon_off = sb1_off + SB1_PARTY_DATA + (i * PARTY_MON_SIZE)
                try:
                    species = self._read_ewram_u16(mon_off)
                    if species == 0 or species > 500:
                        continue  # Skip invalid entries
                    nickname_data = self._read_ewram(mon_off + PKM_NICKNAME, 10)
                    nickname = decode_gen3(nickname_data)
                    level = self._read_ewram_u8(mon_off + PKM_LEVEL)
                    hp = self._read_ewram_u16(mon_off + PKM_HP)
                    max_hp = self._read_ewram_u16(mon_off + PKM_MAX_HP)

                    # Sanity checks
                    if level > 100:
                        level = 0
                    if max_hp > 999:
                        max_hp = 0
                        hp = 0

                    species_name = SPECIES_NAMES.get(species, f"Pokemon #{species}")
                    party.append({
                        "species": species_name,
                        "species_id": species,
                        "nickname": nickname,
                        "level": level,
                        "hp": hp,
                        "max_hp": max_hp,
                    })
                except Exception:
                    pass

            # Read badges
            event_flags = self._read_ewram(sb1_off + SB1_EVENT_FLAGS, 0x200)
            badges = 0
            badge_list = []
            for i in range(8):
                flag = BADGE_FLAGS[i]
                byte_idx = flag // 8
                bit_idx = flag % 8
                if byte_idx < len(event_flags) and (event_flags[byte_idx] & (1 << bit_idx)):
                    badges += 1
                    badge_list.append(BADGE_NAMES[i])

            # Read money (XOR encrypted)
            money_raw = self._read_ewram_u32(sb1_off + SB1_MONEY)
            security_key = self._read_ewram_u32(sb1_off + SB1_SECURITY_KEY)
            money = money_raw ^ security_key
            if money > 999999:
                money = 0  # Sanity check

            # Check battle state
            battle_flags = self._read_ewram_u32(BATTLE_TYPE_FLAGS_OFF)
            in_battle = battle_flags != 0

            return {
                "status": "in_battle" if in_battle else "overworld",
                "game": "Pokemon Emerald",
                "player": player_name,
                "gender": gender,
                "location": location,
                "map_group": map_group,
                "map_num": map_num,
                "position": {"x": px, "y": py},
                "badges": badges,
                "badge_list": badge_list,
                "money": money,
                "playtime": f"{hours}h {minutes}m {seconds}s",
                "playtime_hours": hours,
                "playtime_minutes": minutes,
                "playtime_seconds": seconds,
                "party_count": len(party),
                "party": party,
                "in_battle": in_battle,
                "mgba_pid": self.pid,
                "timestamp": time.time(),
            }

        except Exception as e:
            log.error(f"Error reading game state: {e}")
            self.pid = None
            self.gba_block_base = None
            return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------
class ReuseAddrHTTPServer(HTTPServer):
    allow_reuse_address = True


class StateHandler(BaseHTTPRequestHandler):
    reader: MgbaMemoryReader

    def do_GET(self):
        if self.path == "/health":
            self._json({"ok": True})
        elif self.path in ("/state", "/"):
            self._json(self.reader.read_game_state())
        else:
            self.send_error(404)

    def _json(self, data: dict):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


# ---------------------------------------------------------------------------
# Push updates to stream server
# ---------------------------------------------------------------------------
def push_to_stream_server(state: dict, url: str):
    try:
        status = state.get("status", "disconnected")
        # Always send all fields to avoid stale data
        base = {
            "status": status,
            "title": "EMERALD",
            "subtitle": "",
            "status_text": "",
            "objective": None,
            "last_action": None,
            "location": None,
            "playtime": None,
            "badges": 0,
            "party_count": 0,
        }
        if status == "disconnected":
            payload = {**base,
                "title": "DISCONNECTED",
                "subtitle": "mGBA not running",
                "status_text": "NO EMULATOR",
            }
        elif status == "title_screen":
            payload = {**base,
                "title": "TITLE SCREEN",
                "subtitle": state.get("detail", "Waiting for game..."),
                "status_text": "STANDBY",
            }
        elif status == "error":
            payload = {**base,
                "title": "ERROR",
                "subtitle": state.get("error", "Unknown"),
                "status_text": "ERROR",
            }
        else:
            player = state.get("player", "???")
            location = state.get("location", "Unknown")
            badges = state.get("badges", 0)
            playtime = state.get("playtime", "0h 0m")
            in_battle = state.get("in_battle", False)
            money = state.get("money", 0)

            party = state.get("party", [])
            if party:
                lead = party[0]
                lead_text = f"{lead['species']} Lv.{lead['level']}"
                if lead["max_hp"] > 0:
                    lead_text += f" ({lead['hp']}/{lead['max_hp']} HP)"
            else:
                lead_text = "No party"

            payload = {**base,
                "status": "connected",
                "title": player or "EMERALD",
                "subtitle": location,
                "status_text": "IN BATTLE" if in_battle else "EXPLORING",
                "objective": f"Badges: {badges}/8 | ${money:,}",
                "last_action": lead_text,
                "location": location,
                "playtime": playtime,
                "badges": badges,
                "party_count": len(party),
            }

        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception as e:
        log.debug(f"Push failed: {e}")


def background_loop(reader: MgbaMemoryReader):
    log.info("Background poller started")
    while True:
        try:
            if not reader.is_connected():
                reader.connect()
            state = reader.read_game_state()
            push_to_stream_server(state, STREAM_SERVER_URL)
        except Exception as e:
            log.error(f"Background error: {e}")
        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    reader = MgbaMemoryReader()

    if reader.connect():
        log.info(f"Connected to mGBA PID {reader.pid}")
        state = reader.read_game_state()
        log.info(f"Initial state: {state.get('status')} - {state.get('player', 'N/A')}")
    else:
        log.info("mGBA not found, will retry in background")

    StateHandler.reader = reader
    bg = threading.Thread(target=background_loop, args=(reader,), daemon=True)
    bg.start()

    server = ReuseAddrHTTPServer(("0.0.0.0", PORT), StateHandler)
    log.info(f"Emerald game state server on port {PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Diagnostic: read the bot's embedded mGBA process (PID from arg or pid file)
and dump key memory values — save block pointers, player position, map, battle flags.
"""
import sys, struct, os, glob

def find_bot_pid():
    try:
        return int(open("/home/ryan/projects/emerald-ai/logs/emerald_v2.pid").read().strip())
    except:
        pass
    # fallback: find by cmdline
    for d in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            cmd = open(d).read()
            if "src_v2.main" in cmd:
                return int(d.split("/")[2])
        except:
            pass
    return None

def find_gba_mmap(pid):
    """Find the anonymous ~384KB mapping that holds GBA address space."""
    with open(f"/proc/{pid}/maps") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 5: continue
            if parts[1] != "rw-p": continue
            if parts[4] != "0": continue  # anonymous (no file)
            start, end = [int(x, 16) for x in parts[0].split("-")]
            size = end - start
            if 300_000 <= size <= 500_000:
                return start, end
    return None, None

def r32(mem_fd, base, gba_addr):
    # GBA EWRAM starts at base+0, IWRAM at base+0x58000 based on mGBA layout
    if 0x02000000 <= gba_addr < 0x02040000:
        off = base + (gba_addr - 0x02000000)
    elif 0x03000000 <= gba_addr < 0x03008000:
        off = base + 0x58000 + (gba_addr - 0x03000000)
    else:
        return None
    try:
        mem_fd.seek(off)
        return struct.unpack("<I", mem_fd.read(4))[0]
    except:
        return None

def r16(mem_fd, base, gba_addr):
    val = r32(mem_fd, base, gba_addr)
    return val & 0xFFFF if val is not None else None

def r8(mem_fd, base, gba_addr):
    val = r32(mem_fd, base, gba_addr)
    return val & 0xFF if val is not None else None

pid = int(sys.argv[1]) if len(sys.argv) > 1 else find_bot_pid()
if not pid:
    print("ERROR: cannot find bot PID"); sys.exit(1)
print(f"Bot PID: {pid}")

mmap_base, mmap_end = find_gba_mmap(pid)
if not mmap_base:
    print("ERROR: cannot find GBA mmap region"); sys.exit(1)
print(f"GBA mmap: 0x{mmap_base:x}–0x{mmap_end:x} ({mmap_end-mmap_base} bytes)")

with open(f"/proc/{pid}/mem", "rb") as m:
    SB1_PTR = r32(m, mmap_base, 0x03005D8C)
    SB2_PTR = r32(m, mmap_base, 0x03005D90)
    BATTLE  = r32(m, mmap_base, 0x02022FEC)
    print(f"SaveBlock1 ptr: 0x{SB1_PTR:08X}" if SB1_PTR else "SaveBlock1 ptr: NONE")
    print(f"SaveBlock2 ptr: 0x{SB2_PTR:08X}" if SB2_PTR else "SaveBlock2 ptr: NONE")
    print(f"Battle flags:   0x{BATTLE:08X}" if BATTLE is not None else "Battle flags: NONE")

    if SB1_PTR and 0x02000000 <= SB1_PTR < 0x04000000:
        x  = r16(m, mmap_base, SB1_PTR + 0x00)
        y  = r16(m, mmap_base, SB1_PTR + 0x02)
        mg = r8(m,  mmap_base, SB1_PTR + 0x04)
        mn = r8(m,  mmap_base, SB1_PTR + 0x05)
        print(f"Player pos: ({x}, {y})  map=({mg}, {mn})")
        # Dump first 32 bytes of SaveBlock1 raw
        raw = []
        for i in range(0, 32, 4):
            v = r32(m, mmap_base, SB1_PTR + i)
            raw.append(f"{v:08X}" if v is not None else "????????")
        print(f"SB1[0:32]: {' '.join(raw)}")
    else:
        print("SaveBlock1 pointer invalid — game not in overworld yet")

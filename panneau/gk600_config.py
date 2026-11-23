#!/usr/bin/env python3
"""
gk600_config.py - EXPERIMENTAL - keys, macros, per-key colours, keyboard settings and clock of the
MSI Forge GK600 TKL Wireless, over USB, without MSI's software.

Every block is written the way MSI's own software writes it (DeviceDriver.exe of the "MSI FORGE
GK600 Driver 1.0.0.8"), on the command interface (64-byte feature reports, usage page FF13):

    04 18  (04 19 for macros)        open                acknowledged: byte 3 = 01
    04 <block>, byte 8 = packets     select the block    acknowledged
    packets x 64 bytes               data                not acknowledged one by one
    04 02                            store and close     acknowledged; bytes 4-7 = sum of the bytes
                                                         the keyboard read back from its own flash
    04 F0                            refresh, after keys, colours and lighting (as MSI does)

    block               write  read  packets  MCU flash (Frieren V1.17)
    keys, main layer     11     10     9      0x9400   4 bytes per key at key number x 4
    keys, Fn layer       27     26     9      0xAC00
    lighting effect      13     12     1      0x9800   effect 0x80 = per-key colours
    per-key colours      23     22     9      0x9C00   [key number, R, G, B] at key number x 4
    settings             17     16     1      0x9000
    macros               15     14    <=48    0xA000   opened with 04 19
    clock                28      -     1      (RAM and clock chip; the TKL firmware never draws it)

The panel checks the sum of every write against the data it sent (MSI's software ignores it): a
write only counts as done when the keyboard read back exactly what was sent. If the sum does not
match, the block is read back and compared instead. Reads follow MSI's own read (04 F5): select,
read the acknowledgement, then one GET_FEATURE per packet, then 04 02. Each read is done twice and
compared.

Limits the panel enforces (checked on the Frieren V1.17 firmware in an emulator):
  - macros: 48 packets at most. The firmware accepts 49, but the 49th packet erases the first
    page of the Fn layer (0xAC00), so MSI's own limit (about 3100 bytes) can damage it.
  - a block is refused before anything is sent when its size or its AA 55 end mark is wrong.

Usage (gk600_restore.py in ../restauration):
  python gk600_config.py read keys            show the main layer
  python gk600_config.py read colours         show the per-key colours
  python gk600_config.py backup FILE.json     save keys, colours, macros, lighting and settings
  python gk600_config.py clock                set the keyboard clock to this PC's time (MSI's "Time
                                              Syns"; the TKL screen does not show it, test use only)
"""

import argparse
import datetime
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "restauration"))
sys.path.insert(0, HERE)
import gk600_restore as g  # noqa: E402
import gk600_layout as lay  # noqa: E402

__version__ = "0.1-experimental"

PACKET = 64
OPEN, CLOSE, REFRESH, OPEN_MACROS, CLOCK = 0x18, 0x02, 0xF0, 0x19, 0x28
DATA_DELAY = 0.035          # between data packets (MSI: cmd_delaytime 35 ms)
READ_DELAY = 0.02           # between read packets (MSI: 3 ms)
TABLE = 576                 # keys and colours: 144 entries x 4 bytes, AA 55 at 574
MACRO_PACKETS = 48          # never more (see above)
MACRO_SLOTS = 100           # directory: 100 x 4 bytes
MACRO_DIR = MACRO_SLOTS * 4
MAX_INDEX = 142             # entry 143 holds the AA 55 end mark


class Block:
    def __init__(self, name, write, read, packets, open_op=OPEN, select_b2=0, refresh=False):
        self.name, self.write, self.read, self.packets = name, write, read, packets
        self.open_op, self.select_b2, self.refresh = open_op, select_b2, refresh


BLOCKS = {
    "keys": Block("keys", 0x11, 0x10, 9, refresh=True),
    "fnkeys": Block("fnkeys", 0x27, 0x26, 9, refresh=True),
    "lighting": Block("lighting", 0x13, 0x12, 1, refresh=True),
    "colours": Block("colours", 0x23, 0x22, 9, refresh=True),
    "settings": Block("settings", 0x17, 0x16, 1, select_b2=1),
    "macros": Block("macros", 0x15, 0x14, MACRO_PACKETS, open_op=OPEN_MACROS),
}
ORDER = ("macros", "keys", "fnkeys", "colours", "lighting", "settings")     # MSI's order


class NotSupported(g.RestoreError):
    pass


# ---------------------------------------------------------------- transactions
def _acked(r, op):
    return len(r) >= 4 and r[0] == 0x04 and r[1] == op and r[3] == 0x01


def _trailer_ok(name, data):
    if name in ("keys", "fnkeys", "colours"):
        return len(data) == TABLE and data[574:576] == b"\xAA\x55"
    if name == "lighting":
        return len(data) == PACKET and data[14:16] == b"\xAA\x55"
    if name in ("settings", "clock"):
        return len(data) == PACKET and data[62:64] == b"\xAA\x55"
    if name == "macros":
        return 0 < len(data) <= MACRO_PACKETS * PACKET and data[-2:] == b"\xAA\x55"
    return False


def write_block(t, name, data, log=print):
    """Writes one block and checks the keyboard's read-back sum. Raises RestoreError."""
    data = bytes(data)
    blk = BLOCKS[name]
    if len(data) % PACKET or not _trailer_ok(name, data):
        raise g.RestoreError("invalid %s block (size %d or end mark)" % (name, len(data)))
    n = len(data) // PACKET
    if n > blk.packets:
        raise g.RestoreError("invalid %s block: %d packets, %d at most" % (name, n, blk.packets))
    log("write %s: %d bytes, %d packets" % (name, len(data), n))
    r = g.command(t, blk.open_op, log=log)
    if not _acked(r, blk.open_op):
        raise g.RestoreError("the keyboard is busy (reply %s): switch it off and on, then try again"
                             % r[:8].hex(" "))
    r = g.command(t, blk.write, blk.select_b2, n, log=log)
    if not _acked(r, blk.write) or (r[8] | (r[9] << 8)) != n:
        g.command(t, CLOSE, log=log)
        raise g.RestoreError("%s block refused (reply %s)" % (name, r[:10].hex(" ")))
    for i in range(n):
        t.sleep(DATA_DELAY)
        t.set_feature(data[i * PACKET:(i + 1) * PACKET])
    r = g.command(t, CLOSE, log=log)
    if not _acked(r, CLOSE):
        raise g.RestoreError("%s not stored: 04 02 refused (reply %s)" % (name, r[:8].hex(" ")))
    got, want = int.from_bytes(r[4:8], "little"), sum(data)
    if blk.refresh:
        r = g.command(t, REFRESH, log=log)
        if not _acked(r, REFRESH):
            log("  note: 04 F0 not acknowledged (%s)" % r[:8].hex(" "))
    if got == want:
        log("write %s: done, checked (sum %d)" % (name, got))
        return
    # MSI's software ignores this sum. A firmware that does not give it (or gives another one) is
    # checked by reading the block back instead; a corrupted write fails both checks.
    log("  note: the keyboard's sum is %d, sent %d: reading the block back" % (got, want))
    t.sleep(0.2)
    try:
        back = read_block(t, name, packets=n, log=log)
    except NotSupported:
        raise g.RestoreError("%s check failed: sum %d, sent %d, and this firmware cannot read it back"
                             % (name, got, want))
    if back[:len(data)] != data:
        raise g.RestoreError("%s check failed: the keyboard holds different data" % name)
    log("write %s: done, checked by reading it back" % name)


def _read_once(t, blk, n, log):
    r = g.command(t, OPEN, log=log)
    if not _acked(r, OPEN):
        raise g.RestoreError("the keyboard is busy (reply %s): switch it off and on, then try again"
                             % r[:8].hex(" "))
    r = g.command(t, blk.read, 0, n, log=log)
    if not _acked(r, blk.read):
        g.command(t, CLOSE, log=log)
        raise NotSupported("reading %s is not supported by this firmware (reply %s)"
                           % (blk.name, r[:10].hex(" ")))
    pages = []
    for _ in range(n):
        t.sleep(READ_DELAY)
        p = bytes(t.get_feature())
        if len(p) < PACKET:
            raise g.RestoreError("short read packet")
        pages.append(p[:PACKET])
    r = g.command(t, CLOSE, log=log)
    if not _acked(r, CLOSE):
        raise g.RestoreError("read %s: 04 02 refused (reply %s)" % (blk.name, r[:8].hex(" ")))
    return b"".join(pages)


def read_block(t, name, packets=None, log=print):
    """Reads one block twice and returns it when both reads agree."""
    blk = BLOCKS[name]
    n = packets or blk.packets
    if not 1 <= n <= blk.packets:
        raise g.RestoreError("invalid read size")
    try:
        first = _read_once(t, blk, n, log)
    except NotSupported:
        # A transfer left unfinished (by another program) is dropped by the keyboard after 2 s
        # without a command: wait for that once, then ask again.
        t.sleep(2.2)
        first = _read_once(t, blk, n, log)
    for _ in range(2):
        again = _read_once(t, blk, n, log)
        if again == first:
            log("read %s: %d bytes, read twice, identical" % (name, len(first)))
            return first
        log("read %s: the two reads differ, reading again" % name)
        first = again
    raise g.RestoreError("read %s: the keyboard gave different data each time" % name)


def set_clock(t, when=None, log=print):
    """Sets the keyboard clock, like MSI's "Time Syns" button. The GK600 TKL firmware stores it
    (RAM 0x200001F3, clock chip) and redraws the home screen, but has no code to draw it."""
    now = when or datetime.datetime.now()
    p = bytearray(PACKET)
    p[1] = 1                     # MSI: index of the screen view + 1
    p[2] = 0x5A                  # checked by the firmware
    p[3], p[4], p[5] = now.year % 100, now.month, now.day
    p[6], p[7], p[8] = now.hour, now.minute, now.second
    p[10] = now.isoweekday() % 7  # Sunday = 0, like Windows
    p[62:64] = b"\xAA\x55"
    r = g.command(t, OPEN, log=log)
    if not _acked(r, OPEN):
        raise g.RestoreError("the keyboard is busy (reply %s)" % r[:8].hex(" "))
    r = g.command(t, CLOCK, 0, 1, log=log)
    if not _acked(r, CLOCK):
        g.command(t, CLOSE, log=log)
        raise g.RestoreError("clock refused (reply %s)" % r[:10].hex(" "))
    t.sleep(DATA_DELAY)
    t.set_feature(bytes(p))
    r = g.command(t, CLOSE, log=log)
    if not _acked(r, CLOSE):
        raise g.RestoreError("clock not set: 04 02 refused (reply %s)" % r[:8].hex(" "))
    log("clock set to %s" % now.strftime("%Y-%m-%d %H:%M:%S"))
    return now


# ---------------------------------------------------------------- key entries
def _int(v, lo, hi, what):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError("invalid %s" % what)
    if not lo <= n <= hi:
        raise ValueError("invalid %s" % what)
    return n


def encode_action(a):
    """One key setting -> the 4 bytes the keyboard stores."""
    if not isinstance(a, dict):
        raise ValueError("invalid key setting")
    kind = a.get("type")
    if kind == "default":
        return b"\x00\x00\x00\x00"
    if kind == "disabled":
        return b"\x05\x03\x00\x00"
    if kind == "key":
        mods = _int(a.get("mods", 0), 0, 255, "modifiers")
        code = _int(a.get("code", 0), 0, 255, "key")
        if code and code not in lay.USAGE_CODES:
            raise ValueError("invalid key")
        if not code and not mods:
            raise ValueError("invalid key: nothing to send")
        if 0xE0 <= code <= 0xE7 and not mods:         # a modifier alone: MSI sends its bit
            return bytes([0x02, 1 << (code - 0xE0), 0, 0])
        return bytes([0x02, mods, code, 0])
    if kind == "mouse":
        mask = {m[0]: m[1] for m in lay.MOUSE}.get(a.get("button"))
        if mask is None:
            raise ValueError("invalid mouse button")
        return bytes([0x01, 0x01, mask, 0])
    if kind == "wheel":
        v = {w[0]: w[1] for w in lay.WHEEL}.get(a.get("dir"))
        if v is None:
            raise ValueError("invalid wheel direction")
        return bytes([0x01, 0x03, v, 0])
    if kind == "media":
        u = _int(a.get("code"), 1, 0x3FF, "media key")
        if u not in lay.MEDIA_CODES:
            raise ValueError("invalid media key")
        return bytes([0x03, u & 0xFF, u >> 8, 0])
    if kind == "macro":
        idx = _int(a.get("index"), 0, MACRO_SLOTS - 1, "macro number")
        mode = _int(a.get("mode", 0), 0, 3, "macro mode")
        count = _int(a.get("count", 1), 1, 255, "repeat count") if mode == 1 else 1
        return bytes([0x06, idx, mode, count])
    if kind == "raw":
        try:
            b = bytes.fromhex(a.get("bytes", ""))
        except ValueError:
            raise ValueError("invalid raw entry")
        if len(b) != 4:
            raise ValueError("invalid raw entry")
        return b
    raise ValueError("invalid key setting")


def decode_entry(b):
    """4 stored bytes -> key setting (unknown entries are kept as raw bytes)."""
    b = bytes(b)
    if b == b"\x00\x00\x00\x00":
        return {"type": "default"}
    if b == b"\x05\x03\x00\x00":
        return {"type": "disabled"}
    t0, b1, b2, b3 = b
    if t0 == 0x02 and b3 == 0:
        if b2 == 0 and b1 and (b1 & (b1 - 1)) == 0:        # one modifier alone
            return {"type": "key", "mods": 0, "code": 0xE0 + b1.bit_length() - 1}
        if (b2 == 0 and b1) or b2 in lay.USAGE_CODES:
            return {"type": "key", "mods": b1, "code": b2}
    if t0 == 0x01 and b3 == 0:
        if b1 == 0x01:
            for i, m, _, _ in lay.MOUSE:
                if m == b2:
                    return {"type": "mouse", "button": i}
        if b1 == 0x03:
            for i, v, _, _ in lay.WHEEL:
                if v == b2:
                    return {"type": "wheel", "dir": i}
    if t0 == 0x03 and b3 == 0 and (b1 | (b2 << 8)) in lay.MEDIA_CODES:
        return {"type": "media", "code": b1 | (b2 << 8)}
    if t0 == 0x06 and b1 < MACRO_SLOTS and b2 <= 3:
        return {"type": "macro", "index": b1, "mode": b2, "count": b3 if b2 == 1 else 1}
    return {"type": "raw", "bytes": b.hex()}


def build_keys(actions):
    """{key number: setting} -> the 576-byte layer. Keys not listed keep their default."""
    out = bytearray(TABLE)
    for idx, a in actions.items():
        idx = _int(idx, 1, MAX_INDEX, "key number")
        if idx in lay.NOT_REMAPPABLE and (a or {}).get("type") != "default":
            raise ValueError("this key cannot be changed")
        e = encode_action(a)
        for i in lay.mirrors(idx):
            out[i * 4:i * 4 + 4] = e
    out[574:576] = b"\xAA\x55"
    return bytes(out)


def parse_keys(data):
    """576-byte layer -> {key number: setting} for every key that is not default."""
    if len(data) < TABLE:
        raise g.RestoreError("short key table")
    out = {}
    for idx in range(1, MAX_INDEX + 1):
        e = data[idx * 4:idx * 4 + 4]
        if e != b"\x00\x00\x00\x00":
            out[idx] = decode_entry(e)
    return lay.fold(out)                                 # second numbers (Home, ISO * µ)


def keys_valid(data):
    return len(data) >= TABLE and data[574:576] == b"\xAA\x55"


# ---------------------------------------------------------------- per-key colours
def parse_colour(c):
    if isinstance(c, (list, tuple)) and len(c) == 3:
        rgb = tuple(_int(v, 0, 255, "colour") for v in c)
    else:
        s = str(c).strip().lstrip("#")
        if len(s) != 6:
            raise ValueError("invalid colour")
        try:
            rgb = tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            raise ValueError("invalid colour")
    return rgb


def build_colours(colours):
    """{key number: colour} -> the 576-byte table ([number, R, G, B] at number x 4)."""
    out = bytearray(TABLE)
    for idx, c in colours.items():
        idx = _int(idx, 1, MAX_INDEX, "key number")
        r, gr, b = parse_colour(c)
        for i in lay.mirrors(idx):
            out[i * 4:i * 4 + 4] = bytes([i, r, gr, b])
    out[574:576] = b"\xAA\x55"
    return bytes(out)


def parse_colours(data):
    """576-byte table -> {key number: "#rrggbb"} for the entries the keyboard holds."""
    if len(data) < TABLE:
        raise g.RestoreError("short colour table")
    out = {}
    for idx in range(1, MAX_INDEX + 1):
        e = data[idx * 4:idx * 4 + 4]
        if e[0] == idx:
            out[idx] = "#%02x%02x%02x" % tuple(e[1:4])
    return lay.fold(out)


def custom_mode(brightness):
    """Lighting block that switches the keyboard to its per-key colours (effect 0x80)."""
    p = bytearray(PACKET)
    p[0] = 0x80
    p[9] = _int(brightness, 1, 5, "brightness")
    p[14:16] = b"\xAA\x55"
    return bytes(p)


def parse_lighting(data):
    """Lighting block -> {"effect": n | "custom", ...}. effect None: nothing valid stored."""
    if len(data) < 16 or data[14:16] != b"\xAA\x55":
        return {"effect": None}
    e = data[0]
    if e == 0x80:
        return {"effect": "custom", "brightness": data[9] or 5}
    if e >= 20:
        return {"effect": None}
    return {"effect": e, "color": "#%02x%02x%02x" % tuple(data[1:4]), "multicolour": bool(data[8]),
            "brightness": data[9] or 5, "speed": data[10] or 3, "direction": data[11] & 3}


# ---------------------------------------------------------------- settings
SLEEP = (0, 1, 2, 3)            # never, 1 min, 5 min, 30 min


def build_settings(s, base=None):
    """Settings block. Bytes the panel does not know are kept from `base` (what the keyboard
    holds); without it, MSI's own block is used (byte 1 = 1)."""
    if base and len(base) >= PACKET and base[62:64] == b"\xAA\x55":
        p = bytearray(base[:PACKET])
    else:
        p = bytearray(PACKET)
        p[1] = 1
    p[2] = 1 if s.get("no_alt_tab") else 0
    p[3] = 1 if s.get("no_alt_f4") else 0
    p[4] = 1 if s.get("no_win") else 0
    p[5] = 1 if s.get("fn_toggle") else 0
    p[6] = _int(s.get("sleep", 2), 0, 3, "sleep time")
    p[8] = _int(s.get("debounce", 2), 1, 5, "key response")
    p[62:64] = b"\xAA\x55"
    return bytes(p)


def parse_settings(data):
    if len(data) < PACKET or data[62:64] != b"\xAA\x55":
        return None
    return {"no_alt_tab": bool(data[2]), "no_alt_f4": bool(data[3]), "no_win": bool(data[4]),
            "fn_toggle": bool(data[5]), "sleep": data[6] if data[6] in SLEEP else 2,
            "debounce": data[8] if 1 <= data[8] <= 5 else 2}


# ---------------------------------------------------------------- macros
# Steps of a macro, as the panel stores them, and the 4 bytes of each in the keyboard
# (MSI's encoding, DeviceDriver.exe):
#   {"t": "down", "code": usage}        00 00 usage B0
#   {"t": "up", "code": usage}          00 00 usage 30
#   {"t": "mdown", "button": b}         00 00 mask 90    (left 1, right 2, middle 4)
#   {"t": "mup", "button": b}           00 00 mask 10
#   {"t": "delay", "ms": n}             lo hi 00 50      (10 to 65535 ms)
# MSI puts a delay after every key or mouse step; the panel does the same (10 ms by default).
# Directory: 100 x [offset LE16, 00, 00]; MSI writes FF FF FF FF for a macro without steps and
# leaves the slots after its last macro at 00 00 00 00. The panel writes FF FF FF FF for every
# unused slot, so a key left pointing at a deleted macro finds MSI's own "empty" mark.
MACRO_BUTTONS = {"left": 1, "right": 2, "middle": 4}
MIN_DELAY, MAX_DELAY = 10, 65535


def _macro_actions(steps):
    acts = []
    for s in steps:
        if not isinstance(s, dict):
            raise ValueError("invalid macro step")
        t = s.get("t")
        if t == "delay":
            ms = min(MAX_DELAY, max(MIN_DELAY, _int(s.get("ms", MIN_DELAY), 0, 10 ** 7, "delay")))
            if acts and acts[-1][3] == 0x50:                 # two delays in a row: one delay
                ms = min(MAX_DELAY, ms + (acts[-1][0] | (acts[-1][1] << 8)))
                acts[-1] = (ms & 0xFF, ms >> 8, 0, 0x50)
            else:
                acts.append((ms & 0xFF, ms >> 8, 0, 0x50))
            continue
        if t in ("down", "up"):
            code = _int(s.get("code"), 1, 255, "macro key")
            if code not in lay.USAGE_CODES:
                raise ValueError("invalid macro key")
            ev = (0, 0, code, 0xB0 if t == "down" else 0x30)
        elif t in ("mdown", "mup"):
            mask = MACRO_BUTTONS.get(s.get("button"))
            if not mask:
                raise ValueError("invalid macro mouse button")
            ev = (0, 0, mask, 0x90 if t == "mdown" else 0x10)
        elif t == "raw":                                     # unknown step read from the keyboard
            try:
                b = bytes.fromhex(s.get("bytes", ""))
            except ValueError:
                raise ValueError("invalid macro step")
            if len(b) != 4:
                raise ValueError("invalid macro step")
            ev = tuple(b)
        else:
            raise ValueError("invalid macro step")
        if acts and acts[-1][3] != 0x50:                     # keep MSI's event / delay rhythm
            acts.append((MIN_DELAY, 0, 0, 0x50))
        acts.append(ev)
    if acts and acts[-1][3] != 0x50:
        acts.append((MIN_DELAY, 0, 0, 0x50))
    return acts


def build_macros(macros):
    """List of macros ({"name", "steps"}) -> the macro block. Macro number = position."""
    if len(macros) > MACRO_SLOTS:
        raise ValueError("too many macros (%d at most)" % MACRO_SLOTS)
    buf = bytearray(MACRO_PACKETS * PACKET)
    buf[:MACRO_DIR] = b"\xFF" * MACRO_DIR      # every unused slot marked empty, as MSI marks an empty macro
    off = MACRO_DIR
    for i, m in enumerate(macros):
        acts = _macro_actions((m or {}).get("steps") or [])
        if not acts:
            buf[i * 4:i * 4 + 4] = b"\xFF\xFF\xFF\xFF"
            continue
        need = 8 + 4 * len(acts)
        if off + need > len(buf):
            raise ValueError("macros too long")
        buf[i * 4:i * 4 + 4] = bytes([off & 0xFF, off >> 8, 0, 0])
        buf[off] = len(acts) & 0xFF
        buf[off + 1] = len(acts) >> 8
        for k, a in enumerate(acts):
            buf[off + 8 + 4 * k:off + 12 + 4 * k] = bytes(a)
        off += need
    packets = off // PACKET + (1 if off % PACKET == 0 else 2)     # MSI's count: room for AA 55
    if packets > MACRO_PACKETS:
        raise ValueError("macros too long: %d bytes, %d at most" % (off, macro_capacity()))
    data = buf[:packets * PACKET]
    data[-2:] = b"\xAA\x55"
    return bytes(data)


def macro_capacity():
    """Largest macro data (directory included) that still fits in 48 packets with MSI's count."""
    return (MACRO_PACKETS - 1) * PACKET


def macro_bytes(macros):
    """Bytes used by these macros (directory included), to show how full the keyboard is."""
    return MACRO_DIR + sum(8 + 4 * len(_macro_actions((m or {}).get("steps") or []))
                           for m in macros if _macro_actions((m or {}).get("steps") or []))


def parse_macros(data):
    """Macro block -> list of {"name", "steps"} (None for a slot without a macro). Trailing
    empty slots are dropped."""
    out = []
    for i in range(MACRO_SLOTS):
        d = data[i * 4:i * 4 + 4]
        if len(d) < 4 or d == b"\xFF\xFF\xFF\xFF" or d == b"\x00\x00\x00\x00":
            out.append(None)
            continue
        off = d[0] | (d[1] << 8)
        if off < MACRO_DIR or off + 8 > len(data):
            out.append(None)
            continue
        n = data[off] | (data[off + 1] << 8)
        if off + 8 + 4 * n > len(data):
            out.append(None)
            continue
        steps = []
        for k in range(n):
            a = data[off + 8 + 4 * k:off + 12 + 4 * k]
            kind = a[3]
            if kind == 0x50:
                steps.append({"t": "delay", "ms": a[0] | (a[1] << 8)})
            elif kind in (0xB0, 0x30):
                steps.append({"t": "down" if kind == 0xB0 else "up", "code": a[2]})
            elif kind in (0x90, 0x10):
                btn = {v: k2 for k2, v in MACRO_BUTTONS.items()}.get(a[2], "left")
                steps.append({"t": "mdown" if kind == 0x90 else "mup", "button": btn})
            else:
                steps.append({"t": "raw", "bytes": bytes(a).hex()})
        out.append({"name": "Macro %d" % (i + 1), "steps": steps})
    while out and out[-1] is None:
        out.pop()
    return out


# ---------------------------------------------------------------- whole configuration
def read_all(t, parts=ORDER, log=print):
    """Reads what the keyboard holds. Returns ({part: parsed}, {part: raw bytes}, {part: error})."""
    parsed, raw, errors = {}, {}, {}
    for p in parts:
        try:
            data = read_block(t, p, log=log)
        except NotSupported as e:
            errors[p] = "not_supported"
            log(str(e))
            continue
        raw[p] = data
        if p in ("keys", "fnkeys"):
            parsed[p] = parse_keys(data) if keys_valid(data) else {}
        elif p == "colours":
            parsed[p] = parse_colours(data) if keys_valid(data) else {}
        elif p == "lighting":
            parsed[p] = parse_lighting(data)
        elif p == "settings":
            parsed[p] = parse_settings(data)
        elif p == "macros":
            parsed[p] = parse_macros(data)
    return parsed, raw, errors


def _print_keys(actions):
    names = {k["idx"]: k["us"] for k in lay.keys("iso") + lay.keys("ansi")}
    if not actions:
        print("  every key does its normal job")
    for idx, a in sorted(actions.items()):
        print("  %-10s %s" % (names.get(idx, "#%d" % idx), json.dumps(a)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="GK600 TKL keys, colours, macros, settings (experimental)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read", help="show a block the keyboard holds")
    r.add_argument("part", choices=ORDER)
    b = sub.add_parser("backup", help="save everything the keyboard holds to a JSON file")
    b.add_argument("file")
    sub.add_parser("clock", help="set the keyboard clock to this PC's time")
    args = ap.parse_args(argv)
    info = g.select_keyboard(log=print)
    t = g.HidTransport(info)
    try:
        if args.cmd == "clock":
            set_clock(t)
            return 0
        parts = ORDER if args.cmd == "backup" else (args.part,)
        parsed, raw, errors = read_all(t, parts, log=lambda m: None)
    finally:
        t.close()
    if args.cmd == "read":
        p = args.part
        if p in errors:
            print("reading %s is not supported by this firmware" % p)
            return 1
        if p in ("keys", "fnkeys"):
            _print_keys(parsed[p])
        else:
            print(json.dumps(parsed[p], indent=1, ensure_ascii=False))
        return 0
    out = {"format": "gk600-backup", "version": 1, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
           "parsed": {k: v for k, v in parsed.items()}, "raw": {k: v.hex() for k, v in raw.items()},
           "unsupported": sorted(errors)}
    with open(args.file, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("saved %s (%s)" % (args.file, ", ".join(sorted(raw)) or "nothing could be read"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except g.RestoreError as e:
        print("ERROR:", e)
        sys.exit(2)

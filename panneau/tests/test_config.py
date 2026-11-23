#!/usr/bin/env python3
"""
test_config.py - keys, Fn layer, per-key colours, macros, settings, clock and lighting written
and read back on the real Frieren V1.17 firmware code (emulated), with the MCU flash modelled
(emu_flash.py): every block must land in its own flash page and nowhere else.

Usage (from this folder; unicorn needed):
  python -I test_config.py <frieren_v117.bin>
"""

import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.normpath(os.path.join(HERE, ".."))
RESTO = os.path.normpath(os.path.join(PANEL, "..", "restauration"))
for p in (HERE, PANEL, RESTO, os.path.join(RESTO, "tests")):
    sys.path.insert(0, p)

import gk600_restore as g  # noqa: E402
import gk600_fw_emu as E  # noqa: E402
import emu_flash as F  # noqa: E402
import gk600_config as cfg  # noqa: E402
import gk600_layout as lay  # noqa: E402
import gk600_lighting as light  # noqa: E402

fw = open(sys.argv[1], "rb").read()
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  [%s]" % detail) if detail and not ok else ""))


def quiet(msg):
    pass


def new():
    emu = F.FlashEmu(fw, E.SpiFlash(16 << 20))
    return emu, E.EmulatedTransport(emu)


def clean(emu):
    return emu.state == 0 and emu.u8(0x200000BE) == 0 and emu.u8(0x20000040) == 0


PAGES = {"keys": 0x9400, "fnkeys": 0xAC00, "lighting": 0x9800, "colours": 0x9C00, "settings": 0x9000}

# ---------------------------------------------------------------- C1 encodings
acts = [
    {"type": "default"}, {"type": "disabled"},
    {"type": "key", "mods": 0, "code": 0x04}, {"type": "key", "mods": 0x05, "code": 0x3D},
    {"type": "key", "mods": 0x08, "code": 0}, {"type": "mouse", "button": "back"},
    {"type": "wheel", "dir": "down"}, {"type": "media", "code": 0x192},
    {"type": "macro", "index": 3, "mode": 1, "count": 7}, {"type": "macro", "index": 0, "mode": 3, "count": 1},
]
expect = ["00000000", "05030000", "02000400", "02053d00", "02080000", "01010800", "0103ff00",
          "03920100", "06030107", "06000301"]
enc = [cfg.encode_action(a).hex() for a in acts]
check("C1 entries encoded like MSI's software", enc == expect, str(enc))
check("C1 entries decoded back to the same bytes",
      all(cfg.encode_action(cfg.decode_entry(cfg.encode_action(a))) == cfg.encode_action(a) for a in acts)
      and cfg.decode_entry(cfg.encode_action(acts[3])) == acts[3] and cfg.decode_entry(cfg.encode_action(acts[8])) == acts[8],
      str([cfg.decode_entry(cfg.encode_action(a)) for a in acts]))
check("C1 a modifier alone is sent as its bit (MSI)",
      cfg.encode_action({"type": "key", "mods": 0, "code": 0xE1}).hex() == "02020000"
      and cfg.decode_entry(bytes.fromhex("02020000")) == {"type": "key", "mods": 0, "code": 0xE1})
check("C1 unknown entries kept as raw bytes", cfg.decode_entry(bytes.fromhex("07112233")) ==
      {"type": "raw", "bytes": "07112233"} and cfg.encode_action({"type": "raw", "bytes": "07112233"}).hex() == "07112233")
bad = [{"type": "key"}, {"type": "key", "code": 0x99}, {"type": "mouse", "button": "x"},
       {"type": "media", "code": 0x999}, {"type": "macro", "index": 100}, {"type": "macro", "index": 0, "mode": 4},
       {"type": "nope"}, "text", {"type": "raw", "bytes": "zz"}]
refused = 0
for a in bad:
    try:
        cfg.encode_action(a)
    except ValueError:
        refused += 1
check("C1 invalid settings refused before anything is sent", refused == len(bad), "%d/%d" % (refused, len(bad)))

# ---------------------------------------------------------------- C2 tables
layer = {41: {"type": "key", "mods": 0, "code": 0x46}, 117: {"type": "disabled"},
         55: {"type": "key", "mods": 0, "code": 0xE0}, 111: {"type": "media", "code": 0xCD}}
k = cfg.build_keys(layer)
check("C2 key table: 576 bytes, AA 55 at 574", len(k) == 576 and k[574:576] == b"\xAA\x55")
check("C2 key table: entry at number x 4", k[41 * 4:41 * 4 + 4].hex() == "02004600" and k[55 * 4:55 * 4 + 4].hex() == "02010000")
check("C2 Home written to 117 and 113", k[117 * 4:117 * 4 + 4] == k[113 * 4:113 * 4 + 4] == b"\x05\x03\x00\x00")
check("C2 key table read back", cfg.parse_keys(k) == {41: layer[41], 117: layer[117], 55: layer[55], 111: layer[111]},
      str(cfg.parse_keys(k)))
try:
    cfg.build_keys({96: {"type": "key", "code": 4}})
    check("C2 Fn cannot be remapped", False)
except ValueError:
    check("C2 Fn cannot be remapped", True)
cols = {i: "#%02x%02x%02x" % (i, 255 - i, i // 2) for i in (1, 20, 67, 85, 117, 121, 111)}
c = cfg.build_colours(cols)
check("C2 colour table: [number, R, G, B] at number x 4", c[20 * 4:20 * 4 + 4] == bytes([20, 20, 235, 10])
      and c[113 * 4] == 113 and c[574:576] == b"\xAA\x55")
check("C2 colour table read back", cfg.parse_colours(c) == cols, str(cfg.parse_colours(c)))
check("C2 ISO * µ key colour written to 67 and 110", c[67 * 4 + 1:67 * 4 + 4] == c[110 * 4 + 1:110 * 4 + 4] == bytes([67, 188, 33])
      and c[110 * 4] == 110)
k2 = cfg.build_keys({110: {"type": "disabled"}})
check("C2 a second number given alone is written under both numbers and read back as the first",
      k2[67 * 4:67 * 4 + 4] == k2[110 * 4:110 * 4 + 4] == b"\x05\x03\x00\x00"
      and cfg.parse_keys(k2) == {67: {"type": "disabled"}}, str(cfg.parse_keys(k2)))
check("C2 the ISO layout calls the * µ key 67, like the US backslash",
      [k["idx"] for k in lay.keys("iso") if k["id"] == "iso_hash"] == [67]
      and [k["idx"] for k in lay.keys("ansi") if k["id"] == "backslash"] == [67])
check("C2 every layout key number fits the table",
      max(lay.all_indexes()) <= cfg.MAX_INDEX and all(k["idx"] >= 1 for k in lay.keys("iso") + lay.keys("ansi")))
check("C2 ISO layout: 84 keys, ANSI: 83",
      len(lay.keys("iso")) == 84 and len(lay.keys("ansi")) == 83, "%d %d" % (len(lay.keys("iso")), len(lay.keys("ansi"))))

# ---------------------------------------------------------------- C3-C9 on the firmware
emu, t = new()
before = emu.iflash(0x8000, F.FLASH_END - 0x8000)


def written_pages(n0):
    return sorted({op[1] & ~0x3FF for op in emu.iflash_ops[n0:]})


def block_check(label, block, data, pages):
    name = label
    n0 = len(emu.iflash_ops)
    try:
        cfg.write_block(t, block, data, log=quiet)
        ok = True
    except g.RestoreError as e:
        ok, err = False, str(e)
    check("%s written, sum checked by the keyboard" % name, ok, "" if ok else err)
    check("%s: only its flash page(s) touched" % name, written_pages(n0) == pages,
          str([hex(p) for p in written_pages(n0)]))
    check("%s: protocol idle afterwards" % name, clean(emu))


block_check("C3 main layer", "keys", k, [0x9400])
check("C3 flash holds the main layer", emu.iflash(0x9400, 576) == k)
check("C3 04 F0 sent after the keys (display refresh, like MSI)", emu.calls[-1][1] == "display E0C2", str(emu.calls[-1:]))
rk = cfg.read_block(t, "keys", log=quiet)
check("C3 main layer read back (twice, identical)", rk == k and clean(emu))

fn = cfg.build_keys({2: {"type": "media", "code": 0xE9}, 3: {"type": "key", "mods": 1, "code": 0x06}})
block_check("C4 Fn layer", "fnkeys", fn, [0xAC00])
check("C4 flash holds the Fn layer, main layer untouched", emu.iflash(0xAC00, 576) == fn and emu.iflash(0x9400, 576) == k)
check("C4 Fn layer read back", cfg.read_block(t, "fnkeys", log=quiet) == fn)

block_check("C5 custom-colour mode (effect 0x80)", "lighting", cfg.custom_mode(4), [0x9800])
check("C5 lighting page: effect 0x80, brightness 4", emu.iflash(0x9800, 16) == cfg.custom_mode(4)[:16],
      emu.iflash(0x9800, 16).hex())
check("C5 firmware switched to its per-key pattern", emu.u8(0x20000152) == 0x14 and emu.u8(0x20001450) == 0x80,
      "%x %x" % (emu.u8(0x20000152), emu.u8(0x20001450)))
block_check("C5 per-key colours", "colours", c, [0x9C00])
check("C5 colours read back", cfg.parse_colours(cfg.read_block(t, "colours", log=quiet)) == cols)
check("C5 lighting read back as 'custom'", cfg.parse_lighting(cfg.read_block(t, "lighting", log=quiet)) ==
      {"effect": "custom", "brightness": 4})

macros = [
    {"name": "copy", "steps": [{"t": "down", "code": 0xE0}, {"t": "down", "code": 0x06}, {"t": "delay", "ms": 30},
                               {"t": "up", "code": 0x06}, {"t": "up", "code": 0xE0}]},
    {"name": "empty", "steps": []},
    {"name": "click", "steps": [{"t": "mdown", "button": "right"}, {"t": "delay", "ms": 5},
                                {"t": "delay", "ms": 20}, {"t": "mup", "button": "right"}]},
]
mb = cfg.build_macros(macros)
check("C6 macro block: directory, AA 55 at the very end", mb[0:4] == bytes([0x90, 1, 0, 0]) and mb[4:8] == b"\xFF" * 4
      and mb[-2:] == b"\xAA\x55" and len(mb) % 64 == 0)
check("C6 every unused macro slot marked empty (FF FF FF FF)", mb[12:400] == b"\xFF" * 388)
block_check("C6 macros", "macros", mb, [0xA000])
pm = cfg.parse_macros(cfg.read_block(t, "macros", log=quiet))
want0 = [{"t": "down", "code": 0xE0}, {"t": "delay", "ms": 10}, {"t": "down", "code": 0x06}, {"t": "delay", "ms": 30},
         {"t": "up", "code": 0x06}, {"t": "delay", "ms": 10}, {"t": "up", "code": 0xE0}, {"t": "delay", "ms": 10}]
want2 = [{"t": "mdown", "button": "right"}, {"t": "delay", "ms": 30}, {"t": "mup", "button": "right"},
         {"t": "delay", "ms": 10}]
check("C6 macros read back (MSI rhythm: a delay after every step, 10 ms at least)",
      len(pm) == 3 and pm[0]["steps"] == want0 and pm[1] is None and pm[2]["steps"] == want2, str(pm))
big = [{"name": "m%d" % i, "steps": [{"t": "down", "code": 4}, {"t": "up", "code": 4}] * 21} for i in range(20)]
try:
    cfg.build_macros(big)
    check("C6 too many macro steps refused before sending", False)
except ValueError:
    check("C6 too many macro steps refused before sending", True)
fill, steps = [], []
while True:                       # largest single macro that fits
    steps.append({"t": "down", "code": 4})
    try:
        cfg.build_macros([{"steps": steps}])
    except ValueError:
        steps.pop()
        break
mx = cfg.build_macros([{"steps": steps}])
check("C6 the largest macro block is 48 packets, never 49", len(mx) == 48 * 64, str(len(mx)))
block_check("C6 largest macro block", "macros", mx, [0xA000, 0xA400, 0xA800])
check("C6 the Fn layer survives the largest macro block (0xAC00 not erased)", emu.iflash(0xAC00, 576) == fn)
check("C6 macro capacity matches the packet limit", cfg.macro_capacity() == 47 * 64
      and cfg.macro_bytes([{"steps": steps}]) <= cfg.macro_capacity())

base = cfg.read_block(t, "settings", log=quiet)
check("C7 factory settings read: sleep 5 min, key response 2", cfg.parse_settings(base) ==
      {"no_alt_tab": False, "no_alt_f4": False, "no_win": False, "fn_toggle": False, "sleep": 2, "debounce": 2},
      str(cfg.parse_settings(base)))
st = cfg.build_settings({"no_win": True, "no_alt_f4": True, "fn_toggle": True, "sleep": 3, "debounce": 4}, base)
block_check("C7 settings", "settings", st, [0x9000])
check("C7 firmware applied them: Win locked, Fn toggle, 30 min sleep, key response 4",
      emu.u8(0x20000054) & 1 and emu.u8(0x200000C0) == 1 and emu.u32(0x2000010C) == 18000 and emu.u8(0x20000056) == 4
      and emu.u8(0x200000BA) & 0x40, "54=%x c0=%x 10c=%d 56=%d ba=%x" % (emu.u8(0x20000054), emu.u8(0x200000C0),
                                                                       emu.u32(0x2000010C), emu.u8(0x20000056), emu.u8(0x200000BA)))
check("C7 unknown bytes kept from the keyboard (byte 1 stays 0)", st[1] == base[1] == 0)
check("C7 settings read back", cfg.parse_settings(cfg.read_block(t, "settings", log=quiet)) ==
      {"no_alt_tab": False, "no_alt_f4": True, "no_win": True, "fn_toggle": True, "sleep": 3, "debounce": 4})
check("C7 without a keyboard copy: MSI's block (byte 1 = 1)", cfg.build_settings({})[1] == 1)

n0 = len(emu.iflash_ops)
when = datetime.datetime(2026, 11, 23, 18, 7, 42)
cfg.set_clock(t, when, log=quiet)
check("C8 clock set (RTC 26-11-23 18:07:42), no flash write",
      emu.rb(0x200001F3, 7) == bytes([26, 11, 0, 23, 18, 7, 42]) and not emu.iflash_ops[n0:],
      emu.rb(0x200001F3, 7).hex())
check("C8 protocol idle afterwards", clean(emu))

n0 = len(emu.iflash_ops)
light.set_lighting(t, 11, (255, 0, 0), 5, 3, 0, True, log=quiet)
check("C9 lighting effect stored through the checked writer", emu.iflash(0x9800, 16) == light.payload(11, (255, 0, 0), 5, 3, 0, True)[:16]
      and written_pages(n0) == [0x9800] and clean(emu))
check("C9 a read right after a lighting write works (no echo read left pending)",
      cfg.parse_lighting(cfg.read_block(t, "lighting", log=quiet))["effect"] == 11)

after = emu.iflash(0x8000, F.FLASH_END - 0x8000)
touched = sorted({(i + 0x8000) & ~0x3FF for i in range(len(before)) if before[i] != after[i]})
check("C10 MCU flash: only the configuration pages changed", set(touched) <= {0x9000, 0x9400, 0x9800, 0x9C00, 0xA000, 0xA400, 0xA800, 0xAC00},
      str([hex(p) for p in touched]))
check("C10 code pages untouched (0x8000-0x8FFF and from 0xB000)", before[:0x1000] == after[:0x1000]
      and before[0x3000:] == after[0x3000:])
check("C10 SPI flash (screen) untouched", not emu.flash.ops)
check("C10 no program over unerased bytes, nothing refused", not emu.overprogram and not emu.refused)


# ---------------------------------------------------------------- C11 errors
class Flip(E.EmulatedTransport):
    """Corrupts one byte of the 3rd data packet, like a bad cable would."""
    def __init__(self, emu):
        super().__init__(emu)
        self.n = 0

    def set_feature(self, p):
        p = bytearray(p)
        if p[0] != 0x04:
            self.n += 1
            if self.n == 3:
                p[10] ^= 0x40
        super().set_feature(bytes(p))


class NoSum(E.EmulatedTransport):
    """A firmware that answers 04 02 without the read-back sum (MSI's software ignores it)."""
    def __init__(self, emu, flip=False):
        super().__init__(emu)
        self.last, self.n, self.flip = b"", 0, flip

    def set_feature(self, p):
        p = bytearray(p)
        self.last = bytes(p[:2])
        if p[0] != 0x04:
            self.n += 1
            if self.flip and self.n == 3:
                p[10] ^= 0x40
        super().set_feature(bytes(p))

    def get_feature(self):
        r = bytearray(super().get_feature())
        if self.last == b"\x04\x02" and len(r) >= 8:
            r[4:8] = bytes(4)
        return bytes(r)


emu2, _ = new()
try:
    cfg.write_block(Flip(emu2), "keys", k, log=quiet)
    check("C11 a corrupted packet is caught by the sum", False)
except g.RestoreError as e:
    check("C11 a corrupted packet is caught by the sum", "check failed" in str(e), str(e))
emu4, _ = new()
try:
    cfg.write_block(NoSum(emu4), "keys", k, log=quiet)
    check("C11 no sum from the keyboard: the write is checked by reading it back", emu4.iflash(0x9400, 576) == k)
except g.RestoreError as e:
    check("C11 no sum from the keyboard: the write is checked by reading it back", False, str(e))
try:
    cfg.write_block(NoSum(emu4, flip=True), "colours", c, log=quiet)
    check("C11 no sum from the keyboard: a corrupted packet is still caught", False)
except g.RestoreError as e:
    check("C11 no sum from the keyboard: a corrupted packet is still caught", "different data" in str(e), str(e))
for name, data in (("keys", k[:-2] + b"\x00\x00"), ("lighting", bytes(64)), ("macros", bytes(49 * 64 - 2) + b"\xAA\x55"),
                   ("settings", bytes(60))):
    n_before = len(emu2.calls)
    try:
        cfg.write_block(E.EmulatedTransport(emu2), name, data, log=quiet)
        check("C11 bad %s block refused before sending" % name, False)
    except g.RestoreError:
        check("C11 bad %s block refused before sending" % name, True)


class NoRead(E.EmulatedTransport):
    """A firmware without the read commands: they get no acknowledgement."""
    def set_feature(self, p):
        if p[0] == 0x04 and p[1] in (0x10, 0x12, 0x14, 0x16, 0x22, 0x26):
            p = bytes([0x04, 0x77]) + bytes(62)
        super().set_feature(p)


emu3, _ = new()
try:
    cfg.read_block(NoRead(emu3), "keys", log=quiet)
    check("C11 read refused -> NotSupported", False)
except cfg.NotSupported:
    check("C11 read refused -> NotSupported", True)
parsed, raw, errors = cfg.read_all(NoRead(emu3), ("keys", "settings"), log=quiet)
check("C11 read_all reports unsupported parts", errors == {"keys": "not_supported", "settings": "not_supported"}, str(errors))

n_ok = sum(1 for _, ok, _ in results if ok)
print("\n%d/%d checks passed" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)

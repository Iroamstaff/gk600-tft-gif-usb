#!/usr/bin/env python3
"""
Runs the real command-line entry point of gk600_restore.py (main()) with a fake
`hid` module that mimics hidapi on Windows (report ID 0 prefix on writes and
feature reports, ID stripped on reads) and forwards everything to the emulated
Frieren V1.17 firmware. Covers: enumeration, collection selection, dry run,
probe, unprobe, restore, refusal when not idle.

Usage: python -I test_cli_with_fake_hidapi.py <frieren_v117.bin> <16 MiB dump> <tool dir> <emu dir>
"""
import hashlib
import io
import os
import random
import sys
import types
from contextlib import redirect_stdout

FW, DUMP, TOOL_DIR, EMU_DIR = sys.argv[1:5]
sys.path.insert(0, TOOL_DIR)
sys.path.insert(0, EMU_DIR)
from gk600_fw_emu import FirmwareEmu, SpiFlash  # noqa: E402

fw = open(FW, "rb").read()
ref = open(DUMP, "rb").read()
fails = 0


def make_fake_hid(emu, writes):
    m = types.ModuleType("hid")
    base = dict(vendor_id=0x0DB0, product_id=0xEA47, serial_number="", release_number=0x0120,
                manufacturer_string="MSI", product_string="MSI FORGE GK600 TKL WIRELESS Keyboard")
    entries = [dict(base, path=b"kbd", usage_page=0x0001, usage=6, interface_number=0),
               dict(base, path=b"data", usage_page=0xFF68, usage=1, interface_number=2),
               dict(base, path=b"ctrl", usage_page=0xFF13, usage=1, interface_number=3)]
    m.enumerate = lambda vid=0, pid=0: [e for e in entries if vid in (0, e["vendor_id"])]

    class Device:
        def open_path(self, p):
            self.p = p

        def set_nonblocking(self, v):
            pass

        def close(self):
            pass

        def send_feature_report(self, buf):
            buf = bytes(buf)
            assert self.p == b"ctrl" and len(buf) == 65 and buf[0] == 0, (self.p, len(buf))
            emu.host_set_feature(buf[1:])
            return 65

        def get_feature_report(self, rid, n):
            assert self.p == b"ctrl" and rid == 0 and n == 65
            return [0] + list(emu.host_get_feature())        # Windows: report ID first

        def write(self, buf):
            buf = bytes(buf)
            assert self.p == b"data" and len(buf) == 4097 and buf[0] == 0
            writes.append(1)
            emu.host_write_page(buf[1:])
            return 4097

        def read(self, n, timeout_ms=0):
            assert self.p == b"data"
            a = emu.host_read_ep4()
            return list(a) if a else []                       # ID 0 stripped by hidapi

    m.device = Device
    return m


def run(args, flash_img, setup=None):
    flash = SpiFlash(16 << 20, init=flash_img)
    emu = FirmwareEmu(fw, flash)
    if setup:
        setup(emu)
    writes = []
    sys.modules["hid"] = make_fake_hid(emu, writes)
    import gk600_restore as T
    T.time.sleep = lambda s: emu.tick_ms(int(round(s * 1000)))
    out = io.StringIO()
    with redirect_stdout(out):
        rc = T.main(args + ["--log", ""])
    return rc, flash, out.getvalue(), writes, T


def check(name, cond, detail=""):
    global fails
    fails += 0 if cond else 1
    print(("PASS " if cond else "FAIL ") + name + ((" - " + detail) if detail else ""))


bad = bytearray(ref)
rnd = random.Random(7)
bad[:0x120000] = bytes(rnd.getrandbits(8) for _ in range(0x120000))

rc, flash, out, writes, T = run(["check"], bytearray(ref))
check("check: finds the FF13/FF68 pair and the handshake passes",
      rc == 0 and "Handshake OK" in out and "V1.20" in out and not writes)

rc, flash, out, writes, T = run(["restore", "--image", DUMP], bytearray(bad))
check("restore without --write is a dry run (no page sent, flash unchanged)",
      rc == 0 and not writes and bytes(flash.mem) == bytes(bad) and "DRY RUN" in out)

rc, flash, out, writes, T = run(["probe", "--image", DUMP, "--write", "--yes"], bytearray(ref))
check("probe --write: 17 pages, striped icons + test card in [0, 0x11000), rest untouched",
      rc == 0 and len(writes) == 17 and bytes(flash.mem[:0x11000]) == T.probe_image(ref[:0x1A0000])
      and bytes(flash.mem[0x11000:]) == ref[0x11000:])

rc, flash, out, writes, T = run(["unprobe", "--image", DUMP, "--write", "--yes"], bytearray(flash.mem))
check("unprobe --write: back to the reference bytes", rc == 0 and bytes(flash.mem) == ref)

rc, flash, out, writes, T = run(["restore", "--image", DUMP, "--write", "--yes"], bytearray(bad))
check("restore --write from the 16 MiB dump repairs the whole flash",
      rc == 0 and len(writes) == 416 and bytes(flash.mem) == ref, hashlib.sha256(flash.mem).hexdigest()[:16])


def leave_busy(emu):
    emu.host_set_feature(bytes([4, 0x18]) + bytes(62))
    emu.host_get_feature()
    emu.host_set_feature(bytes([4, 0x38, 0, 0, 0, 0, 0, 0, 5, 0]) + bytes(54))
    emu.host_get_feature()


rc, flash, out, writes, T = run(["restore", "--image", DUMP, "--write", "--yes"], bytearray(bad), leave_busy)
check("restore refuses a keyboard left busy, sends no page",
      rc == 2 and not writes and "not idle" in out and bytes(flash.mem) == bytes(bad))

boot_bad = bytearray(ref)
boot_bad[:0x300000] = bytes(rnd.getrandbits(8) for _ in range(0x300000))
rc, flash, out, writes, T = run(["restore", "--with-boot", "--image", DUMP, "--write", "--yes"], bytearray(boot_bad))
check("restore --with-boot: 960 pages, menus and boot animation back to the dump",
      rc == 0 and len(writes) == 960 and bytes(flash.mem) == ref)

import tempfile  # noqa: E402
tmp = os.path.join(tempfile.mkdtemp(), "RESSOURCES_0_1A0000.bin")
open(tmp, "wb").write(ref[:0x1A0000])
rc, flash, out, writes, T = run(["restore", "--with-boot", "--image", tmp, "--write", "--yes"], bytearray(boot_bad))
check("restore --with-boot refuses the menus-only extract (full dump needed), sends nothing",
      rc == 2 and not writes and "full 16 MiB dump" in out)

print("\n%s" % ("ALL PASSED" if not fails else "%d FAILED" % fails))
sys.exit(1 if fails else 0)

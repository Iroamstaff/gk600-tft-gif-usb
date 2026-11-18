#!/usr/bin/env python3
"""
Runs gk600_home_picture.py (main()) against the emulated Frieren V1.17 firmware through the
fake Windows-style `hid` module of test_cli_with_fake_hidapi.py, then gk600_restore.py restore.

Usage: python -I test_home_picture.py <frieren_v117.bin> <16 MiB dump> <tool dir> <emu dir> <picture>
"""
import hashlib
import io
import sys
import types
from contextlib import redirect_stdout

FW, DUMP, TOOL_DIR, EMU_DIR, PIC = sys.argv[1:6]
sys.path.insert(0, TOOL_DIR)
sys.path.insert(0, EMU_DIR)
from gk600_fw_emu import FirmwareEmu, SpiFlash  # noqa: E402

fw = open(FW, "rb").read()
ref = open(DUMP, "rb").read()
pic = open(PIC, "rb").read()
fails = 0


def check(name, cond, detail=""):
    global fails
    fails += 0 if cond else 1
    print(("PASS " if cond else "FAIL ") + name + ((" - " + detail) if detail else ""))


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


def run_main(module, args, flash_img):
    flash = SpiFlash(16 << 20, init=flash_img)
    emu = FirmwareEmu(fw, flash)
    writes = []
    sys.modules["hid"] = make_fake_hid(emu, writes)
    import gk600_restore as T
    T.time.sleep = lambda s: emu.tick_ms(int(round(s * 1000)))
    mod = __import__(module)
    out = io.StringIO()
    with redirect_stdout(out):
        rc = mod.main(args + ["--log", ""])
    return rc, flash, out.getvalue(), writes


A, E = 0x17A1CE, 0x17A1CE + len(pic)
rc, flash, out, writes = run_main("gk600_home_picture", [PIC, "--image", DUMP], bytearray(ref))
check("picture without --write is a dry run", rc == 0 and not writes and bytes(flash.mem) == ref)

rc, flash, out, writes = run_main("gk600_home_picture", [PIC, "--image", DUMP, "--write", "--yes"], bytearray(ref))
m = bytes(flash.mem)
check("picture --write: 384 pages acknowledged", rc == 0 and len(writes) == 384, out[-200:] if rc else "")
check("picture bytes at 0x17A1CE, 160 x 65", m[A:E] == pic)
check("[0, 0x17A1CE) and [0x17F30E, end) equal the dump", m[:A] == ref[:A] and m[E:] == ref[E:])
after = bytearray(m)

rc, flash, out, writes = run_main("gk600_restore", ["restore", "--image", DUMP, "--write", "--yes"], after)
check("restore brings the dragon back, whole chip = dump",
      rc == 0 and len(writes) == 416 and bytes(flash.mem) == ref, hashlib.sha256(flash.mem).hexdigest()[:16])

print("\n" + ("ALL PASSED" if fails == 0 else "%d FAILED" % fails))
sys.exit(1 if fails else 0)

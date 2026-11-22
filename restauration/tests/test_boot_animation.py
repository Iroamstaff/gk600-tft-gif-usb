#!/usr/bin/env python3
"""
Checks gk600_boot_animation.py against the real Frieren V1.17 firmware code, emulated:
  1. playback: the boot area the tool builds is played by the real boot code (0xF104, header
     read 0xFE04, 2 ms tick 0x11428, screen task 0xFE7E): same frames, same times as the
     tool announces, for several animations;
  2. transfer: main() --write goes through the emulated USB path (fake Windows-style hid),
     every page is acknowledged, the flash holds the payload and nothing else changed;
     then gk600_restore.py restore --with-boot puts the whole chip back to the dump.

Usage: python -I test_boot_animation.py <frieren_v117.bin> <16 MiB dump> <tool dir> <emu dir> <gif>...
"""
import io
import os
import struct
import sys
import tempfile
import types
from contextlib import redirect_stdout

FW, DUMP, TOOL_DIR, EMU_DIR = sys.argv[1:5]
GIFS = sys.argv[5:]
sys.path.insert(0, TOOL_DIR)
sys.path.insert(0, EMU_DIR)
import gk600_fw_emu as fe                      # noqa: E402
from unicorn import UC_HOOK_CODE               # noqa: E402
from unicorn.arm_const import UC_ARM_REG_SP    # noqa: E402

fw = open(FW, "rb").read()
ref = open(DUMP, "rb").read()
fails = 0


def check(name, cond, detail=""):
    global fails
    fails += 0 if cond else 1
    print(("PASS " if cond else "FAIL ") + name + ((" - " + detail) if detail else ""))


# ------------------------------------------------------------------ 1. playback
fe.STUBS.update({0x7822: "LCD reset", 0x7836: "LCD init", 0x7BF4: "blit", 0xF850: "draw element",
                 0x6EE0: "wdt delay"})
SCR, START, FPTR = 0x200001FC, 0x20000203, 0x200001E8


def emulate_boot(flash_img, start=0, max_ticks=30000):
    """[(flash address of the frame, ms on screen)], end ('status' | 'GIF')."""
    emu = fe.FirmwareEmu(fw, fe.SpiFlash(init=flash_img))

    def spi_send(uc, addr, size, _):            # 0x8F64: command / address bytes of a read
        emu.flash.xfer(uc.reg_read(fe.UC_ARM_REG_R0) & 0xFF)
        uc.reg_write(fe.UC_ARM_REG_PC, uc.reg_read(fe.UC_ARM_REG_LR) | 1)
    shown, now = [], [0]

    def blit(uc, addr, size, _):
        a = struct.unpack("<I", uc.mem_read(uc.reg_read(UC_ARM_REG_SP), 4))[0]
        shown.append((now[0], a))
    emu.uc.hook_add(UC_HOOK_CODE, spi_send, begin=0x8F64, end=0x8F64)
    emu.uc.hook_add(UC_HOOK_CODE, blit, begin=0x7BF4, end=0x7BF4)
    emu.w8(START, start)
    emu.call(0xF104)
    end = None
    for tick in range(1, max_ticks + 1):
        now[0] = tick
        emu.call(0x11428)
        while emu.u8(SCR + 1) != emu.u8(SCR + 2):
            emu.calls.clear()
            emu.call(0xFE7E)
            calls = [(n, r0) for (_, n, r0) in emu.calls]
            if ("draw element", 0x48) in calls:
                shown.append((tick, emu.u32(FPTR)))
            if "user animation reload FE20" in [n for n, _ in calls]:
                end = (tick, "GIF")
            elif emu.u8(SCR + 5) != 0:
                end = (tick, "status")
        if end:
            break
    out = []
    for k, (tick, a) in enumerate(shown):
        nxt = shown[k + 1][0] if k + 1 < len(shown) else end[0]
        out.append((a, (nxt - tick) * 2))
    return out, end[1] if end else None


import gk600_boot_animation as B    # noqa: E402


def frames_of(spec):
    """Synthetic animation: [(ms, colour)] -> frames as the tool would load them."""
    return [(bytes([c & 0xFF, c >> 8]) * (B.W * B.H), ms) for ms, c in spec]


cases = []
for path in GIFS:
    cases.append((os.path.basename(path), B.load_animation(path), B.LEAD_IN_MS))
cases += [
    ("one picture", frames_of([(100, 0xF800)]), B.LEAD_IN_MS),
    ("two frames", frames_of([(100, 0xF800), (100, 0x07E0)]), B.LEAD_IN_MS),
    ("no lead-in, 100/200/300 ms", frames_of([(100, 1), (200, 2), (300, 3), (100, 4)]), 0),
    ("1.2 s frames (split)", frames_of([(1200, 5), (1200, 6), (1200, 7)]), B.LEAD_IN_MS),
    ("200 frames x 30 ms", frames_of([(30, i) for i in range(200)]), B.LEAD_IN_MS),
]
for name, frames, lead in cases:
    slots, used = B.plan(frames, lead)
    area = B.build_boot_area(slots)
    payload = B.build_payload(ref[:B.HDR_ADDR], area)
    img = bytearray(ref)
    img[:len(payload)] = payload
    got, end = emulate_boot(bytes(img))
    want = B.playback(slots)
    same_times = [ms for _, ms in got] == [ms for _, ms in want]
    same_frames = all(img[a:a + B.FRAME_SIZE] == data for (a, _), (data, _) in zip(got, want))
    check("playback %-28s %2d frames, %5d ms" % (name, len(slots), sum(ms for _, ms in got)),
          same_times and same_frames and len(got) == len(want) and end == "status",
          "" if same_times else "emulated %s / tool %s" % ([ms for _, ms in got][:12],
                                                          [ms for _, ms in want][:12]))
    check("  fits before 0x3C0000 (%d pages)" % (len(payload) // 4096),
          len(slots) <= 72 and len(payload) <= 0x3C0000 and len(payload) % 4096 == 0)

slots, _ = B.plan(frames_of([(100, 1), (100, 2), (100, 3)]), 0)
img = bytearray(ref)
p = B.build_payload(ref[:B.HDR_ADDR], B.build_boot_area(slots))
img[:len(p)] = p
check("start screen = GIF: the GIF follows the boot animation", emulate_boot(bytes(img), start=6)[1] == "GIF")
check("72 frames end at 0x%X, below 0x3C0000" % (B.FRAMES_ADDR + 72 * B.FRAME_SIZE),
      B.MAX_FRAMES == 72 and B.FRAMES_ADDR + 72 * B.FRAME_SIZE <= 0x3C0000 < B.FRAMES_ADDR + 73 * B.FRAME_SIZE)


# ------------------------------------------------------------------ 2. transfer
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
            assert self.p == b"ctrl" and len(buf) == 65 and buf[0] == 0
            emu.host_set_feature(buf[1:])
            return 65

        def get_feature_report(self, rid, n):
            assert self.p == b"ctrl" and rid == 0 and n == 65
            return [0] + list(emu.host_get_feature())

        def write(self, buf):
            buf = bytes(buf)
            assert self.p == b"data" and len(buf) == 4097 and buf[0] == 0
            writes.append(1)
            emu.host_write_page(buf[1:])
            return 4097

        def read(self, n, timeout_ms=0):
            a = emu.host_read_ep4()
            return list(a) if a else []

    m.device = Device
    return m


def run_main(module, args, flash_img):
    flash = fe.SpiFlash(16 << 20, init=flash_img)
    emu = fe.FirmwareEmu(fw, flash)
    writes = []
    sys.modules["hid"] = make_fake_hid(emu, writes)
    import gk600_restore as T
    T.time.sleep = lambda s: emu.tick_ms(int(round(s * 1000)))
    mod = __import__(module)
    out = io.StringIO()
    with redirect_stdout(out):
        rc = mod.main(args + ["--log", ""])
    return rc, flash, out.getvalue(), writes


if GIFS:
    gif = GIFS[0]
    rc, flash, out, writes = run_main("gk600_boot_animation", [gif, "--image", DUMP], bytearray(ref))
    check("dry run sends nothing", rc == 0 and not writes and bytes(flash.mem) == ref)
    tmp = os.path.join(tempfile.mkdtemp(), "p.gif")
    rc, flash, out, writes = run_main("gk600_boot_animation", [gif, "--image", DUMP, "--preview", tmp],
                                      bytearray(ref))
    check("preview sends nothing and writes the preview", rc == 0 and not writes and os.path.getsize(tmp) > 0)

    slots, _ = B.plan(B.load_animation(gif), B.LEAD_IN_MS)
    payload = B.build_payload(ref[:B.HDR_ADDR], B.build_boot_area(slots))
    rc, flash, out, writes = run_main("gk600_boot_animation", [gif, "--image", DUMP, "--write", "--yes"],
                                      bytearray(ref))
    m = bytes(flash.mem)
    check("--write: %d pages acknowledged" % (len(payload) // 4096),
          rc == 0 and len(writes) == len(payload) // 4096, out[-300:] if rc else "")
    check("flash = payload on [0, 0x%X), dump everywhere else" % len(payload),
          m[:len(payload)] == payload and m[len(payload):] == ref[len(payload):])
    check("menus and icons unchanged, user GIF untouched",
          m[:B.HDR_ADDR] == ref[:B.HDR_ADDR] and m[0x3C0000:] == ref[0x3C0000:])
    got, end = emulate_boot(m)
    check("the written chip plays the new animation", [ms for _, ms in got] == [ms for _, ms in B.playback(slots)])

    home = os.path.join(os.path.dirname(tmp), "home.rgb565")
    open(home, "wb").write(bytes(range(256)) * 81 + bytes(64))       # 20 800 bytes
    rc, flash2, out, writes = run_main("gk600_boot_animation",
                                       [gif, "--image", DUMP, "--home", home, "--write", "--yes"],
                                       bytearray(ref))
    m2 = bytes(flash2.mem)
    import gk600_home_picture as hp
    check("--home: home picture written at 0x17A1CE, rest identical",
          rc == 0 and m2[hp.PIC_ADDR:hp.PIC_ADDR + hp.PIC_SIZE] == open(home, "rb").read()
          and m2[:hp.PIC_ADDR] == m[:hp.PIC_ADDR] and m2[hp.PIC_ADDR + hp.PIC_SIZE:] == m[hp.PIC_ADDR + hp.PIC_SIZE:])

    rc, flash, out, writes = run_main("gk600_restore", ["restore", "--with-boot", "--image", DUMP,
                                                        "--write", "--yes"], bytearray(m2))
    check("restore --with-boot: whole chip back to the dump (960 pages)",
          rc == 0 and len(writes) == 960 and bytes(flash.mem) == ref)

print("\n" + ("ALL PASSED" if fails == 0 else "%d FAILED" % fails))
sys.exit(1 if fails else 0)

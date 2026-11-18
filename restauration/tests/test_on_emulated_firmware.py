#!/usr/bin/env python3
"""
End-to-end checks of gk600_restore.py against the REAL Frieren V1.17 firmware code
(run in Unicorn by gk600_fw_emu.py), with an emulated SPI NOR flash.

Usage:
  python -I test_on_emulated_firmware.py <frieren_v117.bin> <public 16 MiB dump> <tool dir> <emu dir> [--slow]

Writes results to results.json next to this file. Exit code 0 = all checks passed.
"""
import hashlib
import json
import os
import random
import sys
import time

FW, DUMP, TOOL_DIR, EMU_DIR = sys.argv[1:5]
SLOW = "--slow" in sys.argv
sys.path.insert(0, TOOL_DIR)
sys.path.insert(0, EMU_DIR)
import gk600_restore as T                          # noqa: E402
from gk600_fw_emu import FirmwareEmu, SpiFlash, EmulatedTransport, DISP_MODE  # noqa: E402

fw = open(FW, "rb").read()
ref = open(DUMP, "rb").read()
assert hashlib.sha256(ref).hexdigest() == T.DUMP_SHA256
MENUS = ref[:T.MENUS_END]
results = []
quiet = lambda *a, **k: None                       # noqa: E731


def check(name, cond, detail=""):
    results.append({"check": name, "ok": bool(cond), "detail": detail})
    print(("PASS " if cond else "FAIL ") + name + ((" - " + detail) if detail else ""))
    return cond


def ops_summary(flash):
    er = [o for o in flash.ops if o[0] == "erase"]
    pr = [o for o in flash.ops if o[0] == "program"]
    rf = [o for o in flash.ops if o[0] == "refused"]
    span = (min(o[1] for o in er), max(o[1] for o in er) + 0x1000) if er else None
    return er, pr, rf, span


def corrupted(size=16 << 20, upto=0x150000, seed=1):
    img = bytearray(ref[:size]) if size == len(ref) else bytearray(ref[:size])
    rnd = random.Random(seed)
    img[0:upto] = bytes(rnd.getrandbits(8) for _ in range(upto))
    return img


def fresh(flash_img, size=16 << 20):
    flash = SpiFlash(size, init=flash_img)
    return FirmwareEmu(fw, flash), flash


def gif_upload_0472(emu, frames):
    """What the MSI driver does for a GIF of `frames` frames (04 18 / 04 72 / pages / 04 02)."""
    t = EmulatedTransport(emu)
    size = 256 + frames * 160 * 96 * 2
    pages = -(-size // 4096)
    T.command(t, 0x18)
    r = T.command(t, 0x72, 1, pages & 0xFFFF)
    assert r[3] == 1, r[:10].hex()
    rnd = random.Random(frames)
    for i in range(pages):
        emu.host_write_page(bytes(rnd.getrandbits(8) for _ in range(4096)) if i < 3 else bytes([i & 0xFF]) * 4096)
        assert emu.host_read_ep4()[:3] == T.ACK
    T.command(t, 0x02)
    return pages


t_start = time.time()

# ---------------------------------------------------------------- S0 command bytes
c18, c02 = T.build_command(0x18), T.build_command(0x02)
check("S0 04 18 / 04 02 identical to the MSI driver (04 xx then 62 zero bytes)",
      c18 == bytes([4, 0x18]) + bytes(62) and c02 == bytes([4, 0x02]) + bytes(62))
c38 = T.build_command(0x38, 0, 416)
check("S0 04 38 carries the page count little-endian at bytes 8-9 (same slot as 04 72)",
      c38[:10] == bytes([4, 0x38, 0, 0, 0, 0, 0, 0, 0xA0, 0x01]) and not any(c38[10:]))

# ---------------------------------------------------------------- S1 full restore
emu, flash = fresh(corrupted())
t = EmulatedTransport(emu)
pages = T.raw_write(t, MENUS, log=quiet)
er, pr, rf, span = ops_summary(flash)
check("S1 416 pages acknowledged, transaction closed", pages == 416 and emu.state == 0)
check("S1 SPI erases exactly cover [0, 0x1A0000)", len(er) == 416 and span == (0, 0x1A0000),
      "erases=%d span=%s" % (len(er), span and tuple(hex(x) for x in span)))
check("S1 16 page-programs per page, none refused", len(pr) == 416 * 16 and not rf)
check("S1 whole 16 MiB flash equals the reference dump afterwards", bytes(flash.mem) == ref,
      hashlib.sha256(flash.mem).hexdigest())
names = [c[1] for c in emu.calls]
check("S1 IRQ19/LED engine restarted once at the end (0x7E24)",
      names.count("LED engine restart (IRQ19 re-enable)") == 1)
check("S1 status screen redrawn (0xF868) and display mode back to 1",
      "display redraw F868" in names and emu.u8(DISP_MODE) == 1)
check("S1 user animation reload (0xFE20) NOT triggered by 04 38", "user animation reload FE20" not in names)
check("S1 internal MCU flash never touched",
      not any("INTERNAL FLASH" in n for n in names))
acks = [x for x in t.log if x[0] == "ACK"]
check("S1 every ACK is 01 5A 02", all(a[1] and a[1][:3] == T.ACK for a in acks) and len(acks) == 416)

# ---------------------------------------------------------------- S2 probe / unprobe
def status_screen_assets():
    """Runs the real status-screen code (0xF868 queue + 0xF156 display task) for every
    switch position and lock state, and returns the (address, w, h) it reads from flash."""
    import struct
    import gk600_fw_emu as E
    from unicorn import UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0
    saved = E.STUBS.pop(0xF868)
    found = set()
    try:
        for sel in (0, 1, 2):
            for locks in (0x00, 0x0F):
                e = E.FirmwareEmu(fw, E.SpiFlash(16 << 20, init=ref))
                uc = e.uc

                def draw(uc, addr, size, _):
                    sp = uc.reg_read(UC_ARM_REG_SP)
                    found.add((struct.unpack("<I", uc.mem_read(sp, 4))[0],
                               uc.reg_read(UC_ARM_REG_R2), uc.reg_read(UC_ARM_REG_R3)))
                    uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR) | 1)

                def stub(uc, addr, size, _):
                    uc.reg_write(UC_ARM_REG_R0, 0)
                    uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR) | 1)
                uc.hook_add(UC_HOOK_CODE, draw, begin=0x7BF4, end=0x7BF4)
                for a in (0x7A76, 0x7B04, 0x6B60):          # LCD window / pixel push / panel init
                    uc.hook_add(UC_HOOK_CODE, stub, begin=a, end=a)
                e.w8(0x200000E8, sel)
                e.w8(0x20000184, locks)
                e.w8(0x20000278, 1)
                e.w8(0x20000201, 1)
                e.call(0xF868)
                for _ in range(e.u8(0x200001E6) + 2):
                    e.call(0xF156)
    finally:
        E.STUBS[0xF868] = saved
    return found


assets = status_screen_assets()
icons = sorted(a for a in assets if a[0] not in (0x000000, 0x183FCE))
check("S2 status screen (real code, 3 switch positions x 2 lock states): background at 0x000000, "
      "edition picture, and %d icons, all inside the striped range [0x7800, 0x10806)" % len(icons),
      (0, 160, 96) in assets and len(icons) >= 10
      and all(T.ICONS[0] <= a and a + w * h * 2 <= T.ICONS[1] for a, w, h in icons))
emu, flash = fresh(bytearray(ref))
t = EmulatedTransport(emu)
T.raw_write(t, T.probe_image(MENUS), log=quiet)
er, pr, rf, span = ops_summary(flash)
check("S2 probe writes 17 pages, erases only [0, 0x11000)", span == (0, 0x11000) and len(er) == 17)
check("S2 probe leaves everything from 0x11000 untouched", bytes(flash.mem[0x11000:]) == ref[0x11000:])
check("S2 after the probe every icon the status screen draws is striped, the background holds the test card",
      bytes(flash.mem[:0x11000]) == T.probe_image(MENUS)
      and all(bytes(flash.mem[a:a + w * h * 2]) != ref[a:a + w * h * 2] for a, w, h in icons)
      and bytes(flash.mem[:T.CARD_END]) == T.test_card())
check("S2 reference background area is all zeros (black) before the probe", ref[:0x7800] == bytes(0x7800))
T.raw_write(EmulatedTransport(emu), T.unprobe_image(MENUS), log=quiet)
check("S2 unprobe restores the exact reference bytes", bytes(flash.mem) == ref)

# ---------------------------------------------------------------- S3 refusals
for bad, why in ((b"\x00" * 100, "not a multiple of 4096"), (b"", "empty"),
                 (b"\x00" * (T.USER_GIF + 4096), "beyond 0x3C0000")):
    try:
        T.raw_write(EmulatedTransport(emu), bad, log=quiet)
        ok = False
    except T.RestoreError:
        ok = True
    check("S3 payload refused: " + why, ok)

# ---------------------------------------------------------------- S4 not idle at start
for label, setup, expect in (
        ("transfer waiting for pages (state 5)",
         lambda e: (T.command(EmulatedTransport(e), 0x18), T.command(EmulatedTransport(e), 0x38, 0, 3)), 5),
        ("transfer waiting for 04 02 (state 3)",
         lambda e: (T.command(EmulatedTransport(e), 0x18), T.command(EmulatedTransport(e), 0x38, 0, 1),
                    e.host_write_page(MENUS[:4096]), e.host_read_ep4()), 3)):
    emu, flash = fresh(bytearray(ref))
    setup(emu)
    n_ops = len(flash.ops)
    st = emu.state
    try:
        T.raw_write(EmulatedTransport(emu), MENUS, log=quiet)
        refused = False
    except T.RestoreError as e:
        refused = "not idle" in str(e)
    check("S4 handshake refuses a keyboard left in a %s" % label,
          st == expect and refused and len(flash.ops) == n_ops)

# ---------------------------------------------------------------- S5 lost ACK
class DropAck(EmulatedTransport):
    def __init__(self, emu, at):
        super().__init__(emu)
        self.n, self.at = 0, at

    def read_ack(self, timeout_s):
        a = super().read_ack(timeout_s)
        self.n += 1
        return None if self.n == self.at else a


emu, flash = fresh(corrupted())
t = DropAck(emu, 100)
try:
    T.raw_write(t, MENUS, log=quiet)
    stopped = False
except T.RestoreError as e:
    stopped = "page 100/416" in str(e)
sent = sum(1 for x in t.log if x[0] == "PAGE")
check("S5 missing ACK stops the tool at once (no page sent after it)", stopped and sent == 100)
st5 = emu.state
emu.tick_ms(2001)
names = [c[1] for c in emu.calls]
check("S5 firmware gives up after ~2 s: state 0 but LED engine NOT restarted, display mode 0x0E",
      st5 == 5 and emu.state == 0 and "LED engine restart (IRQ19 re-enable)" not in names
      and emu.u8(DISP_MODE) == 0x0E,
      "this is why the docs say: power-cycle after any aborted transfer")
emu2, flash2 = fresh(bytearray(flash.mem))          # power cycle = new MCU, same flash
T.raw_write(EmulatedTransport(emu2), MENUS, log=quiet)
check("S5 after a power cycle the same command repairs everything", bytes(flash2.mem) == ref)

# ---------------------------------------------------------------- S6 stale fragment counter
emu, flash = fresh(corrupted())
for _ in range(10):                                  # interrupted earlier transfer: 10 stray fragments
    emu.host_write_fragment(b"\xAA" * 64)
k = emu.frag_counter
log6 = []
T.raw_write(EmulatedTransport(emu), MENUS, log=log6.append)
diff = sum(1 for a, b in zip(flash.mem[:T.MENUS_END], MENUS) if a != b)
check("S6 a stale fragment counter (K=%d) is invisible to the host but shifts the data" % k,
      k == 10 and emu.state == 0 and diff > 0, "%d bytes differ in [0, 0x1A0000)" % diff)
emu2, flash2 = fresh(bytearray(flash.mem))
T.raw_write(EmulatedTransport(emu2), MENUS, log=quiet)
check("S6 power cycle + same command -> exact reference", bytes(flash2.mem) == ref)

# ---------------------------------------------------------------- S7 byte 2 of 04 38
outs = []
for b2 in (0, 1):
    emu, flash = fresh(bytearray(ref))
    tr = EmulatedTransport(emu)
    T.command(tr, 0x18)
    T.command(tr, 0x38, b2, 7)
    for i in range(7):
        emu.host_write_page(T.probe_image(MENUS)[i * 4096:(i + 1) * 4096])
        emu.host_read_ep4()
    T.command(tr, 0x02)
    outs.append(bytes(flash.mem))
check("S7 byte 2 of 04 38 is ignored by this firmware (0 and 1 give the same flash)", outs[0] == outs[1])

# ---------------------------------------------------------------- S8 incident + repair, 8 MiB chip
size8 = 8 << 20
emu, flash = fresh(bytearray(ref[:size8]), size8)
pages = gif_upload_0472(emu, 200)
menus_hit = bytes(flash.mem[:T.MENUS_END]) != MENUS
boot_ok = bytes(flash.mem[0x1A0000:0x31E900]) == ref[0x1A0000:0x31E900]
check("S8 8 MiB chip + 200-frame GIF (%d pages, legal for the MSI driver): menus overwritten, boot animation intact"
      % pages, menus_hit and boot_ok)
emu2, flash2 = fresh(bytearray(flash.mem), size8)
T.raw_write(EmulatedTransport(emu2), MENUS, log=quiet)
check("S8 restore brings [0, 0x1A0000) back on the 8 MiB chip",
      bytes(flash2.mem[:T.MENUS_END]) == MENUS)

# ---------------------------------------------------------------- S9 incident + repair, 16 MiB chip (slow)
if SLOW:
    emu, flash = fresh(bytearray(ref))
    pages = gif_upload_0472(emu, 470)
    menus_hit = bytes(flash.mem[:T.MENUS_END]) != MENUS
    boot_ok = bytes(flash.mem[0x1A0000:0x31E900]) == ref[0x1A0000:0x31E900]
    check("S9 16 MiB chip + 470-frame GIF (%d pages, needs gif_maxframes raised): menus overwritten, boot intact"
          % pages, menus_hit and boot_ok)
    emu2, flash2 = fresh(bytearray(flash.mem))
    T.raw_write(EmulatedTransport(emu2), MENUS, log=quiet)
    check("S9 restore brings [0, 0x1A0000) back on the 16 MiB chip",
          bytes(flash2.mem[:T.MENUS_END]) == MENUS)

# ---------------------------------------------------------------- S10 --with-boot (menus + boot animation)
emu, flash = fresh(corrupted(upto=0x300000, seed=3))
T.raw_write(EmulatedTransport(emu), ref[:T.BOOT_END], log=quiet)
er, pr, rf, span = ops_summary(flash)
check("S10 --with-boot: 960 pages, erases exactly [0, 0x3C0000), whole chip back to the dump",
      len(er) == 960 and span == (0, 0x3C0000) and bytes(flash.mem) == ref)

# ---------------------------------------------------------------- S11 boot animation hit too (slow)
if SLOW:
    emu, flash = fresh(bytearray(ref))
    pages = gif_upload_0472(emu, 500)
    gif_area = bytes(flash.mem[T.USER_GIF:])
    boot_hit = bytes(flash.mem[0x1A0000:0x31E900]) != ref[0x1A0000:0x31E900]
    check("S11 16 MiB chip + 500-frame GIF (%d pages): menus AND boot animation overwritten" % pages,
          bytes(flash.mem[:T.MENUS_END]) != MENUS and boot_hit)
    emu2, flash2 = fresh(bytearray(flash.mem))
    T.raw_write(EmulatedTransport(emu2), MENUS, log=quiet)
    check("S11 plain restore fixes the menus but leaves the boot animation broken",
          bytes(flash2.mem[:T.MENUS_END]) == MENUS
          and bytes(flash2.mem[0x1A0000:0x31E900]) != ref[0x1A0000:0x31E900])
    emu3, flash3 = fresh(bytearray(flash2.mem))
    T.raw_write(EmulatedTransport(emu3), ref[:T.BOOT_END], log=quiet)
    check("S11 --with-boot restores [0, 0x3C0000) exactly and leaves the GIF area as it was",
          bytes(flash3.mem[:T.BOOT_END]) == ref[:T.BOOT_END] and bytes(flash3.mem[T.USER_GIF:]) == gif_area)

elapsed = time.time() - t_start
ok = all(r["ok"] for r in results)
out = {"firmware_sha256": hashlib.sha256(fw).hexdigest(), "dump_sha256": T.DUMP_SHA256,
       "tool_version": T.__version__, "elapsed_s": round(elapsed, 1), "all_passed": ok,
       "checks": results}
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.json"), "w"), indent=1)
print("\n%d/%d checks passed in %.0f s" % (sum(r["ok"] for r in results), len(results), elapsed))
sys.exit(0 if ok else 1)

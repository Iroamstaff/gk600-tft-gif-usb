#!/usr/bin/env python3
# SPDX-License-Identifier: CC-BY-4.0
"""
gk600_restore.py - restore the TFT screen resources (menus, icons) of an
MSI Forge GK600 TKL Wireless over USB, without opening the keyboard.

STATUS: EXPERIMENTAL.  The command sequence below was verified by running the
real Frieren V1.17 firmware code (same platform, same protocol) in an emulator.
It has NOT yet been confirmed on a GK600 (VID 0DB0 / PID EA47).  Run `probe`
first: it only touches the home-screen icons and background (first 68 KB) and
is easy to undo.

What it does (same transport as the official MSI driver, one command differs):
    04 18                -> open transaction          (identical to the driver)
    04 38 .. pages(LE)   -> raw write from SPI address 0x000000
                            (the driver's GIF upload uses 04 72 -> 0x3C0000)
    N x 4096-byte pages  -> each one ACKed by the keyboard with 01 5A 02
    04 02                -> close transaction         (identical to the driver)

Default image: the first 0x1A0000 bytes (416 pages) of the public GK600 dump,
i.e. every menu and icon, stopping right before the boot animation (0x1A0000)
and far below the user GIF (0x3C0000).

Commands:
    list        show matching HID devices (read-only)
    check       identify the keyboard and send the 04 18 handshake (no write)
    probe       first 68 KB (17 pages): every home-screen icon (battery, WIN/MAC,
                connection, lock indicators) becomes magenta/yellow stripes, and the
                black background at 0x000000 gets colour bars
    unprobe     put those 17 pages back from the reference dump
    restore     write the reference resources [0, 0x1A0000) (416 pages)
                --with-boot: also the boot animation area, [0, 0x3C0000) (960 pages,
                full 16 MiB dump needed)

Nothing is written unless --write is given.  Target: Windows. So far the tool
has only run against the emulated firmware (see tests/); Linux/macOS are untested.

Requirements: Python 3.8+, `pip install hidapi`
"""

import argparse
import hashlib
import os
import sys
import time

__version__ = "0.9.4-experimental"

# ---------------------------------------------------------------- constants
VID = 0x0DB0
KNOWN_PIDS = {
    0xEA47: "MSI FORGE GK600 TKL WIRELESS (USB)",
    0x54EB: "MSI FORGE TKL FRIEREN EDITION (USB)",
}
USAGE_PAGE_CTRL = 0xFF13      # MI_03 : 64-byte feature reports (commands)
USAGE_PAGE_DATA = 0xFF68      # MI_02 : 4096-byte output reports (pages) + 64-byte input (ACK)
PAGE = 4096
MENUS_END = 0x1A0000          # boot animation header lives here
USER_GIF = 0x3C0000           # user GIF (04 72) starts here - never touched by this tool
BOOT_END = USER_GIF           # --with-boot: menus + boot animation, up to the user GIF
PROBE_END = 0x11000           # 17 pages: background + every home-screen icon
CARD_END = 0x7000             # colour bars inside the black background (160x96 at 0x000000)
ICONS = (0x7800, 0x10806)     # battery x7, connection strips x10, A/1/WIN/MAC/lock (GK600 dump)
CMD_DELAY = 0.035             # rgb-keyboard.xml <cmd_delaytime value="35"/>
ACK = bytes([0x01, 0x5A, 0x02])

DUMP_SIZE = 16 << 20
DUMP_SHA256 = "d3a7359a69692e2d25994b8c886cdd87444342b509eaf505cb197664ab671b50"
MENUS_SHA256 = "d8b28e550239611ae82d628fd4766bdb0e797e8ca54b3d420aed40cb8bde30d5"


class RestoreError(Exception):
    pass


# ---------------------------------------------------------------- images
def rgb565le(r, g, b):
    v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return bytes((v & 0xFF, v >> 8))


def test_card():
    """Test card for the background area: 8 colour bars, then a checkerboard.
    160 px wide, RGB565 little-endian (the byte order used in the flash)."""
    bars = [(255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0),
            (255, 0, 255), (255, 0, 0), (0, 0, 255), (0, 0, 0)]
    out = bytearray()
    row = 0
    while len(out) < CARD_END:
        for x in range(160):
            if row < 44:
                c = bars[x // 20]
            else:
                c = (255, 255, 255) if ((x // 10) + ((row - 44) // 10)) % 2 == 0 else (255, 0, 0)
            out += rgb565le(*c)
        row += 1
    return bytes(out[:CARD_END])


def probe_image(reference):
    """First 17 pages of the reference, with the colour bars in the background and every
    home-screen icon replaced by magenta/yellow stripes (2 pixels each)."""
    img = bytearray(reference[:PROBE_END])
    img[:CARD_END] = test_card()
    a, b = ICONS
    stripes = bytearray()
    for i in range((b - a) // 2):
        stripes += rgb565le(255, 0, 255) if (i // 2) % 2 == 0 else rgb565le(255, 255, 0)
    img[a:b] = stripes
    return bytes(img)


def unprobe_image(reference):
    return bytes(reference[:PROBE_END])


def load_reference(path, end):
    """Accepts the full public dump (16 MiB) or the 0x1A0000-byte menus extract.
    Returns the [0, end) slice after checking SHA-256."""
    data = open(path, "rb").read()
    h = hashlib.sha256(data).hexdigest()
    if len(data) == DUMP_SIZE:
        if h != DUMP_SHA256:
            raise RestoreError("%s: unknown 16 MiB dump (SHA-256 %s)" % (path, h))
        return data[:end]
    if len(data) == MENUS_END:
        if end != MENUS_END:
            raise RestoreError("%s holds the menus only: --with-boot needs the full 16 MiB dump" % path)
        if h != MENUS_SHA256:
            raise RestoreError("%s: unknown menus image (SHA-256 %s)" % (path, h))
        return data
    raise RestoreError("%s: expected the 16 MiB dump or the %d-byte menus image, got %d bytes"
                       % (path, MENUS_END, len(data)))


def find_reference(explicit, end):
    candidates = [explicit] if explicit else []
    here = os.path.dirname(os.path.abspath(__file__))
    candidates += [os.path.join(here, n) for n in
                   ("Forge gk600 tkl wireless.bin", "RESSOURCES_0_1A0000.bin",
                    "RESSOURCES_0_1A0000_EXPERIMENTAL.bin")]
    for c in candidates:
        if c and os.path.isfile(c):
            return c, load_reference(c, end)
    raise RestoreError("reference image not found: pass --image <file> (full dump or menus extract)")


# ---------------------------------------------------------------- protocol
def build_command(op, b2=0, param16=0):
    b = bytearray(64)
    b[0] = 0x04
    b[1] = op
    b[2] = b2
    b[8] = param16 & 0xFF
    b[9] = (param16 >> 8) & 0xFF
    return bytes(b)


def command(t, op, b2=0, param16=0, log=None):
    payload = build_command(op, b2, param16)
    t.sleep(CMD_DELAY)
    t.set_feature(payload)
    t.sleep(CMD_DELAY)
    resp = bytes(t.get_feature())
    if log:
        log("  -> %s" % payload[:12].hex(" "))
        log("  <- %s" % resp[:12].hex(" "))
    return resp


STATE_HINT = {
    0x01: "idle (ready)",
    0x00: "busy: a previous transfer is still waiting for pages",
    0xFF: "busy: a previous transfer is waiting for its 04 02",
}


def handshake(t, log=print):
    """04 18 is what the MSI driver sends first. Byte 3 of the reply tells the
    protocol state (verified on the Frieren V1.17 code)."""
    r = command(t, 0x18, log=log)
    if r[0] != 0x04 or r[1] != 0x18:
        raise RestoreError("unexpected reply to 04 18: %s" % r[:8].hex(" "))
    if r[3] != 0x01:
        raise RestoreError("keyboard not idle (%s). Power it OFF and ON again "
                           "(the boot animation must play), then retry."
                           % STATE_HINT.get(r[3], "status 0x%02X" % r[3]))
    return r


def raw_write(t, payload, ack_timeout=2.0, log=print, progress=None):
    """Writes `payload` from SPI address 0 with 04 38. Stops at the first anomaly."""
    if not payload or len(payload) % PAGE:
        raise RestoreError("payload must be a non-empty multiple of 4096 bytes")
    pages = len(payload) // PAGE
    if len(payload) > USER_GIF:
        raise RestoreError("refusing to write at or beyond 0x3C0000 (user GIF area)")

    log("[1/4] 04 18 handshake")
    handshake(t, log=log)

    log("[2/4] 04 38 raw write from 0x000000, %d pages" % pages)
    r = command(t, 0x38, 0, pages, log=log)
    if r[0] != 0x04 or r[1] != 0x38 or r[3] != 0x01:
        raise RestoreError("04 38 refused (reply %s). No page was sent. Power-cycle the keyboard "
                           "before using it again." % r[:10].hex(" "))
    if r[8] | (r[9] << 8) != pages:
        raise RestoreError("04 38 echo carries a different page count: %s. No page was sent. "
                           "Power-cycle the keyboard before using it again." % r[:10].hex(" "))

    log("[3/4] sending %d pages (each must be acknowledged with 01 5A 02)" % pages)
    t0 = time.time()
    for i in range(pages):
        t.write_page(payload[i * PAGE:(i + 1) * PAGE])
        a = t.read_ack(ack_timeout)
        if a is None or bytes(a[:3]) != ACK:
            raise RestoreError(
                "page %d/%d: %s. STOP. Unplug the cable, power the keyboard OFF and ON, "
                "then run the same command again (it rewrites everything from the start)."
                % (i + 1, pages, "no ACK" if a is None else "bad ACK " + bytes(a[:8]).hex(" ")))
        if progress:
            progress(i + 1, pages, time.time() - t0)

    log("[4/4] 04 02 close")
    r = command(t, 0x02, log=log)
    if r[3] != 0x01:
        raise RestoreError("04 02 not acknowledged (reply %s). The pages were written; "
                           "power-cycle the keyboard and check the screen." % r[:8].hex(" "))
    return pages


# ---------------------------------------------------------------- hidapi transport
def _hid():
    try:
        import hid  # pip install hidapi
    except ImportError:
        raise RestoreError("Python module 'hid' missing: run  pip install hidapi")
    return hid


def enumerate_keyboards():
    hid = _hid()
    found = {}
    for d in hid.enumerate(VID, 0):
        if d["product_id"] not in KNOWN_PIDS:
            continue
        key = (d["product_id"], d.get("serial_number") or "")
        found.setdefault(key, []).append(d)
    return found


def win_caps(path):
    """Windows only: HIDP_CAPS report lengths of one collection.
    Returns None when not on Windows or when the query fails (advisory check)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class HIDP_CAPS(ctypes.Structure):
            _fields_ = [("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
                        ("InputReportByteLength", wintypes.USHORT),
                        ("OutputReportByteLength", wintypes.USHORT),
                        ("FeatureReportByteLength", wintypes.USHORT),
                        ("Reserved", wintypes.USHORT * 17),
                        ("Fields", wintypes.USHORT * 10)]
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        hidd = ctypes.WinDLL("hid")
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        hidd.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
        hidd.HidD_GetPreparsedData.restype = wintypes.BOOLEAN
        hidd.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
        hidd.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
        p = path.decode() if isinstance(path, bytes) else path
        h = k32.CreateFileW(p, 0, 3, None, 3, 0, None)
        if h is None or h == ctypes.c_void_p(-1).value:
            return None
        try:
            pp = ctypes.c_void_p()
            if not hidd.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                return None
            caps = HIDP_CAPS()
            hidd.HidP_GetCaps(pp, ctypes.byref(caps))
            hidd.HidD_FreePreparsedData(pp)
            return (caps.UsagePage, caps.InputReportByteLength,
                    caps.OutputReportByteLength, caps.FeatureReportByteLength)
        finally:
            k32.CloseHandle(h)
    except Exception:
        return None


CONFLICTING = ("DeviceDriver.exe", "OpenRGB.exe", "SignalRgb.exe", "SignalRGB.exe")


def other_software_running():
    """Windows: programs that also talk to the keyboard and could interleave commands."""
    if os.name != "nt":
        return []
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                             timeout=10).stdout.lower()
    except Exception:
        return []
    return [p for p in CONFLICTING if '"%s"' % p.lower() in out]


def select_keyboard(log=print):
    busy = other_software_running()
    if busy:
        raise RestoreError("close %s first (also from the system tray): it talks to the keyboard "
                           "and would mix its commands with ours" % ", ".join(busy))
    found = enumerate_keyboards()
    if not found:
        raise RestoreError("no GK600 / Frieren keyboard found in wired USB mode "
                           "(VID 0DB0, PID EA47 or 54EB). Plug the cable, wired mode.")
    if len(found) > 1:
        raise RestoreError("more than one matching keyboard: keep only one plugged in")
    (pid, _), entries = next(iter(found.items()))
    ctrl = [e for e in entries if e["usage_page"] == USAGE_PAGE_CTRL]
    data = [e for e in entries if e["usage_page"] == USAGE_PAGE_DATA]
    if len(ctrl) != 1 or len(data) != 1:
        raise RestoreError("expected one FF13 and one FF68 collection, found %d / %d"
                           % (len(ctrl), len(data)))
    ctrl, data = ctrl[0], data[0]
    info = {
        "pid": pid,
        "name": KNOWN_PIDS[pid],
        "product": ctrl.get("product_string"),
        "version": ctrl.get("release_number") or 0,
        "ctrl_if": ctrl.get("interface_number"),
        "data_if": data.get("interface_number"),
        "ctrl_path": ctrl["path"],
        "data_path": data["path"],
    }
    log("Keyboard : %s" % info["name"])
    log("Product  : %s" % info["product"])
    log("Firmware : V%X.%02X (bcdDevice 0x%04X)" % (info["version"] >> 8, info["version"] & 0xFF,
                                                    info["version"]))
    log("Command  : interface %s, usage page FF13" % info["ctrl_if"])
    log("Data     : interface %s, usage page FF68" % info["data_if"])
    if (info["ctrl_if"], info["data_if"]) != (3, 2):
        log("WARNING  : interface numbers differ from the measured GK600 layout (3 / 2)")
    cc, dc = win_caps(ctrl["path"]), win_caps(data["path"])
    if cc and dc:
        log("HIDP_CAPS: FF13 feature=%d  FF68 in=%d out=%d" % (cc[3], dc[1], dc[2]))
        if cc[3] != 65 or dc[2] != 4097 or dc[1] != 65:
            raise RestoreError("report lengths differ from the known layout "
                               "(expected feature 65, out 4097, in 65)")
    elif os.name == "nt":
        log("HIDP_CAPS: could not be read (advisory check skipped)")
    return info


class HidTransport:
    """hidapi on Windows: report ID 0 is prepended on writes and feature reports."""

    def __init__(self, info):
        hid = _hid()
        try:
            self.ctrl = hid.device()
            self.ctrl.open_path(info["ctrl_path"])
            self.data = hid.device()
            self.data.open_path(info["data_path"])
            self.data.set_nonblocking(0)
            for _ in range(64):                # drain stale input reports
                if not self.data.read(65, 20):
                    break
        except (OSError, ValueError) as e:
            raise RestoreError("cannot open the keyboard's HID collections (%s). Is another program "
                               "using it?" % e)

    def close(self):
        for d in (self.ctrl, self.data):
            try:
                d.close()
            except Exception:
                pass

    @staticmethod
    def _io(what, fn, *args):
        try:
            return fn(*args)
        except (OSError, ValueError) as e:
            raise RestoreError("%s failed (%s). If pages were being sent: unplug the cable, switch the "
                               "keyboard OFF and ON, then run the same command again." % (what, e))

    def set_feature(self, payload64):
        n = self._io("SET_FEATURE", self.ctrl.send_feature_report, b"\x00" + bytes(payload64))
        if n is None or n < 0:
            raise RestoreError("SET_FEATURE failed")

    def get_feature(self):
        r = bytes(self._io("GET_FEATURE", self.ctrl.get_feature_report, 0, 65))
        if len(r) == 65:
            r = r[1:]
        if len(r) < 64:
            raise RestoreError("short GET_FEATURE reply (%d bytes)" % len(r))
        return r[:64]

    def write_page(self, page4096):
        n = self._io("page write", self.data.write, b"\x00" + bytes(page4096))
        if n is None or n < PAGE:
            raise RestoreError("page write failed (%s)" % n)

    def read_ack(self, timeout_s):
        r = self._io("ACK read", self.data.read, 65, int(timeout_s * 1000))
        if not r:
            return None
        r = bytes(r)
        if len(r) == 65:
            r = r[1:]
        return r

    def sleep(self, seconds):
        time.sleep(seconds)


# ---------------------------------------------------------------- CLI
class Logger:
    def __init__(self, path):
        self.f = open(path, "a", encoding="utf-8") if path else None

    def __call__(self, msg):
        print(msg)
        if self.f:
            self.f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
            self.f.flush()


def confirm(args, what, log):
    if not args.write:
        log("\nDRY RUN: nothing was sent. Add --write to do it.")
        return False
    if args.yes:
        return True
    log("\n%s" % what)
    log("Before going on: unplug the cable, switch the keyboard OFF, wait 10 s, switch it ON,")
    log("plug the cable (wired mode). The boot animation must have played (if yours is broken:")
    log("just keep the keyboard off for those 10 s).")
    ans = input('Type  WRITE  to continue: ').strip()
    if ans != "WRITE":
        log("Cancelled.")
        return False
    return True


def progress_bar(done, total, elapsed):
    width = 30
    fill = int(width * done / total)
    eta = elapsed / done * (total - done) if done else 0
    sys.stdout.write("\r  [%s%s] %d/%d pages  %ds left " % ("#" * fill, "." * (width - fill),
                                                             done, total, eta))
    sys.stdout.flush()
    if done == total:
        sys.stdout.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="GK600 TKL screen resource restore (experimental)")
    ap.add_argument("action", choices=["list", "check", "probe", "unprobe", "restore"])
    ap.add_argument("--image", help="full 16 MiB public dump or the 0x1A0000-byte menus image")
    ap.add_argument("--write", action="store_true", help="really send (default: dry run)")
    ap.add_argument("--with-boot", action="store_true",
                    help="restore: also rewrite the boot animation area (960 pages, full dump needed)")
    ap.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    ap.add_argument("--ack-timeout", type=float, default=2.0)
    ap.add_argument("--log", default="gk600_restore.log")
    args = ap.parse_args(argv)
    log = Logger(args.log)
    log("gk600_restore %s - %s" % (__version__, args.action))

    try:
        if args.action == "list":
            for (pid, serial), entries in enumerate_keyboards().items():
                log("%04X:%04X %s" % (VID, pid, KNOWN_PIDS[pid]))
                for e in sorted(entries, key=lambda e: (e["interface_number"], e["usage_page"])):
                    log("   if %s  usage page %04X  version %04X  %s"
                        % (e["interface_number"], e["usage_page"], e["release_number"],
                           e.get("product_string")))
            return 0

        if args.action == "probe":
            src, ref = find_reference(args.image, MENUS_END)
            payload, what = probe_image(ref), "PROBE: home-screen icons and background, [0, 0x11000)"
        elif args.action == "unprobe":
            src, ref = find_reference(args.image, MENUS_END)
            payload, what = unprobe_image(ref), "UNPROBE: original icons and background, [0, 0x11000)"
        elif args.action == "restore":
            src, payload = find_reference(args.image, BOOT_END if args.with_boot else MENUS_END)
            what = "RESTORE: %s -> [0, 0x%X) (%d pages)" % (os.path.basename(src), len(payload),
                                                             len(payload) // PAGE)
        else:
            payload, what = None, None

        info = select_keyboard(log)
        if payload is not None:
            log("Payload  : %d pages, SHA-256 %s" % (len(payload) // PAGE,
                                                      hashlib.sha256(payload).hexdigest()))
            if not confirm(args, what, log):
                return 0
        t = HidTransport(info)
        try:
            if payload is None:
                handshake(t, log=log)
                log("Handshake OK: the keyboard answers and is idle. Nothing was written.")
                return 0
            raw_write(t, payload, args.ack_timeout, log=log, progress=progress_bar)
        finally:
            t.close()
        log("\nDone. The keyboard redraws its status screen at the end of the transfer.")
        if args.action == "probe":
            log("Expected on the home screen (dragon + laptop): the battery icon and the whole")
            log("bottom bar (WIN/MAC, connection, lock indicators) turn into magenta/yellow stripes.")
            log("Press Caps Lock or Num Lock to force a redraw. The dragon may hide the background.")
            log("Undo with:  python gk600_restore.py unprobe --write")
        elif args.action == "restore":
            log("Check every menu (knob / Fn keys), then power-cycle and check again.")
        return 0
    except RestoreError as e:
        log("\nERROR: %s" % e)
        return 2
    except KeyboardInterrupt:
        log("\nINTERRUPTED. If pages were being sent: unplug the cable, switch the keyboard OFF and ON,"
            " then run the same command again (it rewrites everything from the start).")
        return 3


if __name__ == "__main__":
    sys.exit(main())

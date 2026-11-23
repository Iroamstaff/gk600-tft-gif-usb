#!/usr/bin/env python3
"""
test_panel.py - the panel against the real Frieren V1.17 firmware code (emulated), through its
real web server: GIF upload (04 72), lighting (04 13), home picture, boot animation and repair
(04 38, with the power-cycle step), plus the server's protections.

Usage (from this folder; unicorn, Pillow needed):
  python -I test_panel.py <frieren_v117.bin> "<Forge gk600 tkl wireless.bin>" <anim.gif> <picture.png>
"""

import hashlib
import http.client
import json
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.normpath(os.path.join(HERE, ".."))
RESTO = os.path.normpath(os.path.join(PANEL, "..", "restauration"))
for p in (HERE, PANEL, RESTO, os.path.join(RESTO, "tests")):
    sys.path.insert(0, p)

import gk600_restore as g  # noqa: E402
import gk600_fw_emu as E  # noqa: E402
import gk600_gif as gif  # noqa: E402
import gk600_lighting as light  # noqa: E402
import gk600_home_picture as hp  # noqa: E402
import gk600_boot_animation as ba  # noqa: E402
import gk600_panel as P  # noqa: E402

fw_path, dump_path, anim_path, pic_path = sys.argv[1:5]
fw = open(fw_path, "rb").read()
ref = open(dump_path, "rb").read()
assert hashlib.sha256(ref).hexdigest() == g.DUMP_SHA256, "not the reference dump"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  [%s]" % detail) if detail and not ok else ""))


import emu_backend  # noqa: E402
emu_backend.fw, emu_backend.ref = fw, ref
new_panel = emu_backend.new_panel


class Client:
    def __init__(self, server, host=None, token=None, origin=None):
        self.port = server.port
        self.host = host or "127.0.0.1:%d" % server.port
        self.token = server.token if token is None else token
        self.origin = origin

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=600)
        h = {"Host": self.host, "X-Token": self.token}
        if self.origin:
            h["Origin"] = self.origin
        h.update(headers or {})
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        if r.getheader("Content-Type", "").startswith("application/json"):
            return r.status, json.loads(data)
        return r.status, data

    def post(self, path, obj):
        return self.req("POST", path, json.dumps(obj).encode(), {"Content-Type": "application/json"})

    def upload(self, kind, path, fill=False):
        return self.req("POST", "/api/file?kind=%s&fill=%d" % (kind, int(fill)), open(path, "rb").read(),
                        {"X-File-Name": os.path.basename(path), "Content-Type": "application/octet-stream"})

    def wait_job(self, until=("done", "error", "cancelled"), timeout=900):
        t0 = time.time()
        while time.time() - t0 < timeout:
            _, st = self.req("GET", "/api/status")
            j = st["job"]
            if j and j["phase"] in until:
                return j
            time.sleep(0.2)
        raise TimeoutError("job did not finish")


def flash(emu):
    return bytes(emu.flash.mem)


t_start = time.time()

# ---------------------------------------------------------------- P1 protocol units
p = light.payload(1, (0x12, 0x34, 0x56), 4, 2, 1, False)
check("P1 lighting payload: effect, colour, brightness, speed, direction, AA 55",
      p[:16] == bytes([1, 0x12, 0x34, 0x56, 0, 0, 0, 0, 0, 4, 2, 1, 0, 0, 0xAA, 0x55]) and not any(p[16:]))
check("P1 lighting 'off' sends no colour", light.payload(0, (9, 9, 9), 5, 3, 0, True)[:14] == bytes(14))
check("P1 20 effects in MSI's order", len(light.EFFECTS) == 20 and light.EFFECTS[1][1] == "Static"
      and light.EFFECTS[19][1] == "Shuttle")
frames = ba.load_animation(anim_path)
stream = gif.build_stream(gif.plan(frames))
check("P1 GIF header: frame count, then times in 2 ms steps",
      stream[0] == len(frames) and all(stream[1 + i] == gif.ticks(ms) for i, (_, ms) in enumerate(frames)))
check("P1 GIF data: frames right after the 256-byte header, padded to a page",
      stream[256:256 + gif.FRAME_SIZE] == frames[0][0] and len(stream) % 4096 == 0)
many = [(frames[0][0], 40)] * 300
check("P1 300 frames are cut to 255, total time kept as far as 510 ms frames allow",
      len(gif.plan(many)) == 255 and abs(sum(ms for _, ms in gif.plan(many)) - 12000) < 1)
bad = []
for s in (bytes(4096), bytearray(stream[:4096]), stream[:-4096]):
    try:
        gif.check_stream(bytes(s))
    except g.RestoreError:
        bad.append(True)
z = bytearray(stream)
z[1] = 0
try:
    gif.check_stream(bytes(z))
except g.RestoreError:
    bad.append(True)
check("P1 malformed GIF data refused before anything is sent (0 frames, short data, time 0)", len(bad) == 4)
try:
    gif.build_stream([(frames[0][0], 40)] * 256)
    over = False
except g.RestoreError:
    over = True
check("P1 a 256-frame GIF cannot be built", over)

# ---------------------------------------------------------------- P2 server protections
emu, backend, panel, server = new_panel()
c = Client(server)
st, page = c.req("GET", "/")
check("P2 page served to our own Host, token injected", st == 200 and server.token.encode() in page
      and b"__GK600_TOKEN__" not in page)
st, _ = Client(server, host="evil.example:%d" % server.port).req("GET", "/")
check("P2 other Host refused (DNS rebinding)", st == 403)
st, _ = Client(server, token="").req("GET", "/api/status")
check("P2 API without the token refused", st == 403)
st, _ = Client(server, origin="http://evil.example").req("POST", "/api/light", b"{}")
check("P2 request from another website refused (Origin)", st == 403)
st, s0 = c.req("GET", "/api/status")
check("P2 status: keyboard, firmware V1.20 validated, full dump",
      st == 200 and s0["keyboard"]["firmware"] == "V1.20" and s0["keyboard"]["validated"] and s0["reference"] == "full")

# ---------------------------------------------------------------- P3 lighting through the panel
st, r = c.post("/api/light", {"effect": 1, "color": "#123456", "multicolour": False, "brightness": 4,
                              "speed": 2, "direction": 1})
ram = bytes(emu.rb(0x20002980, 16))
check("P3 lighting applied, acknowledged at each step, colour in the firmware's settings",
      st == 200 and r["ok"] and bytes([0x12, 0x34, 0x56]) in ram, ram.hex(" "))
check("P3 settings stored by the keyboard in its MCU flash, screen flash untouched",
      any("INTERNAL FLASH" in c[1] for c in emu.calls) and flash(emu) == ref)
st, r = c.post("/api/light", {"effect": 99, "color": "#123456", "brightness": 4, "speed": 2, "direction": 1})
check("P3 bad lighting settings refused", st == 400)

# ---------------------------------------------------------------- P4 GIF through the panel
st, f = c.upload("gif", anim_path)
st2, prev = c.req("GET", f["preview"])
check("P4 GIF file accepted, preview served", st == 200 and f["info"]["frames"] == len(frames)
      and st2 == 200 and prev[:6] in (b"GIF89a", b"GIF87a"))
st, j = c.post("/api/job", {"kind": "gif", "id": f["id"]})
j = c.wait_job()
mem = flash(emu)
check("P4 GIF job done without asking for a restart", j["phase"] == "done" and j["done"] == j["total"])
check("P4 GIF slot holds exactly the stream, the rest of the chip is untouched",
      mem[gif.SLOT_ADDR:gif.SLOT_ADDR + len(stream)] == stream and mem[:gif.SLOT_ADDR] == ref[:gif.SLOT_ADDR]
      and mem[gif.SLOT_ADDR + len(stream):] == ref[gif.SLOT_ADDR + len(stream):])
check("P4 firmware reloaded the user animation (0xFE20)", any(c[1] == "user animation reload FE20" for c in emu.calls))

# ---------------------------------------------------------------- P5 home picture: power cycle, write
st, f = c.upload("home", pic_path)
picture = hp.load_picture(pic_path)
st, j = c.post("/api/job", {"kind": "home", "id": f["id"]})
j = c.wait_job(until=("cycle_off", "error"), timeout=30)
check("P5 home picture waits for the keyboard to be unplugged", j["phase"] == "cycle_off")
time.sleep(0.5)
check("P5 nothing written while waiting", flash(emu)[:hp.END] == ref[:hp.END])
backend.present = False
j = c.wait_job(until=("cycle_on", "error"), timeout=30)
check("P5 unplug seen, waiting for the keyboard to come back", j["phase"] == "cycle_on")
backend.present = True
j = c.wait_job()
mem = flash(emu)
check("P5 home picture written after the restart", j["phase"] == "done" and j["done"] == hp.END // 4096)
check("P5 flash = dump with the picture at 0x17A1CE; GIF slot kept",
      mem[:hp.END] == hp.build_payload(ref, picture) and mem[gif.SLOT_ADDR:gif.SLOT_ADDR + len(stream)] == stream)
_, s1 = c.req("GET", "/api/status")
check("P5 panel remembers the home picture", s1["home"]["active"] and s1["home"]["name"] == os.path.basename(pic_path))

# ---------------------------------------------------------------- P6 boot animation keeps the home picture
st, f = c.upload("boot", anim_path, fill=True)
slots, _ = ba.plan(ba.load_animation(anim_path, True))
area = ba.build_boot_area(slots)
st, j = c.post("/api/job", {"kind": "boot", "id": f["id"], "keep_home": True})
c.wait_job(until=("cycle_off",), timeout=30)
backend.present = False
c.wait_job(until=("cycle_on",), timeout=30)
backend.present = True
j = c.wait_job()
mem = flash(emu)
expected = ba.build_payload(ref, area, picture)
check("P6 boot animation written, home picture kept", j["phase"] == "done"
      and mem[:len(expected)] == expected and j["total"] == len(expected) // 4096)
check("P6 GIF slot still intact", mem[gif.SLOT_ADDR:gif.SLOT_ADDR + len(stream)] == stream)

# ---------------------------------------------------------------- P7 cancel, conflicts, firmware not validated
st, j = c.post("/api/job", {"kind": "repair"})
c.wait_job(until=("cycle_off",), timeout=30)
st, r = c.post("/api/job/cancel", {})
j = c.wait_job()
check("P7 cancel while waiting for the restart: nothing written", j["phase"] == "cancelled" and flash(emu) == mem)
backend.conf = ["DeviceDriver.exe"]
st, r = c.post("/api/light", {"effect": 1, "color": "#ffffff", "brightness": 5, "speed": 3, "direction": 0})
check("P7 MSI's software open: refused with the 'conflict' message", st == 400 and r["error"] == "conflict")
backend.conf = []
backend.version = 0x0117
st, j = c.post("/api/job", {"kind": "home", "id": c.upload("home", pic_path)[1]["id"]})
j = c.wait_job()
check("P7 unvalidated firmware: home picture refused before any restart",
      j["phase"] == "error" and j["error"] == "not_validated" and flash(emu) == mem)
backend.version = 0x0120

# ---------------------------------------------------------------- P8 repair puts everything back
st, j = c.post("/api/job", {"kind": "repair"})
c.wait_job(until=("cycle_off",), timeout=30)
backend.present = False
c.wait_job(until=("cycle_on",), timeout=30)
backend.present = True
j = c.wait_job()
mem = flash(emu)
check("P8 repair: menus, dragon and MSI animation back (= dump up to 0x3C0000)",
      j["phase"] == "done" and mem[:g.BOOT_END] == ref[:g.BOOT_END] and j["total"] == 960)
check("P8 repair keeps the GIF slot", mem[gif.SLOT_ADDR:gif.SLOT_ADDR + len(stream)] == stream)
_, s2 = c.req("GET", "/api/status")
check("P8 panel forgets the home picture after a repair", not s2["home"]["active"])

server.shutdown()
server.server_close()
panel.close()
ok = sum(1 for _, k, _ in results if k)
print("\n%d/%d passed in %.0f s" % (ok, len(results), time.time() - t_start))
sys.exit(0 if ok == len(results) else 1)

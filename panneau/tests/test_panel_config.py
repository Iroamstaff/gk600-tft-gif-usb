#!/usr/bin/env python3
"""
test_panel_config.py - the panel's keys, colours, macros, settings and profiles, through its
real web server, against the real Frieren V1.17 firmware code (emulated, MCU flash modelled).

Usage (from this folder; unicorn needed):
  python -I test_panel_config.py <frieren_v117.bin> "<Forge gk600 tkl wireless.bin>"
"""

import hashlib
import http.client
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.normpath(os.path.join(HERE, ".."))
RESTO = os.path.normpath(os.path.join(PANEL, "..", "restauration"))
for p in (HERE, PANEL, RESTO, os.path.join(RESTO, "tests")):
    sys.path.insert(0, p)

import gk600_restore as g  # noqa: E402
import gk600_config as cfg  # noqa: E402
import emu_backend  # noqa: E402

fw = open(sys.argv[1], "rb").read()
ref = open(sys.argv[2], "rb").read()
assert hashlib.sha256(ref).hexdigest() == g.DUMP_SHA256, "not the reference dump"
emu_backend.fw, emu_backend.ref = fw, ref

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  [%s]" % detail) if detail and not ok else ""))


class Client:
    def __init__(self, server):
        self.port, self.token = server.port, server.token

    def req(self, method, path, obj=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=600)
        h = {"Host": "127.0.0.1:%d" % self.port, "X-Token": self.token}
        body = None
        if obj is not None:
            body = json.dumps(obj).encode()
            h["Content-Type"] = "application/json"
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, json.loads(data)

    def post(self, path, obj):
        return self.req("POST", path, obj)


emu, backend, panel, server = emu_backend.new_panel(flash_model=True)
c = Client(server)

st, cat = c.req("GET", "/api/catalog")
check("K1 catalog: ISO 84 keys, ANSI 83, functions listed", st == 200 and len(cat["layouts"]["iso"]) == 84
      and len(cat["layouts"]["ansi"]) == 83 and cat["media"] and cat["shortcuts"] and cat["macro_capacity"] == 3008)

st, r = c.post("/api/config/read", {"parts": ["keys", "fnkeys", "colours", "lighting", "settings", "macros"]})
check("K2 read everything the keyboard holds", st == 200 and r["ok"] and r["unsupported"] == []
      and r["parsed"]["keys"] == {} and r["parsed"]["settings"]["sleep"] == 2, str(r)[:300])
profs = c.req("GET", "/api/profiles")[1]["profiles"]
check("K2 the first read made a backup profile", len(profs) == 1 and profs[0]["backup"]
      and set(profs[0]["parts"]) >= {"keys", "fnkeys", "colours", "settings", "macros"}, str(profs))

keys = {"55": {"type": "key", "mods": 0, "code": 0xE0}, "13": {"type": "media", "code": 0xE2},
        "117": {"type": "disabled"}, "41": {"type": "macro", "index": 0, "mode": 1, "count": 3}}
st, r = c.post("/api/config/write", {"part": "keys", "data": {"actions": keys}})
check("K3 main layer written", st == 200 and r["ok"], str(r))
check("K3 flash: Caps Lock = Ctrl, F12 = mute, Home off (both numbers)",
      emu.iflash(0x9400 + 55 * 4, 4).hex() == "02010000" and emu.iflash(0x9400 + 13 * 4, 4).hex() == "03e20000"
      and emu.iflash(0x9400 + 117 * 4, 4) == emu.iflash(0x9400 + 113 * 4, 4) == b"\x05\x03\x00\x00")
st, r = c.post("/api/config/read", {"parts": ["keys"]})
check("K3 read back through the server", r["parsed"]["keys"] == keys, str(r["parsed"]["keys"]))

st, r = c.post("/api/config/write", {"part": "keys", "data": {"actions": {"96": {"type": "key", "code": 4}}}})
check("K4 remapping Fn refused, nothing written", st == 400 and r["error"] == "bad_request"
      and emu.iflash(0x9400 + 55 * 4, 4).hex() == "02010000", str(r))
st, r = c.post("/api/config/write", {"part": "keys", "data": {"actions": {"30": {"type": "key", "code": 0x99}}}})
check("K4 unknown key code refused", st == 400 and r["error"] == "bad_request", str(r))

cols = {str(i): "#%02x%02x%02x" % (i * 2, 255 - i, 40) for i in (1, 20, 55, 67, 85, 111, 117, 121)}
st, r = c.post("/api/config/write", {"part": "colours", "data": {"colours": cols, "brightness": 3}})
check("K5 per-key colours written with the custom mode", st == 200 and emu.iflash(0x9800, 1) == b"\x80"
      and emu.iflash(0x9800 + 9, 1) == b"\x03" and emu.iflash(0x9C00 + 20 * 4, 4) == bytes([20, 40, 235, 40]), str(r))
_, stt = c.req("GET", "/api/status")
check("K5 the panel remembers the custom mode", stt["lighting"] == {"effect": "custom", "brightness": 3}, str(stt["lighting"]))
st, r = c.post("/api/config/read", {"parts": ["colours", "lighting"]})
check("K5 colours read back", r["parsed"]["colours"] == cols and r["parsed"]["lighting"]["effect"] == "custom")
check("K5 ISO * µ key and Home written under both numbers",
      emu.iflash(0x9C00 + 110 * 4, 4) == bytes([110, 134, 188, 40]) and emu.iflash(0x9C00 + 113 * 4, 4) == bytes([113, 234, 138, 40]))

st, r = c.post("/api/light", {"effect": "custom", "brightness": 5})
check("K6 lighting tab can switch back to the per-key colours", st == 200 and emu.iflash(0x9800, 16) == cfg.custom_mode(5)[:16])
st, r = c.post("/api/light", {"effect": 11, "color": "#00ff00", "multicolour": False, "brightness": 4, "speed": 2,
                              "direction": 1})
check("K6 an effect replaces the custom mode, colours kept", st == 200 and emu.iflash(0x9800, 1) == b"\x0b"
      and emu.iflash(0x9C00 + 20 * 4, 4) == bytes([20, 40, 235, 40]))

macros = [{"name": "hello", "steps": [{"t": "down", "code": 0x0B}, {"t": "up", "code": 0x0B}, {"t": "delay", "ms": 50},
                                      {"t": "down", "code": 0x08}, {"t": "up", "code": 0x08}]},
          None, {"name": "click", "steps": [{"t": "mdown", "button": "left"}, {"t": "mup", "button": "left"}]}]
st, r = c.post("/api/config/bytes", {"macros": macros})
check("K7 macro size computed by the server (a delay after each step, as sent)", st == 200 and r["bytes"]["used"] == 400 + 8 + 4 * 8 + 8 + 4 * 4
      and r["bytes"]["capacity"] == 3008, str(r))
st, r = c.post("/api/config/write", {"part": "macros", "data": {"macros": macros}})
check("K7 macros written", st == 200 and r["ok"], str(r))
st, r = c.post("/api/config/read", {"parts": ["macros"]})
pm = r["parsed"]["macros"]
check("K7 macros read back (slot 2 empty, 3 macros)", len(pm) == 3 and pm[1] is None
      and [s["t"] for s in pm[2]["steps"]] == ["mdown", "delay", "mup", "delay"], str(pm))
huge = [{"name": "x", "steps": [{"t": "down", "code": 4}, {"t": "up", "code": 4}] * 400}]
st, r = c.post("/api/config/write", {"part": "macros", "data": {"macros": huge}})
check("K7 macros over the limit refused, nothing sent", st == 400 and r["error"] == "too_long"
      and cfg.parse_macros(emu.iflash(0xA000, 1024))[0]["steps"][0] == {"t": "down", "code": 0x0B}, str(r))

st, r = c.post("/api/config/write", {"part": "settings", "data": {"no_win": True, "no_alt_tab": True, "fn_toggle": False,
                                                                  "sleep": 0, "debounce": 1}})
check("K8 settings written, unknown bytes kept from the keyboard", st == 200
      and emu.iflash(0x9000, 9).hex() == "000001000100000001", emu.iflash(0x9000, 9).hex())
st, r = c.post("/api/clock", {})
check("K8 no clock route: the TKL screen never draws the clock", st == 404, str((st, r)))

prof = {"format": "gk600-profile", "version": 1, "name": "Jeux",
        "keys": {"57": {"type": "key", "mods": 0, "code": 0x52}}, "fnkeys": {"2": {"type": "media", "code": 0xCD}},
        "colours": {"colours": {"57": "#ff0000"}, "brightness": 2},
        "lighting": {"effect": "custom", "brightness": 2},
        "macros": [{"name": "a", "steps": [{"t": "down", "code": 4}, {"t": "up", "code": 4}]}],
        "settings": {"no_win": True, "sleep": 1, "debounce": 3}}
st, r = c.post("/api/profiles/save", {"profile": prof})
pid = r.get("id")
check("K9 profile saved", st == 200 and pid)
st, r = c.post("/api/profiles/apply", {"id": pid})
check("K9 profile applied in MSI's order", st == 200 and r["parts"] == ["macros", "keys", "fnkeys", "colours", "lighting",
                                                                       "settings"], str(r))
check("K9 keyboard holds the profile", emu.iflash(0x9400 + 57 * 4, 4).hex() == "02005200"
      and emu.iflash(0x9400 + 55 * 4, 4) == bytes(4) and emu.iflash(0xAC00 + 2 * 4, 4).hex() == "03cd0000"
      and emu.iflash(0x9C00 + 57 * 4, 4) == bytes([57, 255, 0, 0]) and emu.iflash(0x9800, 1) == b"\x80"
      and emu.iflash(0x9000 + 6, 1) == b"\x01")
bad = dict(prof, keys={"57": {"type": "key", "code": 0x99}})
n_ops = len(emu.iflash_ops)
st, r = c.post("/api/profiles/apply", {"profile": bad})
check("K9 a bad profile is refused before anything is written", st == 400 and len(emu.iflash_ops) == n_ops, str(r))
st, r = c.post("/api/profiles/get", {"id": "../state"})
check("K9 profile ids cannot leave the folder", st == 400, str(r))
backup = [p for p in c.req("GET", "/api/profiles")[1]["profiles"] if p["backup"]][0]
st, r = c.post("/api/profiles/apply", {"id": backup["id"]})
check("K10 the session backup puts the keyboard back", st == 200 and emu.iflash(0x9400, 576)[:574] == bytes(574)
      and emu.iflash(0x9000, 9).hex() == "000000000000020002", "%s %s" % (r, emu.iflash(0x9000, 9).hex()))
st, r = c.post("/api/profiles/delete", {"id": pid})
check("K10 profile deleted", st == 200 and pid not in [p["id"] for p in c.req("GET", "/api/profiles")[1]["profiles"]])
check("K11 screen flash (SPI) never touched", not emu.flash.ops)
check("K11 no program over unerased bytes, nothing refused", not emu.overprogram and not emu.refused)

backend.conf = ["DeviceDriver.exe"]
st, r = c.post("/api/config/read", {"parts": ["keys"]})
check("K12 MSI software open: refused", st == 400 and r["error"] == "conflict", str(r))
backend.conf = []
server.shutdown()
panel.close()

n_ok = sum(1 for _, ok, _ in results if ok)
print("\n%d/%d checks passed" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)

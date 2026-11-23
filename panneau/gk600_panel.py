#!/usr/bin/env python3
"""
gk600_panel.py - EXPERIMENTAL - one window for the screen and the lighting of the MSI Forge GK600
TKL Wireless: your GIF, the RGB effects, the home picture, the boot animation and the repair, over
USB, without MSI's software.

It runs a small web server on this PC only (127.0.0.1) and opens its page in Edge (or the default
browser). Every request must come from that page: the server checks the Host and Origin headers
and a random token given to the page at start-up, so no website can drive the keyboard.

What it uses:
  GIF            gk600_gif.py       04 72, the GIF slot at 0x3C0000, like MSI's software
  RGB effects    gk600_lighting.py  04 13, one effect for the whole keyboard
  home picture   ../restauration/gk600_home_picture.py    04 38, [0, 0x180000)
  boot animation ../restauration/gk600_boot_animation.py  04 38, [0, end of the animation)
  repair         ../restauration/gk600_restore.py         04 38, [0, 0x3C0000) from the dump
The three 04 38 writes need a freshly restarted keyboard and a validated firmware (V1.04, V1.20),
exactly like the .bat files of ../restauration.

Start it with GK600-Panel.bat (it fetches a portable Python, hidapi, Pillow and the reference dump),
or by hand:  python gk600_panel.py   (Python 3.8+, pip install hidapi pillow, the dump in
../restauration).
"""

import http.server
import json
import os
import secrets
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
RESTO = os.path.normpath(os.path.join(HERE, "..", "restauration"))
sys.path.insert(0, RESTO)
sys.path.insert(0, HERE)
import gk600_restore as g  # noqa: E402
import gk600_home_picture as hp  # noqa: E402
import gk600_boot_animation as ba  # noqa: E402
import gk600_gif as gif  # noqa: E402
import gk600_lighting as light  # noqa: E402

__version__ = "0.1-experimental"

PORT = 47600
VALIDATED = {0x0104: "V1.04", 0x0120: "V1.20"}     # 04 38 writes confirmed on these firmwares
PAGES_PER_S = 7.0                                  # measured on a real keyboard
MAX_UPLOAD = 64 << 20
IDLE_EXIT_S = 300                                  # no page left open: the server stops
WEB = os.path.join(HERE, "web", "index.html")
STATE_DIR = os.path.join(HERE, "state")


class Cancelled(Exception):
    pass


def fw_name(version):
    return "V%X.%02X" % (version >> 8, version & 0xFF)


def error_key(e):
    m = str(e)
    if m.startswith("timeout"):
        return "timeout"
    if m.startswith("choose the file again"):
        return "file_again"
    if m.startswith("invalid") or m.startswith("unknown"):
        return "bad_request"
    if "no GK600" in m:
        return "no_keyboard"
    if m.startswith("close "):
        return "conflict"
    if "not idle" in m or "busy" in m:
        return "not_idle"
    if "reference image" in m or "dump" in m:
        return "no_reference"
    if "Pillow" in m or "not a picture" in m or "no frame" in m:
        return "bad_file"
    if "page " in m or "ACK" in m or "04 38" in m or "04 72" in m or "04 02" in m:
        return "write_failed"
    return "failed"


# ---------------------------------------------------------------- device access
def running_conflicts():
    """Windows: programs that also talk to the keyboard (MSI's software, OpenRGB, SignalRGB).
    Reads tasklist as bytes, so its code page (accents, separators) can never break the check."""
    if os.name != "nt":
        return []
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except Exception:
        return []
    text = out.decode("latin-1").lower()
    return [p for p in g.CONFLICTING if '"%s"' % p.lower() in text]


class Backend:
    """The real keyboard, through hidapi (gk600_restore.py)."""

    def __init__(self):
        self._conflicts = (0.0, [])

    def keyboards(self):
        out = []
        for (pid, _), entries in g.enumerate_keyboards().items():
            ctrl = [e for e in entries if e["usage_page"] == g.USAGE_PAGE_CTRL] or entries
            out.append({"pid": pid, "name": g.KNOWN_PIDS[pid], "product": ctrl[0].get("product_string"),
                        "version": ctrl[0].get("release_number") or 0})
        return out

    def conflicts(self):
        now = time.monotonic()
        if now - self._conflicts[0] > 5:
            self._conflicts = (now, running_conflicts())
        return self._conflicts[1]

    def select(self, log):
        busy = running_conflicts()
        if busy:
            raise g.RestoreError("close %s first (also from the system tray): it talks to the keyboard "
                                 "and would mix its commands with ours" % ", ".join(busy))
        return g.select_keyboard(log)

    def open(self, info):
        return g.HidTransport(info)


# ---------------------------------------------------------------- state kept between sessions
class State:
    def __init__(self, folder):
        self.folder = folder
        self.path = os.path.join(folder, "state.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}

    def save(self):
        os.makedirs(self.folder, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.path)

    def file(self, name):
        return os.path.join(self.folder, name)

    def home_picture(self):
        """The home picture last written by the panel, if it is still on the keyboard."""
        h = self.data.get("home")
        if not h or not h.get("active"):
            return None
        try:
            data = open(self.file("home_picture.rgb565"), "rb").read()
        except OSError:
            return None
        return data if len(data) == hp.PIC_SIZE else None


# ---------------------------------------------------------------- jobs
class Job:
    def __init__(self, kind, item, keep_home=False):
        self.id = secrets.token_hex(4)
        self.kind = kind
        self.item = item
        self.keep_home = keep_home
        self.phase = "starting"
        self.done = 0
        self.total = 0
        self.t0 = None
        self.error = None
        self.detail = ""
        self.cancel = threading.Event()

    @property
    def active(self):
        return self.phase not in ("done", "error", "cancelled")

    def snapshot(self):
        elapsed = time.time() - self.t0 if self.t0 else 0
        eta = elapsed / self.done * (self.total - self.done) if self.done else None
        return {"id": self.id, "kind": self.kind, "phase": self.phase, "done": self.done,
                "total": self.total, "elapsed": round(elapsed, 1),
                "eta": round(eta) if eta is not None else None, "error": self.error,
                "detail": self.detail, "name": self.item.get("name") if self.item else None}


class Panel:
    def __init__(self, backend=None, state_dir=STATE_DIR, reference=None):
        self.backend = backend or Backend()
        self.state = State(state_dir)
        self.work = tempfile.mkdtemp(prefix="gk600_panel_")
        self.items = {}
        self.job = None
        self.lock = threading.Lock()          # one keyboard operation at a time
        self.lines = []
        self.log_file = os.path.join(HERE, "gk600_panel.log")
        self._reference = reference           # full 16 MiB dump (or None: loaded on demand)
        self._reference_error = None

    # ------------------------------------------------------------ log
    def log(self, msg):
        line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
        self.lines = (self.lines + [line])[-300:]
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write("%s %s\n" % (time.strftime("%Y-%m-%d"), line))
        except OSError:
            pass

    # ------------------------------------------------------------ reference dump
    def reference(self, end):
        if self._reference is None and self._reference_error is None:
            try:
                self._reference = g.find_reference(None, g.BOOT_END)[1]
            except g.RestoreError:
                try:
                    self._reference = g.find_reference(None, g.MENUS_END)[1]
                except g.RestoreError as e:
                    self._reference_error = str(e)
        if self._reference is None:
            raise g.RestoreError(self._reference_error or "reference image not found")
        if len(self._reference) < end:
            raise g.RestoreError("the repair needs the full 16 MiB dump (reference image too short)")
        return self._reference[:end]

    # ------------------------------------------------------------ status
    def status(self):
        kb, err = None, None
        try:
            found = self.backend.keyboards()
            if len(found) == 1:
                v = found[0]["version"]
                kb = {"name": found[0]["name"], "product": found[0]["product"], "firmware": fw_name(v),
                      "validated": v in VALIDATED}
            elif len(found) > 1:
                err = "several"
        except g.RestoreError as e:
            err = str(e)
        try:
            self.reference(g.MENUS_END)
            ref = "full" if len(self._reference) >= g.BOOT_END else "menus"
        except g.RestoreError:
            ref = None
        home = self.state.data.get("home") or {}
        return {"app": "gk600-panel", "version": __version__, "keyboard": kb, "keyboard_error": err,
                "conflicts": self.backend.conflicts(), "reference": ref,
                "job": self.job.snapshot() if self.job else None,
                "home": {"name": home.get("name"), "active": bool(self.state.home_picture())},
                "lighting": self.state.data.get("lighting") or light.DEFAULT_JSON,
                "effects": [{"key": k, "en": en, "fr": fr} for k, en, fr in light.EFFECTS]}

    # ------------------------------------------------------------ files
    def add_file(self, kind, name, data, fill=False):
        if kind not in ("gif", "home", "boot"):
            raise g.RestoreError("unknown file kind")
        ext = os.path.splitext(name)[1].lower()[:8] or ".bin"
        item_id = secrets.token_hex(6)
        path = os.path.join(self.work, item_id + ext)
        with open(path, "wb") as f:
            f.write(data)
        item = {"id": item_id, "kind": kind, "name": os.path.basename(name)[:120], "path": path}
        if kind == "gif":
            frames = ba.load_animation(path, fill)
            used = gif.plan(frames)
            stream = gif.build_stream(used)
            loop_ms = sum(ms for _, ms in gif.playback(stream))
            pages = len(stream) // g.PAGE
            item.update(stream=stream, preview=path + ".preview.gif", ctype="image/gif",
                        info={"frames_in": len(frames), "frames": len(used), "loop_s": round(loop_ms / 1000, 1),
                              "pages": pages, "minutes": round(pages / PAGES_PER_S / 60, 1)})
            gif.save_preview(stream, item["preview"])
        elif kind == "home":
            picture = hp.load_picture(path)
            ref = self.reference(g.MENUS_END)
            item.update(picture=picture, preview=path + ".preview.png", ctype="image/png",
                        info={"pages": hp.END // g.PAGE,
                              "minutes": round(hp.END // g.PAGE / PAGES_PER_S / 60, 1)})
            hp.save_preview(ref, picture, item["preview"], scale=3)
        else:
            frames = ba.load_animation(path, fill)
            slots, used = ba.plan(frames)
            ref = self.reference(g.MENUS_END)
            area = ba.build_boot_area(slots)
            pages = len(ba.build_payload(ref, area)) // g.PAGE
            total = sum(ms for _, ms in ba.playback(slots))
            item.update(slots=slots, preview=path + ".preview.gif", ctype="image/gif",
                        info={"frames_in": len(frames), "frames": len(used), "slots": len(slots),
                              "seconds": round(total / 1000, 1),
                              "pages": pages, "minutes": round(pages / PAGES_PER_S / 60, 1)})
            ba.save_preview(slots, item["preview"], ref, self.state.home_picture())
        self.items = {k: v for k, v in self.items.items() if v["kind"] != kind}   # one file per kind
        self.items[item_id] = item
        self.log("file %s: %s %s" % (kind, item["name"], item["info"]))
        return {"id": item_id, "kind": kind, "name": item["name"], "info": item["info"],
                "preview": "/api/preview/" + item_id}

    def preview(self, item_id):
        item = self.items.get(item_id)
        if not item:
            return None, None
        with open(item["preview"], "rb") as f:
            return f.read(), item["ctype"]

    # ------------------------------------------------------------ lighting
    def apply_lighting(self, s):
        try:
            effect = int(s["effect"])
            color = s["color"].lstrip("#")
            rgb = tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
            brightness, speed, direction = int(s["brightness"]), int(s["speed"]), int(s["direction"])
            multicolour = bool(s.get("multicolour"))
        except (KeyError, ValueError, TypeError, AttributeError):
            raise g.RestoreError("invalid lighting settings")
        if self.job and self.job.active:
            raise g.RestoreError("busy: a write is in progress")
        with self.lock:
            info = self.backend.select(self.log)
            t = self.backend.open(info)
            try:
                light.set_lighting(t, effect, rgb, brightness, speed, direction, multicolour, log=self.log)
            finally:
                t.close()
        self.state.data["lighting"] = {"effect": effect, "color": "#%02x%02x%02x" % rgb,
                                       "multicolour": multicolour, "brightness": brightness,
                                       "speed": speed, "direction": direction}
        self.state.save()
        self.log("lighting: %s" % self.state.data["lighting"])

    # ------------------------------------------------------------ writes
    def start_job(self, kind, item_id=None, keep_home=False):
        if self.job and self.job.active:
            raise g.RestoreError("busy: a write is in progress")
        item = None
        if kind in ("gif", "home", "boot"):
            item = self.items.get(item_id or "")
            if not item or item["kind"] != kind:
                raise g.RestoreError("choose the file again")
        elif kind != "repair":
            raise g.RestoreError("unknown action")
        job = Job(kind, item, keep_home)
        self.job = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job.snapshot()

    def cancel_job(self):
        job = self.job
        if job and job.phase in ("starting", "cycle_off", "cycle_on", "check"):
            job.cancel.set()
            return True
        return False

    def _wait(self, job, seconds):
        if job.cancel.wait(seconds):
            raise Cancelled()

    def _present(self):
        try:
            return bool(self.backend.keyboards())
        except g.RestoreError:
            return False

    def _wait_power_cycle(self, job):
        deadline = time.monotonic() + 600
        job.phase = "cycle_off"
        while self._present():
            if time.monotonic() > deadline:
                raise g.RestoreError("timeout: the keyboard was not restarted")
            self._wait(job, 0.4)
        job.phase = "cycle_on"
        while not self._present():
            if time.monotonic() > deadline:
                raise g.RestoreError("timeout: the keyboard did not come back")
            self._wait(job, 0.4)
        self._wait(job, 2.0)

    def _check_idle(self, job):
        job.phase = "check"
        last = None
        for attempt in range(5):
            try:
                with self.lock:
                    info = self.backend.select(self.log)
                    t = self.backend.open(info)
                    try:
                        g.handshake(t, log=self.log)
                    finally:
                        t.close()
                return info
            except g.RestoreError as e:
                last = e
                self.log("check %d/5: %s" % (attempt + 1, e))
                self._wait(job, 3.0)
        raise last

    def _payload(self, job):
        if job.kind == "home":
            return hp.build_payload(self.reference(g.MENUS_END), job.item["picture"])
        if job.kind == "boot":
            home = self.state.home_picture() if job.keep_home else None
            area = ba.build_boot_area(job.item["slots"])
            return ba.build_payload(self.reference(g.MENUS_END), area, home)
        return self.reference(g.BOOT_END)                      # repair: menus + MSI animation

    def _progress(self, job, done, total, elapsed):
        job.done, job.total = done, total

    def _run(self, job):
        self.log("job %s started: %s" % (job.id, job.kind))
        try:
            if job.kind == "gif":
                stream = job.item["stream"]
                job.total = len(stream) // g.PAGE
                job.phase = "check"
                with self.lock:
                    info = self.backend.select(self.log)
                    t = self.backend.open(info)
                    try:
                        job.phase, job.t0 = "write", time.time()
                        gif.gif_write(t, stream, log=self.log,
                                      progress=lambda d, n, e: self._progress(job, d, n, e))
                    finally:
                        t.close()
                self.state.data["gif"] = {"name": job.item["name"], "time": time.strftime("%Y-%m-%d %H:%M")}
            else:
                payload = self._payload(job)
                job.total = len(payload) // g.PAGE
                info = self.backend.select(self.log)
                if info["version"] not in VALIDATED:
                    job.error = "not_validated"
                    raise g.RestoreError("firmware %s has not been validated for this write"
                                         % fw_name(info["version"]))
                self._wait_power_cycle(job)
                info = self._check_idle(job)
                with self.lock:
                    t = self.backend.open(info)
                    try:
                        job.phase, job.t0 = "write", time.time()
                        g.raw_write(t, payload, log=self.log,
                                    progress=lambda d, n, e: self._progress(job, d, n, e))
                    finally:
                        t.close()
            job.phase = "done"
            self.log("job %s done" % job.id)
            try:
                if job.kind != "gif":
                    self._after_write(job)
                self.state.save()
            except OSError as e:                                # the write itself succeeded
                self.log("could not save the panel state: %s" % e)
        except Cancelled:
            job.phase = "cancelled"
            self.log("job %s cancelled" % job.id)
        except g.RestoreError as e:
            job.error = job.error or error_key(e)
            job.detail = str(e)
            job.phase = "error"
            self.log("job %s error: %s" % (job.id, e))
        except Exception as e:                              # keep the server alive, show the cause
            job.error, job.detail, job.phase = "internal", "%s: %s" % (type(e).__name__, e), "error"
            self.log("job %s internal error:\n%s" % (job.id, traceback.format_exc()))

    def _after_write(self, job):
        stamp = time.strftime("%Y-%m-%d %H:%M")
        if job.kind == "home":
            os.makedirs(self.state.folder, exist_ok=True)
            with open(self.state.file("home_picture.rgb565"), "wb") as f:
                f.write(job.item["picture"])
            self.state.data["home"] = {"name": job.item["name"], "time": stamp, "active": True}
        elif job.kind == "boot":
            self.state.data["boot"] = {"name": job.item["name"], "time": stamp}
            if not job.keep_home and self.state.data.get("home"):
                self.state.data["home"]["active"] = False
        elif job.kind == "repair":
            self.state.data.pop("boot", None)
            if self.state.data.get("home"):
                self.state.data["home"]["active"] = False

    def close(self):
        shutil.rmtree(self.work, ignore_errors=True)


# ---------------------------------------------------------------- web server
class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, panel, port):
        super().__init__(("127.0.0.1", port), Handler)
        self.panel = panel
        self.port = self.server_address[1]
        self.token = secrets.token_urlsafe(24)
        self.hosts = {"127.0.0.1:%d" % self.port, "localhost:%d" % self.port}
        self.origins = {"http://" + h for h in self.hosts}
        self.last_seen = time.monotonic()
        self.bye_at = None


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "GK600Panel/" + __version__

    def log_message(self, fmt, *args):
        pass

    # ------------------------------------------------------------ helpers
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, code, key, detail=""):
        self._json(code, {"ok": False, "error": key, "detail": detail})

    def _allowed(self, need_token=True):
        """Our own page only: right Host (no DNS rebinding), right Origin (no other website),
        and the token the page received at start-up."""
        s = self.server
        origin = self.headers.get("Origin")
        if self.headers.get("Host") not in s.hosts or (origin and origin not in s.origins):
            self._error(403, "forbidden")
            return False
        if need_token and not secrets.compare_digest(self.headers.get("X-Token", ""), s.token):
            self._error(403, "forbidden")
            return False
        s.last_seen = time.monotonic()
        s.bye_at = None
        return True

    def _body(self, limit):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise ValueError("too large")
        return self.rfile.read(n) if n else b""

    # ------------------------------------------------------------ routes
    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path in ("/", "/index.html"):
            if not self._allowed(need_token=False):
                return
            try:
                page = open(WEB, encoding="utf-8").read()
            except OSError:
                return self._error(500, "missing_page")
            page = page.replace("__GK600_TOKEN__", self.server.token).replace("__GK600_VERSION__", __version__)
            return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        if path == "/favicon.ico":
            if self._allowed(need_token=False):
                self._send(204, b"", "image/x-icon")
            return
        if path == "/api/ping":                     # lets a second launch find this one
            if self._allowed(need_token=False):
                self._json(200, {"app": "gk600-panel"})
            return
        if not self._allowed():
            return
        panel = self.server.panel
        if path == "/api/status":
            return self._json(200, panel.status())
        if path == "/api/log":
            return self._json(200, {"lines": panel.lines[-120:]})
        if path.startswith("/api/preview/"):
            data, ctype = panel.preview(path.rsplit("/", 1)[1])
            if data is None:
                return self._error(404, "not_found")
            return self._send(200, data, ctype)
        self._error(404, "not_found")

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        panel = self.server.panel
        if u.path == "/api/bye":                    # sent by the page as it closes (no custom header)
            try:
                token = self._body(256).decode("ascii", "ignore")
            except ValueError:
                token = ""
            origin = self.headers.get("Origin")
            if (self.headers.get("Host") in self.server.hosts and (not origin or origin in self.server.origins)
                    and secrets.compare_digest(token, self.server.token)):
                self.server.bye_at = time.monotonic()
            return self._send(204, b"", "text/plain")
        if not self._allowed():
            return
        try:
            if u.path == "/api/file":
                q = urllib.parse.parse_qs(u.query)
                name = urllib.parse.unquote(self.headers.get("X-File-Name", "file"))
                data = self._body(MAX_UPLOAD)
                if not data:
                    return self._error(400, "bad_file", "empty file")
                res = panel.add_file(q.get("kind", [""])[0], name, data, q.get("fill", ["0"])[0] == "1")
                return self._json(200, dict(res, ok=True))
            body = json.loads(self._body(64 << 10) or b"{}")
            if u.path == "/api/light":
                panel.apply_lighting(body)
                return self._json(200, {"ok": True})
            if u.path == "/api/job":
                return self._json(200, {"ok": True, "job": panel.start_job(body.get("kind"), body.get("id"),
                                                                            bool(body.get("keep_home")))})
            if u.path == "/api/job/cancel":
                return self._json(200, {"ok": panel.cancel_job()})
            self._error(404, "not_found")
        except ValueError as e:
            self._error(400, "bad_request", str(e))
        except g.RestoreError as e:
            self._error(400, "busy" if str(e).startswith("busy") else error_key(e), str(e))
        except Exception as e:
            panel.log("request error:\n%s" % traceback.format_exc())
            self._error(500, "internal", "%s: %s" % (type(e).__name__, e))


def watchdog(server):
    """Stops the server when the page is gone (closed tab, or no request for a while)."""
    while True:
        time.sleep(1)
        job = server.panel.job
        if job and job.active:
            continue
        now = time.monotonic()
        if (server.bye_at and now - server.bye_at > 6) or now - server.last_seen > IDLE_EXIT_S:
            server.shutdown()
            return


def find_edge():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.environ.get("LocalAppData")):
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.isfile(p):
                return p
    return None


def open_page(url):
    edge = find_edge()
    if edge:
        try:
            subprocess.Popen([edge, "--app=" + url, "--window-size=1180,860"])
            return
        except OSError:
            pass
    webbrowser.open(url)


def already_running(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1) as s:
            s.sendall(b"GET /api/ping HTTP/1.0\r\nHost: 127.0.0.1:%d\r\n\r\n" % port)
            return b"gk600-panel" in s.recv(4096)
    except OSError:
        return False


def make_server(panel, port=PORT):
    try:
        return Server(panel, port)
    except OSError:
        return Server(panel, 0)                  # port taken by something else: any free port


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if already_running(PORT):
        print("The panel is already running: opening it again.", flush=True)
        open_page("http://127.0.0.1:%d/" % PORT)
        return 0
    panel = Panel()
    server = make_server(panel)
    url = "http://127.0.0.1:%d/" % server.port
    panel.log("panel %s started on %s" % (__version__, url))
    print("GK600 panel %s: %s" % (__version__, url), flush=True)
    print("Garde cette fenêtre ouverte pendant que tu utilises le panneau. / "
          "Keep this window open while you use the panel.", flush=True)
    threading.Thread(target=watchdog, args=(server,), daemon=True).start()
    open_page(url)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        panel.close()
    print("Panel stopped.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

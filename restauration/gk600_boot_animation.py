#!/usr/bin/env python3
"""
gk600_boot_animation.py - EXPERIMENTAL - replaces the GK600 TKL boot animation (the MSI
logo played at power-on) with your own animated GIF, or a still picture.

Where it lives (GK600 dump; playback checked by running the real code of the Frieren V1.17
firmware, the GK600's sibling, in emulation):
  0x1A0000  256-byte header. Byte 0 = number of frames N (1 to 72). Byte i, for i from 1
            to N-2, = how long frame i stays on screen, in 2 ms steps (16 to 255, i.e.
            32 to 510 ms; 15 or less means 50 ms).
  0x1A0100  N frames of 160 x 96, raw RGB565 little-endian, 30 720 bytes each.
Playback: frame 0 stays 50 ms, frames 1 to N-2 their own time, the last frame 1 s, then
the home screen (or your GIF, if it was on screen when the keyboard was switched off).
A single frame stays 3 s. The backlight only comes on about half a second after power-on:
by default the first picture is held during that time (--lead-in), so the animation starts
when the screen lights up.

How: 04 38 always writes from 0x000000, so the tool rewrites [0x000000, end of the new
animation) - about 800 pages and 2 minutes for 50 frames, at most 957 pages - with the
reference dump for the menus and icons, exactly like `gk600_restore.py restore --with-boot`.
Your GIF (0x3C0000) is never touched. The home-screen picture comes back to the dragon
unless you give yours again with --home.

Animation: GIF, animated PNG / WebP, or a single PNG / JPG (needs Pillow). Each frame is
fitted into 160 x 96 on black (aspect ratio kept); --fill crops it to fill the screen.
Frame times come from the file (--delay forces one value). More than 72 frames: frames are
picked evenly, the total time is kept.

Back to the MSI animation:  python gk600_restore.py restore --with-boot --write

Usage (gk600_restore.py, gk600_home_picture.py and the reference dump in the same folder):
  python gk600_boot_animation.py anim.gif --preview preview.gif    animation as it will play
  python gk600_boot_animation.py anim.gif                          dry run, nothing sent
  python gk600_boot_animation.py anim.gif --write
  python gk600_boot_animation.py anim.gif --home my_home.png --write   keep your home picture
"""

import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gk600_restore as g  # noqa: E402

__version__ = "0.1-experimental"

HDR_ADDR = g.MENUS_END                 # 0x1A0000: boot animation header
HDR_SIZE = 0x100
FRAMES_ADDR = HDR_ADDR + HDR_SIZE      # 0x1A0100: first frame
W, H = 160, 96
FRAME_SIZE = W * H * 2                 # 30 720 bytes (0x7800)
MAX_FRAMES = (g.USER_GIF - FRAMES_ADDR) // FRAME_SIZE   # 72: the last one ends at 0x3BC100

TICK_MS = 2                            # firmware animation tick (0x11428, every 2 ms)
MIN_TICKS, MAX_TICKS = 16, 255         # 15 or less is replaced by 25 ticks by the firmware
FIRST_MS = 50                          # frame 0: initial period, 25 ticks
LAST_MS = 1000                         # last frame: 500 ticks (0xFE74(500))
SINGLE_MS = 3000                       # N = 1: 1500 ticks
DEFAULT_MS = 100                       # GIF frames without a usable time (0 to 10 ms)
LEAD_IN_MS = 500                       # backlight comes on about 0.5 s after power-on
LEAD_DARK_MS = 500                     # what the preview shows as a dark screen


def _pil():
    try:
        from PIL import Image
        return Image
    except ImportError:
        raise g.RestoreError("Pillow is needed for GIF / PNG / JPG files and previews "
                             "(pip install pillow)")


# ---------------------------------------------------------------- frames
def _flatten(im, Image):
    """RGB on black, whatever the mode and transparency of the source frame."""
    im = im.convert("RGBA")
    flat = Image.new("RGB", im.size)
    flat.paste(im, mask=im.split()[3])
    return flat


def _fit(im, Image, fill):
    if im.size == (W, H):
        return im
    w, h = im.size
    s = max(W / w, H / h) if fill else min(W / w, H / h)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H))
    canvas.paste(im, ((W - nw) // 2, (H - nh) // 2))     # negative offsets crop (fill)
    return canvas


def to_rgb565(im):
    rgb = im.tobytes()
    out = bytearray(len(rgb) // 3 * 2)
    j = 0
    for i in range(0, len(rgb), 3):
        v = (rgb[i] >> 3) << 11 | (rgb[i + 1] >> 2) << 5 | (rgb[i + 2] >> 3)
        out[j] = v & 0xFF
        out[j + 1] = v >> 8
        j += 2
    return bytes(out)


def load_animation(path, fill=False, delay_ms=None):
    """Returns [(rgb565 frame, ms), ...] in display order."""
    Image = _pil()
    from PIL import ImageSequence
    try:
        im = Image.open(path)
        im.load()
    except Exception as e:
        raise g.RestoreError("%s: not a picture or animation Pillow can read (%s)" % (path, e))
    frames = []
    for fr in ImageSequence.Iterator(im):
        ms = delay_ms if delay_ms else fr.info.get("duration", 0) or 0
        if ms <= 10:                         # like web browsers: 0-10 ms plays at 100 ms
            ms = DEFAULT_MS
        frames.append((to_rgb565(_fit(_flatten(fr, Image), Image, fill)), int(ms)))
    if not frames:
        raise g.RestoreError("%s: no frame found" % path)
    return frames


def pick(frames, count):
    """`count` frames picked evenly; each keeps the time of the frames it stands for."""
    n = len(frames)
    if count >= n:
        return list(frames)
    idx = [k * n // count for k in range(count)]
    out = []
    for k, i in enumerate(idx):
        j = idx[k + 1] if k + 1 < count else n
        out.append((frames[i][0], sum(ms for _, ms in frames[i:j])))
    return out


# ---------------------------------------------------------------- boot area
def _chunks(ms):
    """Splits a time into slot times the header can hold (32 to 510 ms each)."""
    out = []
    while ms > MAX_TICKS * TICK_MS:
        out.append(MAX_TICKS * TICK_MS)
        ms -= MAX_TICKS * TICK_MS
    if ms >= MIN_TICKS * TICK_MS:
        out.append(ms)
    elif ms >= 16:                           # 16-31 ms: rounded up to the shortest slot
        out.append(MIN_TICKS * TICK_MS)
    return out


def slots_for(frames, lead_in_ms):
    """Firmware slots [(frame, ms)] giving, as closely as possible: the first picture held
    `lead_in_ms` + its own time, then each frame for its time. Slot 0 always lasts 50 ms and
    the last slot 1 s (both fixed by the firmware)."""
    if len(frames) == 1:
        return [(frames[0][0], SINGLE_MS)]
    first, ms0 = frames[0]
    slots = [(first, FIRST_MS)]
    slots += [(first, t) for t in _chunks(lead_in_ms + ms0 - FIRST_MS)]
    for data, ms in frames[1:-1]:
        parts = _chunks(ms) or [MIN_TICKS * TICK_MS]
        slots += [(data, t) for t in parts]
    slots.append((frames[-1][0], LAST_MS))
    return slots


def plan(frames, lead_in_ms=LEAD_IN_MS):
    """Fits the animation into the 72 frames of the boot area. Returns (slots, frames used)."""
    count = len(frames)
    while True:
        used = pick(frames, count)
        slots = slots_for(used, lead_in_ms)
        if len(slots) <= MAX_FRAMES:
            return slots, used
        count -= max(1, len(slots) - MAX_FRAMES)
        if count < 1:
            raise g.RestoreError("animation cannot fit in %d frames" % MAX_FRAMES)


def ticks(ms):
    return max(MIN_TICKS, min(MAX_TICKS, int(round(ms / TICK_MS))))


def build_boot_area(slots):
    n = len(slots)
    if not 1 <= n <= MAX_FRAMES:
        raise g.RestoreError("1 to %d frames, got %d" % (MAX_FRAMES, n))
    hdr = bytearray(HDR_SIZE)
    hdr[0] = n
    for i in range(1, n - 1):                # slot 0 and the last slot: fixed by the firmware
        hdr[i] = ticks(slots[i][1])
    body = b"".join(data for data, _ in slots)
    if any(len(data) != FRAME_SIZE for data, _ in slots):
        raise g.RestoreError("internal error: frame size")
    return bytes(hdr) + body


def playback(slots):
    """What the firmware will show: [(frame, ms)], from the header it will read."""
    area = build_boot_area(slots)
    n = area[0]
    if n == 1:
        return [(slots[0][0], SINGLE_MS)]
    out = []
    for i, (data, _) in enumerate(slots):
        if i == 0:
            ms = FIRST_MS
        elif i == n - 1:
            ms = LAST_MS
        else:
            t = area[i]
            ms = (t if t > 15 else 25) * TICK_MS
        out.append((data, ms))
    return out


def build_payload(reference, boot_area, home=None):
    payload = bytearray(reference[:HDR_ADDR])
    if len(payload) != HDR_ADDR:
        raise g.RestoreError("reference image too short")
    if home is not None:
        import gk600_home_picture as hp
        if len(home) != hp.PIC_SIZE or not hp.PIC_ADDR + hp.PIC_SIZE <= HDR_ADDR:
            raise g.RestoreError("home picture must be %d bytes" % hp.PIC_SIZE)
        payload[hp.PIC_ADDR:hp.PIC_ADDR + hp.PIC_SIZE] = home
    payload += boot_area
    payload += bytes(-len(payload) % g.PAGE)        # zeros up to the page, like the dump
    if len(payload) > g.USER_GIF:
        raise g.RestoreError("internal layout check failed (would reach the user GIF)")
    return bytes(payload)


# ---------------------------------------------------------------- preview
def _image(data, Image):
    rgb = bytearray(W * H * 3)
    for k in range(W * H):
        v = data[2 * k] | data[2 * k + 1] << 8
        rgb[3 * k] = (v >> 11) * 255 // 31
        rgb[3 * k + 1] = ((v >> 5) & 63) * 255 // 63
        rgb[3 * k + 2] = (v & 31) * 255 // 31
    return Image.frombytes("RGB", (W, H), bytes(rgb))


def save_preview(slots, path, reference=None, home=None, scale=3):
    """Animated GIF of what the screen shows: dark until the backlight comes on, the boot
    animation with its real times, then the home screen."""
    Image = _pil()
    seq, t = [], 0
    for data, ms in playback(slots):
        dark = max(0, min(ms, LEAD_DARK_MS - t))
        if dark:
            seq.append((Image.new("RGB", (W, H)), dark))
        if ms - dark:
            seq.append((_image(data, Image), ms - dark))
        t += ms
    if reference is not None:
        import gk600_home_picture as hp
        pic = home if home is not None else reference[hp.PIC_ADDR:hp.PIC_ADDR + hp.PIC_SIZE]
        tmp = path + ".home.png"
        hp.save_preview(reference, pic, tmp, scale=1)
        seq.append((Image.open(tmp).convert("RGB"), 2000))
        os.remove(tmp)
    big = [im.resize((W * scale, H * scale), Image.NEAREST) for im, _ in seq]
    big[0].save(path, save_all=True, append_images=big[1:], duration=[ms for _, ms in seq],
                loop=0, optimize=False, disposal=1)


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="GK600 TKL boot animation (experimental)")
    ap.add_argument("animation", help="GIF, animated PNG / WebP, or a PNG / JPG picture")
    ap.add_argument("--image", help="full 16 MiB public dump or the 0x1A0000-byte menus image")
    ap.add_argument("--home", metavar="PICTURE",
                    help="keep your own home-screen picture (same files as gk600_home_picture.py)")
    ap.add_argument("--fill", action="store_true", help="crop to fill the screen instead of fitting")
    ap.add_argument("--delay", type=int, metavar="MS", help="same time for every frame (32 to 510)")
    ap.add_argument("--lead-in", type=int, default=LEAD_IN_MS, metavar="MS",
                    help="hold the first picture while the backlight comes on (default 500, 0 = off)")
    ap.add_argument("--preview", metavar="GIF", help="only save the animation as it will play, send nothing")
    ap.add_argument("--write", action="store_true", help="really send (default: dry run)")
    ap.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    ap.add_argument("--ack-timeout", type=float, default=2.0)
    ap.add_argument("--log", default="gk600_restore.log")
    args = ap.parse_args(argv)
    log = g.Logger(args.log)
    log("gk600_boot_animation %s (gk600_restore %s)" % (__version__, g.__version__))

    try:
        if args.delay is not None and not 32 <= args.delay <= 510:
            raise g.RestoreError("--delay must be between 32 and 510 ms")
        if not 0 <= args.lead_in <= 2000:
            raise g.RestoreError("--lead-in must be between 0 and 2000 ms")
        frames = load_animation(args.animation, args.fill, args.delay)
        slots, used = plan(frames, args.lead_in)
        home = None
        if args.home:
            import gk600_home_picture as hp
            home = hp.load_picture(args.home)
        src, ref = g.find_reference(args.image, g.MENUS_END)
        area = build_boot_area(slots)
        payload = build_payload(ref, area, home)
        total = sum(ms for _, ms in playback(slots))
        log("Animation: %s, %d frame(s)%s -> %d frames in the boot area, %.1f s on screen"
            % (os.path.basename(args.animation), len(frames),
               " (%d kept)" % len(used) if len(used) != len(frames) else "", len(slots),
               total / 1000.0))
        log("Home     : %s" % (os.path.basename(args.home) if args.home
                               else "dragon from the reference dump"))
        if args.preview:
            save_preview(slots, args.preview, ref, home)
            log("Preview  : %s (nothing was sent)" % args.preview)
            return 0
        info = g.select_keyboard(log)
        log("Payload  : %d pages, SHA-256 %s" % (len(payload) // g.PAGE,
                                                  hashlib.sha256(payload).hexdigest()))
        what = ("BOOT ANIMATION: %s (%d frames, %.1f s); menus and icons from %s; home picture: %s; "
                "[0, 0x%X), %d pages" % (os.path.basename(args.animation), len(slots), total / 1000.0,
                                         os.path.basename(src),
                                         os.path.basename(args.home) if args.home else "dragon",
                                         len(payload), len(payload) // g.PAGE))
        if not g.confirm(args, what, log):
            return 0
        t = g.HidTransport(info)
        try:
            g.raw_write(t, payload, args.ack_timeout, log=log, progress=g.progress_bar)
        finally:
            t.close()
        log("\nDone. Switch the keyboard off and on: your animation plays at power-on.")
        log("Back to the MSI animation:  python gk600_restore.py restore --with-boot --write")
        return 0
    except g.RestoreError as e:
        log("\nERROR: %s" % e)
        return 2
    except KeyboardInterrupt:
        log("\nINTERRUPTED. If pages were being sent: unplug the cable, switch the keyboard OFF and ON,"
            " then run the same command again (it rewrites everything from the start).")
        return 3


if __name__ == "__main__":
    sys.exit(main())

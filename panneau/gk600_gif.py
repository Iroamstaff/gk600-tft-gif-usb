#!/usr/bin/env python3
"""
gk600_gif.py - EXPERIMENTAL - sends your GIF to the screen of the MSI Forge GK600 TKL Wireless
over USB, the way MSI's software does it, without MSI's software.

Where it goes: the GIF slot at 0x3C0000 (command 04 72, slot 1, the one MSI's software uses):
  a 256-byte header: byte 0 = number of frames (1 to 255), byte 1 + i = time of frame i in 2 ms
  steps (at least 1, like MSI's driver), then the frames, 160 x 96, RGB565 little-endian.
Only that area is written: menus, home picture and boot animation are not touched. 255 frames at
most, like MSI's software: a GIF of about 420 frames or more would run past the end of the chip
and wipe the menus.

Animation: GIF, animated PNG / WebP, or a single PNG / JPG (needs Pillow). Each frame is fitted
into 160 x 96 on black (aspect ratio kept); --fill crops it to fill the screen. Frame times come
from the file (--delay forces one value). More than 255 frames: frames are picked evenly, the
total time is kept (one frame lasts 510 ms at most).

Usage (gk600_restore.py and gk600_boot_animation.py in ../restauration):
  python gk600_gif.py anim.gif --preview preview.gif    the GIF as the screen will play it
  python gk600_gif.py anim.gif                          dry run, nothing sent
  python gk600_gif.py anim.gif --write
"""

import argparse
import hashlib
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "restauration"))
import gk600_restore as g  # noqa: E402
import gk600_boot_animation as ba  # noqa: E402

__version__ = "0.1-experimental"

SLOT_ADDR = g.USER_GIF                  # 0x3C0000
SLOT_NUMBER = 1                         # byte 2 of 04 72, as sent by MSI's driver
HDR_SIZE = 0x100
FRAME_SIZE = ba.FRAME_SIZE              # 160 x 96 x 2
MAX_FRAMES = 255                        # byte 0 of the header; MSI's gif_maxframes
CHIP_END = 16 << 20
TICK_MS = 2


def ticks(ms):
    return max(1, min(255, int(round(ms / TICK_MS))))


def plan(frames, max_frames=MAX_FRAMES):
    """At most `max_frames` frames, picked evenly, each keeping the time of those it replaces."""
    return ba.pick(frames, min(len(frames), max_frames))


def build_stream(frames):
    n = len(frames)
    if not 1 <= n <= MAX_FRAMES:
        raise g.RestoreError("1 to %d frames, got %d" % (MAX_FRAMES, n))
    if any(len(data) != FRAME_SIZE for data, _ in frames):
        raise g.RestoreError("internal error: frame size")
    hdr = bytearray(HDR_SIZE)
    hdr[0] = n
    for i, (_, ms) in enumerate(frames):
        hdr[1 + i] = ticks(ms)
    stream = bytes(hdr) + b"".join(data for data, _ in frames)
    stream += bytes(-len(stream) % g.PAGE)
    if SLOT_ADDR + len(stream) > CHIP_END:
        raise g.RestoreError("internal layout check failed (would run past the end of the chip)")
    return stream


def check_stream(stream):
    """Last check before anything reaches the keyboard. Returns the number of pages."""
    if not stream or len(stream) % g.PAGE:
        raise g.RestoreError("the GIF data must be a non-empty multiple of 4096 bytes")
    n = stream[0]
    if not 1 <= n <= MAX_FRAMES:
        raise g.RestoreError("frame count must be 1 to %d (header says %d)" % (MAX_FRAMES, n))
    if len(stream) != -(-(HDR_SIZE + n * FRAME_SIZE) // g.PAGE) * g.PAGE:
        raise g.RestoreError("GIF data size does not match its %d frames" % n)
    if any(stream[1 + i] == 0 for i in range(n)):
        raise g.RestoreError("a frame time of 0 is not allowed")
    return len(stream) // g.PAGE


def playback(stream):
    """[(frame, ms)] as stored in the header."""
    n = stream[0]
    return [(stream[HDR_SIZE + i * FRAME_SIZE:HDR_SIZE + (i + 1) * FRAME_SIZE], stream[1 + i] * TICK_MS)
            for i in range(n)]


def save_preview(stream, path, scale=3):
    """Animated GIF of what the screen will play, looping like the keyboard does."""
    Image = ba._pil()
    seq = [(ba._image(data, Image).resize((ba.W * scale, ba.H * scale), Image.NEAREST), ms)
           for data, ms in playback(stream)]
    seq[0][0].save(path, save_all=True, append_images=[im for im, _ in seq[1:]],
                   duration=[ms for _, ms in seq], loop=0, optimize=False, disposal=1)


def gif_write(t, stream, ack_timeout=2.0, log=print, progress=None):
    """Writes `stream` to the GIF slot with 04 72. Stops at the first anomaly."""
    pages = check_stream(stream)
    log("[1/4] 04 18 handshake")
    g.handshake(t, log=log)

    log("[2/4] 04 72 GIF upload to 0x%06X, %d pages" % (SLOT_ADDR, pages))
    r = g.command(t, 0x72, SLOT_NUMBER, pages, log=log)
    if r[0] != 0x04 or r[1] != 0x72 or r[3] != 0x01:
        raise g.RestoreError("04 72 refused (reply %s). No page was sent. Switch the keyboard off "
                             "and on before trying again." % r[:10].hex(" "))
    early = t.read_ack(0.1)
    if early:
        log("  note: report before the first page: %s" % bytes(early[:8]).hex(" "))

    log("[3/4] sending %d pages (each must be acknowledged with 01 5A 02)" % pages)
    t0 = time.time()
    for i in range(pages):
        t.write_page(stream[i * g.PAGE:(i + 1) * g.PAGE])
        a = t.read_ack(ack_timeout)
        if a is None or bytes(a[:3]) != g.ACK:
            raise g.RestoreError(
                "page %d/%d: %s. STOP. Unplug the cable, switch the keyboard off and on, then send "
                "the GIF again." % (i + 1, pages, "no ACK" if a is None else "bad ACK " + bytes(a[:8]).hex(" ")))
        if progress:
            progress(i + 1, pages, time.time() - t0)

    log("[4/4] 04 02 close")
    r = g.command(t, 0x02, log=log)
    if r[3] != 0x01:
        raise g.RestoreError("04 02 not acknowledged (reply %s). The pages were written; switch the "
                             "keyboard off and on and check the screen." % r[:8].hex(" "))
    return pages


def main(argv=None):
    ap = argparse.ArgumentParser(description="GK600 TKL: send a GIF to the screen (experimental)")
    ap.add_argument("animation", help="GIF, animated PNG / WebP, or a PNG / JPG picture")
    ap.add_argument("--fill", action="store_true", help="crop to fill the screen instead of fitting")
    ap.add_argument("--delay", type=int, metavar="MS", help="same time for every frame (2 to 510)")
    ap.add_argument("--preview", metavar="GIF", help="only save the GIF as it will play, send nothing")
    ap.add_argument("--write", action="store_true", help="really send (default: dry run)")
    ap.add_argument("--ack-timeout", type=float, default=2.0)
    ap.add_argument("--log", default="gk600_panel.log")
    args = ap.parse_args(argv)
    log = g.Logger(args.log)
    log("gk600_gif %s (gk600_restore %s)" % (__version__, g.__version__))
    try:
        if args.delay is not None and not 2 <= args.delay <= 510:
            raise g.RestoreError("--delay must be between 2 and 510 ms")
        frames = ba.load_animation(args.animation, args.fill, args.delay)
        used = plan(frames)
        stream = build_stream(used)
        total = sum(ms for _, ms in playback(stream))
        log("GIF      : %s, %d frame(s)%s, %.1f s per loop, %d pages"
            % (os.path.basename(args.animation), len(frames),
               " (%d kept)" % len(used) if len(used) != len(frames) else "", total / 1000.0,
               len(stream) // g.PAGE))
        if args.preview:
            save_preview(stream, args.preview)
            log("Preview  : %s (nothing was sent)" % args.preview)
            return 0
        info = g.select_keyboard(log)
        log("Payload  : %d pages, SHA-256 %s" % (len(stream) // g.PAGE, hashlib.sha256(stream).hexdigest()))
        if not args.write:
            log("\nDRY RUN: nothing was sent. Add --write to do it.")
            return 0
        t = g.HidTransport(info)
        try:
            gif_write(t, stream, args.ack_timeout, log=log, progress=g.progress_bar)
        finally:
            t.close()
        log("\nDone. The screen now plays your GIF (Fn + left / right switches with the home screen).")
        return 0
    except g.RestoreError as e:
        log("\nERROR: %s" % e)
        return 2
    except KeyboardInterrupt:
        log("\nINTERRUPTED. If pages were being sent: unplug the cable, switch the keyboard off and on, "
            "then send the GIF again.")
        return 3


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
gk600_home_picture.py - EXPERIMENTAL - replaces the picture of the GK600 TKL home screen
(the dragon in front of the laptop) with your own 160 x 65 picture.

Where it lives (GK600 dump, checked on a real keyboard, firmware V1.20):
  0x17A1CE, 160 px wide, drawn from the top-left corner of the screen. Rows 0 to 64 are
  shown (160 x 65); below them the screen shows the background, then the bottom bar.
  The battery icon is drawn on top of the picture at x 131-155, y 10-22.

How: 04 38 always writes from 0x000000, so the tool rewrites [0x000000, 0x180000)
(384 pages, about one minute) with the reference dump, your picture in place of the
dragon. Menus and icons come from the dump, exactly as with `gk600_restore.py restore`.
Your GIF and the boot animation are not touched.

Picture: raw RGB565 little-endian, 160 x 65 (20 800 bytes), or a PNG / JPG when Pillow is
installed. An exact 160 x 65 picture is used as it is; any other size has its plain margins
trimmed, then is fitted into 160 x 65 on black (aspect ratio kept, transparency becomes black).

Back to the dragon:  python gk600_restore.py restore --write

Usage (gk600_restore.py and the reference dump in the same folder):
  python gk600_home_picture.py my_picture.png --preview preview.png   picture of the result
  python gk600_home_picture.py my_picture.png                         dry run, nothing sent
  python gk600_home_picture.py my_picture.png --write
"""

import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gk600_restore as g  # noqa: E402

__version__ = "0.2-experimental"

PIC_ADDR = 0x17A1CE           # right after the last small icon (0x179E6E, 27 x 16)
PIC_W, PIC_H = 160, 65
PIC_SIZE = PIC_W * PIC_H * 2  # 20 800 bytes, ends at 0x17F30E
END = 0x180000                # next page boundary: 384 pages from 0x000000

# home-screen icons drawn over / under the picture (address, w, h, x, y), from the dump
OVERLAYS = [(0x84B2, 25, 13, 131, 10),    # battery
            (0xFE2E, 21, 20, 4, 71),      # WIN / MAC
            (0xE13C, 64, 20, 26, 71),     # connection
            (0x10176, 21, 20, 92, 71),    # Windows lock
            (0xEB3C, 21, 20, 113, 71),    # Caps Lock
            (0xF456, 21, 20, 135, 71)]    # Num Lock


def _pil():
    try:
        from PIL import Image
        return Image
    except ImportError:
        raise g.RestoreError("Pillow is needed for PNG / JPG pictures and previews "
                             "(pip install pillow)")


def trim_borders(im, tolerance=40, margin=2):
    """Crops uniform margins (same colour as the top-left pixel), so a logo on a large plain
    background fills the 160 x 65 area. A photo without plain margins is left as it is."""
    from PIL import ImageChops
    bg = im.copy()
    bg.paste(im.getpixel((0, 0)), (0, 0, im.width, im.height))
    diff = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > tolerance else 0)
    box = diff.getbbox()
    if not box:
        return im
    l, t, r, b = box
    return im.crop((max(0, l - margin), max(0, t - margin), min(im.width, r + margin),
                    min(im.height, b + margin)))


def load_picture(path):
    data = open(path, "rb").read()
    if len(data) == PIC_SIZE:
        return data
    Image = _pil()
    try:
        im = Image.open(path)
        im.load()
    except Exception as e:
        raise g.RestoreError("%s: not a picture Pillow can read (%s)" % (path, e))
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        flat = Image.new("RGB", im.size)
        flat.paste(im, mask=im.split()[3])
        im = flat
    else:
        im = im.convert("RGB")
    if im.size != (PIC_W, PIC_H):        # an exact 160 x 65 picture is used as it is
        im = trim_borders(im)
        im.thumbnail((PIC_W, PIC_H), Image.LANCZOS)
    canvas = Image.new("RGB", (PIC_W, PIC_H))
    canvas.paste(im, ((PIC_W - im.width) // 2, (PIC_H - im.height) // 2))
    rgb = canvas.tobytes()            # R, G, B bytes, row by row
    out = bytearray()
    for i in range(0, len(rgb), 3):
        out += g.rgb565le(rgb[i], rgb[i + 1], rgb[i + 2])
    return bytes(out)


def _rgb(buf, o):
    v = buf[o] | buf[o + 1] << 8
    return ((v >> 11) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)


def save_preview(reference, picture, path, scale=4):
    """The home screen as the keyboard will draw it: picture, then the icons from the dump."""
    Image = _pil()
    scr = Image.new("RGB", (160, 96))
    px = scr.load()
    for y in range(PIC_H):
        for x in range(PIC_W):
            px[x, y] = _rgb(picture, 2 * (y * PIC_W + x))
    for addr, w, h, x0, y0 in OVERLAYS:
        for y in range(h):
            for x in range(w):
                px[x0 + x, y0 + y] = _rgb(reference, addr + 2 * (y * w + x))
    scr.resize((160 * scale, 96 * scale), Image.NEAREST).save(path)


def build_payload(reference, picture):
    if len(picture) != PIC_SIZE:
        raise g.RestoreError("picture must be %d bytes" % PIC_SIZE)
    if not (PIC_ADDR + PIC_SIZE <= END <= g.MENUS_END and END % g.PAGE == 0):
        raise g.RestoreError("internal layout check failed")
    payload = bytearray(reference[:END])
    payload[PIC_ADDR:PIC_ADDR + PIC_SIZE] = picture
    return bytes(payload)


def main(argv=None):
    ap = argparse.ArgumentParser(description="GK600 TKL home-screen picture (experimental)")
    ap.add_argument("picture", help="160x65 raw RGB565 LE file, or PNG/JPG with Pillow installed")
    ap.add_argument("--image", help="full 16 MiB public dump or the 0x1A0000-byte menus image")
    ap.add_argument("--preview", metavar="PNG", help="only save a picture of the result, send nothing")
    ap.add_argument("--write", action="store_true", help="really send (default: dry run)")
    ap.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    ap.add_argument("--ack-timeout", type=float, default=2.0)
    ap.add_argument("--log", default="gk600_restore.log")
    args = ap.parse_args(argv)
    log = g.Logger(args.log)
    log("gk600_home_picture %s (gk600_restore %s)" % (__version__, g.__version__))

    try:
        picture = load_picture(args.picture)
        src, ref = g.find_reference(args.image, g.MENUS_END)
        payload = build_payload(ref, picture)
        log("Picture  : %s, 160 x 65 at 0x%06X, SHA-256 %s"
            % (os.path.basename(args.picture), PIC_ADDR, hashlib.sha256(picture).hexdigest()))
        if args.preview:
            save_preview(ref, picture, args.preview)
            log("Preview  : %s (nothing was sent)" % args.preview)
            return 0
        info = g.select_keyboard(log)
        log("Payload  : %d pages, SHA-256 %s" % (len(payload) // g.PAGE,
                                                  hashlib.sha256(payload).hexdigest()))
        what = ("HOME PICTURE: %s in place of the dragon; menus and icons from %s; [0, 0x%X), "
                "%d pages" % (os.path.basename(args.picture), os.path.basename(src), END,
                              END // g.PAGE))
        if not g.confirm(args, what, log):
            return 0
        t = g.HidTransport(info)
        try:
            g.raw_write(t, payload, args.ack_timeout, log=log, progress=g.progress_bar)
        finally:
            t.close()
        log("\nDone. The keyboard redraws its home screen: your picture should be there.")
        log("Back to the dragon:  python gk600_restore.py restore --write")
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

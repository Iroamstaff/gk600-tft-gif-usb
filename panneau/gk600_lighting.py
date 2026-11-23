#!/usr/bin/env python3
"""
gk600_lighting.py - EXPERIMENTAL - keyboard lighting (one effect for the whole keyboard) of the
MSI Forge GK600 TKL Wireless, over USB, without MSI's software.

Protocol (64-byte feature reports on the command interface, usage page FF13):
    04 18                -> open                     (acknowledged: byte 3 = 01)
    04 13 .. byte 8 = 01 -> select the lighting block (acknowledged)
    64-byte settings     -> echoed back by the keyboard
    04 02                -> apply and close          (acknowledged)
Settings: [0] effect, [1:4] colour R G B, [8] multicolour, [9] brightness 1-5, [10] speed 1-5,
[11] direction 0-3, [14:16] AA 55.

Source: the open-source GK600 panel "MSI-Forge-GK600-Software" (ahmettahaklc, MIT licence, see
THIRD_PARTY_NOTICES.md), which checked it on a GK600 and took it from the AULA F75 Max, a keyboard
of the same platform. The effect numbers follow the order of MSI's own software (strings 521 to
539 of its language files). On the Frieren V1.17 firmware run in an emulator, every step is
acknowledged and the keyboard stores the settings in its own memory (MCU flash): send them when
the user asks, not on every slider move.

Usage (gk600_restore.py in ../restauration):
  python gk600_lighting.py list
  python gk600_lighting.py static --color ff0000 --brightness 5
  python gk600_lighting.py rolling --speed 3 --multicolour
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "restauration"))
import gk600_restore as g  # noqa: E402

__version__ = "0.1-experimental"

# (id used in the protocol, English name in MSI's software, French name in traduction-fr)
EFFECTS = [
    ("off", "Off", "Éteint"),
    ("static", "Static", "Fixe"),
    ("singleon", "SingleOn", "Touche allumée"),
    ("singleoff", "SingleOff", "Touche éteinte"),
    ("glittering", "Glittering", "Scintillement"),
    ("falling", "Falling", "Chute"),
    ("colourful", "Colourful", "Multicolore"),
    ("breath", "Breath", "Respiration"),
    ("spectrum", "Spectrum", "Spectre"),
    ("outward", "Outward", "Vers l'extérieur"),
    ("scrolling", "Scrolling", "Défilement"),
    ("rolling", "Rolling", "Roulement"),
    ("rotating", "Rotating", "Rotation"),
    ("explode", "Explode", "Explosion"),
    ("launch", "Launch", "Lancement"),
    ("ripples", "Ripples", "Ondulations"),
    ("flowing", "Flowing", "Écoulement"),
    ("pulsating", "Pulsating", "Pulsation"),
    ("tilt", "Tilt", "Inclinaison"),
    ("shuttle", "Shuttle", "Navette"),
]
DEFAULT = {"effect": 11, "color": (255, 0, 0), "multicolour": False, "brightness": 5, "speed": 3,
           "direction": 0}                      # rgb-keyboard.xml: default_mode 11, brightness 5, speed 3
DEFAULT_JSON = dict(DEFAULT, color="#ff0000")
LIGHT_BLOCK = 0x13


def effect_index(name):
    for i, (key, en, fr) in enumerate(EFFECTS):
        if name.lower() in (key, en.lower(), fr.lower()):
            return i
    raise g.RestoreError("unknown effect %r (see: python gk600_lighting.py list)" % name)


def payload(effect, color, brightness, speed, direction, multicolour):
    if not 0 <= effect < len(EFFECTS):
        raise g.RestoreError("effect must be 0 to %d" % (len(EFFECTS) - 1))
    if not (1 <= brightness <= 5 and 1 <= speed <= 5 and 0 <= direction <= 3):
        raise g.RestoreError("brightness and speed 1 to 5, direction 0 to 3")
    if len(color) != 3 or not all(0 <= c <= 255 for c in color):
        raise g.RestoreError("colour: three values from 0 to 255")
    p = bytearray(64)
    p[0] = effect
    if effect:
        p[1:4] = bytes(color)
        p[8] = 1 if multicolour else 0
        p[9] = brightness
        p[10] = speed
        p[11] = direction
    p[14:16] = b"\xaa\x55"
    return bytes(p)


def _acked(r, op):
    return len(r) >= 4 and r[0] == 0x04 and r[1] == op and r[3] == 0x01


def set_lighting(t, effect, color, brightness, speed, direction, multicolour, log=print):
    """Sends one lighting setting. Raises RestoreError when the keyboard does not acknowledge."""
    data = payload(effect, color, brightness, speed, direction, multicolour)
    r = g.command(t, 0x18, log=log)
    if not _acked(r, 0x18):
        raise g.RestoreError("the keyboard is busy (reply %s): switch it off and on, then try again"
                             % r[:8].hex(" "))
    r = g.command(t, LIGHT_BLOCK, 0, 1, log=log)
    if not _acked(r, LIGHT_BLOCK):
        g.command(t, 0x02, log=log)
        raise g.RestoreError("lighting block refused (reply %s)" % r[:8].hex(" "))
    t.sleep(g.CMD_DELAY)
    t.set_feature(data)
    t.sleep(g.CMD_DELAY)
    echo = bytes(t.get_feature())
    if log:
        log("  -> %s" % data[:16].hex(" "))
        log("  <- %s" % echo[:16].hex(" "))
    r = g.command(t, 0x02, log=log)
    if not _acked(r, 0x02):
        raise g.RestoreError("lighting not applied (reply %s)" % r[:8].hex(" "))
    if echo[:16] != data[:16]:
        log("  note: the echo differs from what was sent")
    return data


def _color(text):
    s = text.strip().lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError("colour as RRGGBB, e.g. ff0000")
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        raise argparse.ArgumentTypeError("colour as RRGGBB, e.g. ff0000")


def main(argv=None):
    ap = argparse.ArgumentParser(description="GK600 TKL lighting (experimental)")
    ap.add_argument("effect", help="effect name or number, or 'list'")
    ap.add_argument("--color", type=_color, default="ff0000", help="RRGGBB (default ff0000)")
    ap.add_argument("--multicolour", action="store_true", help="all colours instead of one")
    ap.add_argument("--brightness", type=int, default=DEFAULT["brightness"], help="1 to 5")
    ap.add_argument("--speed", type=int, default=DEFAULT["speed"], help="1 to 5")
    ap.add_argument("--direction", type=int, default=DEFAULT["direction"], help="0 to 3")
    args = ap.parse_args(argv)
    if args.effect == "list":
        for i, (key, en, fr) in enumerate(EFFECTS):
            print("%2d  %-11s %-11s %s" % (i, key, en, fr))
        return 0
    try:
        effect = int(args.effect) if args.effect.isdigit() else effect_index(args.effect)
        info = g.select_keyboard(print)
        t = g.HidTransport(info)
        try:
            set_lighting(t, effect, args.color, args.brightness, args.speed, args.direction,
                         args.multicolour)
        finally:
            t.close()
        print("Done: %s" % EFFECTS[effect][1])
        return 0
    except g.RestoreError as e:
        print("ERROR: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())

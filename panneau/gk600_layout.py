"""
gk600_layout.py - the keys of the MSI Forge GK600 TKL Wireless, for the panel's keyboard pictures,
and the lists of functions a key can be given.

Key numbers ("idx") are the keyboard's own numbers for keys and LEDs: MSI's software uses the same
number for a key and for its LED (layouts/rgb-keyboard.xml of MSI's driver 1.0.0.8, attributes
key_index and light_index). That file only draws the US (ANSI) layout. The ISO numbers come from
the key matrix of the Frieren V1.17 firmware (MSI FORGE TKL FRIEREN EDITION, same family): 110 for
the key left of the ISO Enter (* and µ on AZERTY) and 111 for the < > key next to the left Shift.

Two keys have two candidate numbers, and the panel writes the same setting to both (the one that
has no key on the keyboard is never used):
- Home: 117 in MSI's file, 113 in the Frieren V1.17 matrix at the same place;
- the * µ key of the ISO layout: 110 in the Frieren matrix, while MSI's own French lighting
  profile colours it through the US backslash entry (67). The panel calls it 67, like the US
  backslash that sits at the same end of the row, and writes 110 too.
The < > key (111) has no second number; it was confirmed on a V1.20 (its LED and its key).

Positions are in key units (1 = one key), for drawing only.
"""

HOME_ALT = 113          # second number written for Home (see above)
ISO_HASH_ALT = 110      # second number written for the ISO * µ key (see above)
ALT = {117: HOME_ALT, 67: ISO_HASH_ALT}   # key number -> second number
_CANON = {v: k for k, v in ALT.items()}

# id, idx, default HID usage, x, y, width, height, layouts, US legend, French legend
_KEYS = [
    # row 0
    ("esc", 1, 0x29, 0, 0, 1, 1, "*", "Esc", "Échap"),
    ("f1", 2, 0x3A, 2, 0, 1, 1, "*", "F1", "F1"), ("f2", 3, 0x3B, 3, 0, 1, 1, "*", "F2", "F2"),
    ("f3", 4, 0x3C, 4, 0, 1, 1, "*", "F3", "F3"), ("f4", 5, 0x3D, 5, 0, 1, 1, "*", "F4", "F4"),
    ("f5", 6, 0x3E, 6.5, 0, 1, 1, "*", "F5", "F5"), ("f6", 7, 0x3F, 7.5, 0, 1, 1, "*", "F6", "F6"),
    ("f7", 8, 0x40, 8.5, 0, 1, 1, "*", "F7", "F7"), ("f8", 9, 0x41, 9.5, 0, 1, 1, "*", "F8", "F8"),
    ("f9", 10, 0x42, 11, 0, 1, 1, "*", "F9", "F9"), ("f10", 11, 0x43, 12, 0, 1, 1, "*", "F10", "F10"),
    ("f11", 12, 0x44, 13, 0, 1, 1, "*", "F11", "F11"), ("f12", 13, 0x45, 14, 0, 1, 1, "*", "F12", "F12"),
    # row 1
    ("grave", 19, 0x35, 0, 1.25, 1, 1, "*", "`", "²"),
    ("1", 20, 0x1E, 1, 1.25, 1, 1, "*", "1", "1 &"), ("2", 21, 0x1F, 2, 1.25, 1, 1, "*", "2", "2 é"),
    ("3", 22, 0x20, 3, 1.25, 1, 1, "*", "3", "3 \""), ("4", 23, 0x21, 4, 1.25, 1, 1, "*", "4", "4 '"),
    ("5", 24, 0x22, 5, 1.25, 1, 1, "*", "5", "5 ("), ("6", 25, 0x23, 6, 1.25, 1, 1, "*", "6", "6 -"),
    ("7", 26, 0x24, 7, 1.25, 1, 1, "*", "7", "7 è"), ("8", 27, 0x25, 8, 1.25, 1, 1, "*", "8", "8 _"),
    ("9", 28, 0x26, 9, 1.25, 1, 1, "*", "9", "9 ç"), ("0", 29, 0x27, 10, 1.25, 1, 1, "*", "0", "0 à"),
    ("minus", 30, 0x2D, 11, 1.25, 1, 1, "*", "-", "° )"), ("equal", 31, 0x2E, 12, 1.25, 1, 1, "*", "=", "+ ="),
    ("backspace", 103, 0x2A, 13, 1.25, 2, 1, "*", "Backspace", "Retour"),
    ("insert", 116, 0x49, 15.5, 1.25, 1, 1, "*", "Ins", "Inser"),
    ("home", 117, 0x4A, 16.5, 1.25, 1, 1, "*", "Home", "Début"),
    # row 2
    ("tab", 37, 0x2B, 0, 2.25, 1.5, 1, "*", "Tab", "Tab"),
    ("q", 38, 0x14, 1.5, 2.25, 1, 1, "*", "Q", "A"), ("w", 39, 0x1A, 2.5, 2.25, 1, 1, "*", "W", "Z"),
    ("e", 40, 0x08, 3.5, 2.25, 1, 1, "*", "E", "E"), ("r", 41, 0x15, 4.5, 2.25, 1, 1, "*", "R", "R"),
    ("t", 42, 0x17, 5.5, 2.25, 1, 1, "*", "T", "T"), ("y", 43, 0x1C, 6.5, 2.25, 1, 1, "*", "Y", "Y"),
    ("u", 44, 0x18, 7.5, 2.25, 1, 1, "*", "U", "U"), ("i", 45, 0x0C, 8.5, 2.25, 1, 1, "*", "I", "I"),
    ("o", 46, 0x12, 9.5, 2.25, 1, 1, "*", "O", "O"), ("p", 47, 0x13, 10.5, 2.25, 1, 1, "*", "P", "P"),
    ("lbracket", 48, 0x2F, 11.5, 2.25, 1, 1, "*", "[", "¨ ^"),
    ("rbracket", 49, 0x30, 12.5, 2.25, 1, 1, "*", "]", "£ $"),
    ("backslash", 67, 0x31, 13.5, 2.25, 1.5, 1, "ansi", "\\", "µ *"),
    ("delete", 119, 0x4C, 15.5, 2.25, 1, 1, "*", "Del", "Suppr"),
    ("end", 120, 0x4D, 16.5, 2.25, 1, 1, "*", "End", "Fin"),
    # row 3
    ("caps", 55, 0x39, 0, 3.25, 1.75, 1, "*", "Caps Lock", "Verr. Maj"),
    ("a", 56, 0x04, 1.75, 3.25, 1, 1, "*", "A", "Q"), ("s", 57, 0x16, 2.75, 3.25, 1, 1, "*", "S", "S"),
    ("d", 58, 0x07, 3.75, 3.25, 1, 1, "*", "D", "D"), ("f", 59, 0x09, 4.75, 3.25, 1, 1, "*", "F", "F"),
    ("g", 60, 0x0A, 5.75, 3.25, 1, 1, "*", "G", "G"), ("h", 61, 0x0B, 6.75, 3.25, 1, 1, "*", "H", "H"),
    ("j", 62, 0x0D, 7.75, 3.25, 1, 1, "*", "J", "J"), ("k", 63, 0x0E, 8.75, 3.25, 1, 1, "*", "K", "K"),
    ("l", 64, 0x0F, 9.75, 3.25, 1, 1, "*", "L", "L"),
    ("semicolon", 65, 0x33, 10.75, 3.25, 1, 1, "*", ";", "M"),
    ("quote", 66, 0x34, 11.75, 3.25, 1, 1, "*", "'", "% ù"),
    ("iso_hash", 67, 0x32, 12.75, 3.25, 1, 1, "iso", "#", "µ *"),
    ("enter", 85, 0x28, 12.75, 3.25, 2.25, 1, "ansi", "Enter", "Entrée"),
    ("enter", 85, 0x28, 13.5, 2.25, 1.5, 2, "iso", "Enter", "Entrée"),
    ("pgup", 118, 0x4B, 15.5, 3.25, 1, 1, "*", "PgUp", "Pg préc"),
    ("pgdn", 121, 0x4E, 16.5, 3.25, 1, 1, "*", "PgDn", "Pg suiv"),
    # row 4
    ("lshift", 73, 0xE1, 0, 4.25, 2.25, 1, "ansi", "Shift", "Maj"),
    ("lshift", 73, 0xE1, 0, 4.25, 1.25, 1, "iso", "Shift", "Maj"),
    ("iso_lt", 111, 0x64, 1.25, 4.25, 1, 1, "iso", "\\", "> <"),
    ("z", 74, 0x1D, 2.25, 4.25, 1, 1, "*", "Z", "W"), ("x", 75, 0x1B, 3.25, 4.25, 1, 1, "*", "X", "X"),
    ("c", 76, 0x06, 4.25, 4.25, 1, 1, "*", "C", "C"), ("v", 77, 0x19, 5.25, 4.25, 1, 1, "*", "V", "V"),
    ("b", 78, 0x05, 6.25, 4.25, 1, 1, "*", "B", "B"), ("n", 79, 0x11, 7.25, 4.25, 1, 1, "*", "N", "N"),
    ("m", 80, 0x10, 8.25, 4.25, 1, 1, "*", "M", "? ,"), ("comma", 81, 0x36, 9.25, 4.25, 1, 1, "*", ",", ". ;"),
    ("period", 82, 0x37, 10.25, 4.25, 1, 1, "*", ".", "/ :"), ("slash", 83, 0x38, 11.25, 4.25, 1, 1, "*", "/", "§ !"),
    ("rshift", 84, 0xE5, 12.25, 4.25, 2.75, 1, "*", "Shift", "Maj"),
    ("up", 101, 0x52, 15.5, 4.25, 1, 1, "*", "↑", "↑"),
    # row 5
    ("lctrl", 91, 0xE0, 0, 5.25, 1.25, 1, "*", "Ctrl", "Ctrl"),
    ("lwin", 92, 0xE3, 1.25, 5.25, 1.25, 1, "*", "Win", "Win"),
    ("lalt", 93, 0xE2, 2.5, 5.25, 1.25, 1, "*", "Alt", "Alt"),
    ("space", 94, 0x2C, 3.75, 5.25, 6.25, 1, "*", "Space", "Espace"),
    ("ralt", 95, 0xE6, 10, 5.25, 1.25, 1, "*", "Alt", "Alt Gr"),
    ("fn", 96, 0, 11.25, 5.25, 1.25, 1, "*", "Fn", "Fn"),
    ("rctrl", 98, 0xE4, 12.5, 5.25, 1.25, 1, "*", "Ctrl", "Ctrl"),
    ("left", 99, 0x50, 14.5, 5.25, 1, 1, "*", "←", "←"),
    ("down", 100, 0x51, 15.5, 5.25, 1, 1, "*", "↓", "↓"),
    ("right", 102, 0x4F, 16.5, 5.25, 1, 1, "*", "→", "→"),
]

LAYOUTS = ("iso", "ansi")
NOT_REMAPPABLE = {96}            # Fn: the keyboard needs it to reach its own functions


def keys(layout="iso"):
    """Keys of one physical layout, as dictionaries."""
    if layout not in LAYOUTS:
        raise ValueError("unknown layout")
    out = []
    for k in _KEYS:
        kid, idx, code, x, y, w, h, where, us, fr = k
        if where not in ("*", layout):
            continue
        out.append({"id": kid, "idx": idx, "code": code, "x": x, "y": y, "w": w, "h": h,
                    "shape": "iso-enter" if (kid == "enter" and layout == "iso") else "",
                    "us": us, "fr": fr, "remap": idx not in NOT_REMAPPABLE})
    return out


def all_indexes():
    """Every key number the panel may write (both layouts, plus the second numbers)."""
    return sorted({k[1] for k in _KEYS} | set(ALT.values()))


def canonical(idx):
    """The number the panel uses for a key, if idx is a second number."""
    return _CANON.get(idx, idx)


def mirrors(idx):
    """Numbers written together for one key."""
    idx = canonical(idx)
    return (idx, ALT[idx]) if idx in ALT else (idx,)


def fold(table):
    """{number: value} read from the keyboard -> second numbers folded into the panel's numbers."""
    out = dict(table)
    for idx, alt in ALT.items():
        if alt in out and idx not in out:
            out[idx] = out[alt]
        out.pop(alt, None)
    return out


# ---------------------------------------------------------------- what a key can do
# Keyboard usages offered in the key editor (HID usage page 7), with US and French names.
# Letters and symbols use the character printed on the key, by layout.
USAGES = [
    (0x04, "A", "Q"), (0x05, "B", "B"), (0x06, "C", "C"), (0x07, "D", "D"), (0x08, "E", "E"),
    (0x09, "F", "F"), (0x0A, "G", "G"), (0x0B, "H", "H"), (0x0C, "I", "I"), (0x0D, "J", "J"),
    (0x0E, "K", "K"), (0x0F, "L", "L"), (0x10, "M", ","), (0x11, "N", "N"), (0x12, "O", "O"),
    (0x13, "P", "P"), (0x14, "Q", "A"), (0x15, "R", "R"), (0x16, "S", "S"), (0x17, "T", "T"),
    (0x18, "U", "U"), (0x19, "V", "V"), (0x1A, "W", "Z"), (0x1B, "X", "X"), (0x1C, "Y", "Y"),
    (0x1D, "Z", "W"),
    (0x1E, "1", "1 &"), (0x1F, "2", "2 é"), (0x20, "3", "3 \""), (0x21, "4", "4 '"), (0x22, "5", "5 ("),
    (0x23, "6", "6 -"), (0x24, "7", "7 è"), (0x25, "8", "8 _"), (0x26, "9", "9 ç"), (0x27, "0", "0 à"),
    (0x28, "Enter", "Entrée"), (0x29, "Esc", "Échap"), (0x2A, "Backspace", "Retour arrière"),
    (0x2B, "Tab", "Tab"), (0x2C, "Space", "Espace"), (0x2D, "-", "° )"), (0x2E, "=", "+ ="),
    (0x2F, "[", "¨ ^"), (0x30, "]", "£ $"), (0x31, "\\", "µ *"), (0x32, "# (ISO)", "µ * (ISO)"),
    (0x33, ";", "M"), (0x34, "'", "% ù"), (0x35, "`", "²"), (0x36, ",", ". ;"), (0x37, ".", "/ :"),
    (0x38, "/", "§ !"), (0x39, "Caps Lock", "Verr. Maj"),
    (0x3A, "F1", "F1"), (0x3B, "F2", "F2"), (0x3C, "F3", "F3"), (0x3D, "F4", "F4"), (0x3E, "F5", "F5"),
    (0x3F, "F6", "F6"), (0x40, "F7", "F7"), (0x41, "F8", "F8"), (0x42, "F9", "F9"), (0x43, "F10", "F10"),
    (0x44, "F11", "F11"), (0x45, "F12", "F12"),
    (0x46, "Print Screen", "Impr. écran"), (0x47, "Scroll Lock", "Arrêt défil"), (0x48, "Pause", "Pause"),
    (0x49, "Insert", "Inser"), (0x4A, "Home", "Début"), (0x4B, "Page Up", "Page préc."),
    (0x4C, "Delete", "Suppr"), (0x4D, "End", "Fin"), (0x4E, "Page Down", "Page suiv."),
    (0x4F, "→", "→"), (0x50, "←", "←"), (0x51, "↓", "↓"), (0x52, "↑", "↑"),
    (0x53, "Num Lock", "Verr. Num"), (0x54, "Num /", "Pavé /"), (0x55, "Num *", "Pavé *"),
    (0x56, "Num -", "Pavé -"), (0x57, "Num +", "Pavé +"), (0x58, "Num Enter", "Pavé Entrée"),
    (0x59, "Num 1", "Pavé 1"), (0x5A, "Num 2", "Pavé 2"), (0x5B, "Num 3", "Pavé 3"), (0x5C, "Num 4", "Pavé 4"),
    (0x5D, "Num 5", "Pavé 5"), (0x5E, "Num 6", "Pavé 6"), (0x5F, "Num 7", "Pavé 7"), (0x60, "Num 8", "Pavé 8"),
    (0x61, "Num 9", "Pavé 9"), (0x62, "Num 0", "Pavé 0"), (0x63, "Num .", "Pavé ."),
    (0x64, "\\ (ISO)", "< > (ISO)"), (0x65, "Menu", "Menu"),
    (0x68, "F13", "F13"), (0x69, "F14", "F14"), (0x6A, "F15", "F15"), (0x6B, "F16", "F16"), (0x6C, "F17", "F17"),
    (0x6D, "F18", "F18"), (0x6E, "F19", "F19"), (0x6F, "F20", "F20"), (0x70, "F21", "F21"), (0x71, "F22", "F22"),
    (0x72, "F23", "F23"), (0x73, "F24", "F24"),
    (0xE0, "Left Ctrl", "Ctrl gauche"), (0xE1, "Left Shift", "Maj gauche"), (0xE2, "Left Alt", "Alt"),
    (0xE3, "Left Win", "Win gauche"), (0xE4, "Right Ctrl", "Ctrl droite"), (0xE5, "Right Shift", "Maj droite"),
    (0xE6, "Right Alt", "Alt Gr"), (0xE7, "Right Win", "Win droite"),
]
USAGE_CODES = {u for u, _, _ in USAGES}

# Modifier bits of the second byte of a key entry (HID boot-keyboard order).
MODS = [(0x01, "Ctrl", "Ctrl"), (0x02, "Shift", "Maj"), (0x04, "Alt", "Alt"), (0x08, "Win", "Win"),
        (0x10, "Right Ctrl", "Ctrl droite"), (0x20, "Right Shift", "Maj droite"),
        (0x40, "Right Alt", "Alt Gr"), (0x80, "Right Win", "Win droite")]

# Consumer usages (HID page 0x0C): the list of MSI's software (DeviceDriver.exe), same codes.
MEDIA = [
    (0xCD, "Play / Pause", "Lecture / Pause"), (0xB7, "Stop", "Arrêt"),
    (0xB6, "Previous track", "Piste précédente"), (0xB5, "Next track", "Piste suivante"),
    (0xE9, "Volume +", "Volume +"), (0xEA, "Volume -", "Volume -"), (0xE2, "Mute", "Muet"),
    (0x192, "Calculator", "Calculatrice"), (0x18A, "Mail", "Courrier"), (0x183, "Media player", "Lecteur multimédia"),
    (0x194, "This PC", "Ce PC"), (0x223, "Browser: home page", "Navigateur : accueil"),
    (0x224, "Browser: back", "Navigateur : précédent"), (0x225, "Browser: forward", "Navigateur : suivant"),
    (0x226, "Browser: stop", "Navigateur : arrêter"), (0x227, "Browser: refresh", "Navigateur : actualiser"),
    (0x221, "Browser: search", "Navigateur : rechercher"), (0x22A, "Browser: favourites", "Navigateur : favoris"),
]
MEDIA_CODES = {u for u, _, _ in MEDIA}

MOUSE = [("left", 0x01, "Left click", "Clic gauche"), ("right", 0x02, "Right click", "Clic droit"),
         ("middle", 0x04, "Middle click", "Clic milieu"), ("back", 0x08, "Back button (4)", "Bouton précédent (4)"),
         ("forward", 0x10, "Forward button (5)", "Bouton suivant (5)")]
WHEEL = [("up", 0x01, "Scroll up", "Molette vers le haut"), ("down", 0xFF, "Scroll down", "Molette vers le bas")]

# Ready-made shortcuts: (modifiers, usage, English, French)
SHORTCUTS = [
    (0x08, 0x07, "Show desktop (Win+D)", "Afficher le bureau (Win+D)"),
    (0x08, 0x08, "File Explorer (Win+E)", "Explorateur (Win+E)"),
    (0x08, 0x0F, "Lock the PC (Win+L)", "Verrouiller le PC (Win+L)"),
    (0x0A, 0x16, "Screenshot (Win+Shift+S)", "Capture d'écran (Win+Maj+S)"),
    (0x08, 0x19, "Clipboard history (Win+V)", "Historique du presse-papiers (Win+V)"),
    (0x08, 0x2B, "Task view (Win+Tab)", "Vue des tâches (Win+Tab)"),
    (0x04, 0x2B, "Switch windows (Alt+Tab)", "Changer de fenêtre (Alt+Tab)"),
    (0x04, 0x3D, "Close the app (Alt+F4)", "Fermer l'application (Alt+F4)"),
    (0x01, 0x1A, "Close the tab (Ctrl+W)", "Fermer l'onglet (Ctrl+W)"),
    (0x03, 0x29, "Task Manager (Ctrl+Shift+Esc)", "Gestionnaire des tâches (Ctrl+Maj+Échap)"),
    (0x01, 0x06, "Copy (Ctrl+C)", "Copier (Ctrl+C)"),
    (0x01, 0x19, "Paste (Ctrl+V)", "Coller (Ctrl+V)"),
    (0x01, 0x1B, "Cut (Ctrl+X)", "Couper (Ctrl+X)"),
    (0x01, 0x1D, "Undo (Ctrl+Z)", "Annuler (Ctrl+Z)"),
]

MACRO_MODES = [(0, "Play once", "Une fois"), (1, "Repeat N times", "N fois"),
               (2, "Repeat until pressed again", "En boucle jusqu'au prochain appui"),
               (3, "Repeat while held", "En boucle tant que la touche est enfoncée")]


def catalog():
    """Everything the page needs to draw the keyboards and the key editor."""
    return {
        "layouts": {name: keys(name) for name in LAYOUTS},
        "second_numbers": {str(k): v for k, v in ALT.items()},
        "usages": [{"code": u, "us": us, "fr": fr} for u, us, fr in USAGES],
        "mods": [{"bit": b, "us": us, "fr": fr} for b, us, fr in MODS],
        "media": [{"code": u, "us": us, "fr": fr} for u, us, fr in MEDIA],
        "mouse": [{"id": i, "mask": m, "us": us, "fr": fr} for i, m, us, fr in MOUSE],
        "wheel": [{"id": i, "value": v, "us": us, "fr": fr} for i, v, us, fr in WHEEL],
        "shortcuts": [{"mods": m, "code": c, "us": us, "fr": fr} for m, c, us, fr in SHORTCUTS],
        "macro_modes": [{"mode": m, "us": us, "fr": fr} for m, us, fr in MACRO_MODES],
    }

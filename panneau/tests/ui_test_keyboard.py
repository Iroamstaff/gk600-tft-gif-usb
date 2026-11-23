#!/usr/bin/env python3
"""
ui_test_keyboard.py - drives the panel's keyboard tabs in a real browser (headless Chrome,
Playwright) against the emulated keyboard (MCU flash modelled), and saves screenshots: per-key
colours, keys (main and Fn layers), macros (recorded from the keyboard), settings, profiles.

Usage:  python -I ui_test_keyboard.py <frieren_v117.bin> "<Forge gk600 tkl wireless.bin>" <out dir> [chrome]
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.normpath(os.path.join(HERE, ".."))
RESTO = os.path.normpath(os.path.join(PANEL, "..", "restauration"))
for p in (HERE, PANEL, RESTO, os.path.join(RESTO, "tests")):
    sys.path.insert(0, p)

from playwright.sync_api import sync_playwright  # noqa: E402
import emu_backend  # noqa: E402
import gk600_config as cfg  # noqa: E402

fw_path, dump_path, out = sys.argv[1:4]
chrome = sys.argv[4] if len(sys.argv) > 4 else "/usr/bin/google-chrome"
os.makedirs(out, exist_ok=True)
emu_backend.fw = open(fw_path, "rb").read()
emu_backend.ref = open(dump_path, "rb").read()
emu, backend, panel, server = emu_backend.new_panel(flash_model=True)
url = "http://127.0.0.1:%d/" % server.port
errors, results = [], []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  [%s]" % detail) if detail and not ok else ""))


def entry(base, idx):
    return emu.iflash(base + idx * 4, 4)


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=chrome, headless=True)
    page = browser.new_page(viewport={"width": 1366, "height": 900}, locale="fr-FR")
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("dialog", lambda d: d.accept())
    shot = lambda n: page.screenshot(path=os.path.join(out, n + ".png"), full_page=True)  # noqa: E731
    wait_msg = lambda sel, txt, to=60000: page.wait_for_function(  # noqa: E731
        "([s, t]) => document.querySelector(s).textContent.includes(t)", arg=[sel, txt], timeout=to)

    page.goto(url)
    page.wait_for_function("document.querySelector('#pill-text').textContent.includes('V1.20')", timeout=15000)
    nav = page.inner_text("nav").lower()
    check("sidebar: screen and keyboard groups", nav.count("couleurs par touche") == 1 and "clavier" in nav and "écran" in nav)

    # ---------------------------------------------------------------- per-key colours
    page.click("nav button[data-tab=perkey]")
    wait_msg("#pk-msg", "Relu depuis le clavier")
    n = page.locator("#perkey-kbd .k").count()
    check("per-key: the keyboard was read, AZERTY ISO drawn (84 keys)", n == 84, str(n))
    check("per-key: AZERTY legends (A where QWERTY has Q)", page.inner_text("#perkey-kbd .k[data-id=q]") == "A")
    page.click("#pk-pal button[title='#1f5bff']")
    page.click("#pk-groups button >> text=Tout le clavier")
    page.click("#pk-pal button[title='#e2231a']")
    page.click("#pk-groups button >> text=ZQSD")
    box = page.locator("#perkey-kbd .k[data-id=f1]").bounding_box()
    box2 = page.locator("#perkey-kbd .k[data-id=f4]").bounding_box()
    page.click("#pk-pal button[title='#2bd94c']")
    page.mouse.move(box["x"] + 5, box["y"] + 5)
    page.mouse.down()
    page.mouse.move(box2["x"] + 5, box2["y"] + 5, steps=12)
    page.mouse.up()
    check("per-key: unsent changes flagged", "pas encore envoyées" in page.inner_text("#pk-dirty"))
    shot("k01_perkey_painted")
    page.click("#pk-send")
    wait_msg("#pk-msg", "relu exactement")
    check("per-key: keyboard holds WASD red, F1-F4 green, the rest blue, custom mode",
          entry(0x9C00, 39) == bytes([39, 0xE2, 0x23, 0x1A]) and entry(0x9C00, 3) == bytes([3, 0x2B, 0xD9, 0x4C])
          and entry(0x9C00, 1) == bytes([1, 0x1F, 0x5B, 0xFF]) and emu.iflash(0x9800, 1) == b"\x80",
          "%s %s %s" % (entry(0x9C00, 39).hex(), entry(0x9C00, 3).hex(), entry(0x9C00, 1).hex()))
    check("per-key: the ISO keys are coloured too (* µ under 67 and 110, < > under 111)",
          entry(0x9C00, 67) == bytes([67, 0x1F, 0x5B, 0xFF]) and entry(0x9C00, 110) == bytes([110, 0x1F, 0x5B, 0xFF])
          and entry(0x9C00, 111) == bytes([111, 0x1F, 0x5B, 0xFF]))
    page.click("nav button[data-tab=light]")
    check("lighting tab now shows the per-key mode", page.input_value("#effect") == "custom"
          and page.is_hidden("#color"))
    shot("k02_light_custom")

    # ---------------------------------------------------------------- keys
    page.click("nav button[data-tab=keys]")
    wait_msg("#keys-msg", "Relu depuis le clavier")
    page.click("#keys-kbd .k[data-id=caps]")
    page.click("#key-editor .types button >> text=Touche / raccourci")
    page.click("#capture-box")
    page.keyboard.down("Control")
    page.keyboard.press("KeyC")
    page.keyboard.up("Control")
    check("keys: capture of Ctrl+C", page.inner_text("#capture-box") == "Ctrl+C", page.inner_text("#capture-box"))
    page.click("#ed-apply")
    page.click("#keys-kbd .k[data-id=f12]")
    page.click("#key-editor .types button >> text=Multimédia")
    page.select_option("#key-editor select", str(0xE2))
    page.click("#ed-apply")
    page.click("#keys-kbd .k[data-id=rctrl]")
    page.click("#key-editor .types button >> text=Souris")
    page.select_option("#key-editor select", "m:right")
    page.click("#ed-apply")
    page.click("#keys-kbd .k[data-id=insert]")
    page.click("#key-editor .types button >> text=Désactivée")
    page.click("#ed-apply")
    check("keys: changed keys show their new job", "Ctrl+C" in page.inner_text("#keys-kbd .k[data-id=caps]")
          and "Muet" in page.inner_text("#keys-kbd .k[data-id=f12]"))
    check("keys: Fn cannot be selected", "fixed" in page.get_attribute("#keys-kbd .k[data-id=fn]", "class"))
    shot("k03_keys_main")
    page.click("#keys-send")
    wait_msg("#keys-msg", "relu exactement")
    check("keys: main layer in the keyboard", entry(0x9400, 55).hex() == "02010600" and entry(0x9400, 13).hex() == "03e20000"
          and entry(0x9400, 98).hex() == "01010200" and entry(0x9400, 116).hex() == "05030000",
          "%s %s %s %s" % (entry(0x9400, 55).hex(), entry(0x9400, 13).hex(), entry(0x9400, 98).hex(), entry(0x9400, 116).hex()))
    page.click("#layer-seg button[data-layer=fn]")
    page.click("#keys-kbd .k[data-id=f5]")
    page.click("#key-editor .types button >> text=Touche / raccourci")
    page.select_option("#key-editor select.wide-select >> nth=1", "3")   # ready-made: Win+Shift+S
    page.click("#ed-apply")
    page.click("#keys-send")
    wait_msg("#keys-msg", "relu exactement")
    check("keys: Fn layer, Fn+F5 = Win+Shift+S", entry(0xAC00, 6).hex() == "020a1600", entry(0xAC00, 6).hex())
    shot("k04_keys_fn")

    # ---------------------------------------------------------------- macros
    page.click("nav button[data-tab=macros]")
    wait_msg("#macros-msg", "Relu depuis le clavier")
    page.click("#macro-new")
    page.fill("#macro-editor input[type=text]", "Bonjour")
    page.click("#rec-btn")
    page.keyboard.type("ok")
    page.click("#rec-btn")
    steps = [s for s in panel.state.data.get("x", [])]  # noqa: F841 (page-side only)
    lbl = page.inner_text("#steps-list")
    check("macros: recorded from the keyboard (O down/up, K down/up, pauses)", lbl.count("Appuie") == 2 and lbl.count("Relâche") == 2
          and lbl.count("Pause") == 3, lbl)
    page.click("#macro-editor .addrow >> nth=3 >> button >> text=Clic")
    page.click("#macros-send")
    wait_msg("#macros-msg", "relu exactement")
    pm = cfg.parse_macros(emu.iflash(0xA000, 3072))
    check("macros: keyboard holds M1 (o, k, left click)", pm and [s["t"] for s in pm[0]["steps"] if s["t"] != "delay"] ==
          ["down", "up", "down", "up", "mdown", "mup"] and pm[0]["steps"][0]["code"] == 0x12, str(pm)[:200])
    shot("k05_macros")
    page.click("nav button[data-tab=keys]")
    page.click("#layer-seg button[data-layer=main]")
    page.click("#keys-kbd .k[data-id=f6]")
    page.click("#key-editor .types button >> text=Macro")
    page.click("#ed-apply")
    page.click("#keys-send")
    wait_msg("#keys-msg", "relu exactement")
    check("keys: F6 plays macro M1 once", entry(0x9400, 7).hex() == "06000001", entry(0x9400, 7).hex())

    # ---------------------------------------------------------------- settings
    page.click("nav button[data-tab=settings]")
    wait_msg("#settings-msg", "Relu depuis le clavier")
    check("settings: factory values shown (5 min, level 2)", page.inner_text("#set-sleep button.on") == "5 min"
          and page.input_value("#set-debounce") == "2")
    page.check("#set-no-win")
    page.click("#set-sleep button >> text=30 min")
    page.click("#set-fn button >> text=Bascule")
    page.eval_on_selector("#set-debounce", "e => { e.value = '3'; e.dispatchEvent(new Event('input')); }")
    page.click("#settings-send")
    wait_msg("#settings-msg", "relu exactement")
    check("settings: keyboard holds Win lock, Fn toggle, 30 min, level 3", emu.iflash(0x9000, 9).hex() == "000000000101030003",
          emu.iflash(0x9000, 9).hex())
    check("settings: no clock button (the TKL screen never draws the clock)", page.locator("#clock-go").count() == 0)
    shot("k06_settings")

    # ---------------------------------------------------------------- profiles
    page.click("nav button[data-tab=profiles]")
    page.wait_for_selector("#prof-list .prof", timeout=15000)
    check("profiles: the session backup is listed", "sauvegarde automatique" in page.inner_text("#prof-list"))
    page.fill("#prof-name", "Jeux")
    page.click("#prof-save")
    wait_msg("#prof-msg", "Profil enregistré")
    page.wait_for_function("document.querySelector('#prof-list').textContent.includes('Jeux')", timeout=10000)
    shot("k07_profiles")
    with page.expect_download() as dl:
        page.click("#prof-list .prof:has-text('Jeux') button >> text=Exporter")
    exported = json.load(open(dl.value.path(), encoding="utf-8"))
    check("profiles: export is a GK600 profile with every part", exported.get("format") == "gk600-profile"
          and all(exported.get(k) is not None for k in ("keys", "fnkeys", "colours", "lighting", "macros", "settings")),
          str(list(exported)))
    page.click("#prof-list .prof:has-text('sauvegarde automatique') button >> text=Appliquer au clavier")
    wait_msg("#prof-msg", "Profil appliqué")
    check("profiles: the backup put the factory keys and settings back", emu.iflash(0x9400, 574) == bytes(574)
          and emu.iflash(0x9000, 9).hex() == "000000000000020002", emu.iflash(0x9000, 9).hex())
    page.click("#prof-list .prof:has-text('Jeux') button >> text=Appliquer au clavier")
    wait_msg("#prof-msg", "Profil appliqué")
    check("profiles: 'Jeux' applied again", entry(0x9400, 55).hex() == "02010600" and entry(0xAC00, 6).hex() == "020a1600")

    # ---------------------------------------------------------------- English, QWERTY, narrow
    page.click(".lang button[data-lang=en]")
    page.click(".kbdlayout button[data-kl=us]")
    page.click("nav button[data-tab=keys]")
    n = page.locator("#keys-kbd .k").count()
    check("QWERTY ANSI drawn (83 keys), English titles", n == 83 and page.inner_text("#title") == "Keys"
          and page.inner_text("#keys-kbd .k[data-id=q]").startswith("Q"))
    shot("k08_keys_english_qwerty")
    page.set_viewport_size({"width": 800, "height": 900})
    page.click("nav button[data-tab=perkey]")
    time.sleep(0.5)
    shot("k09_narrow")
    w = page.locator("#perkey-kbd").bounding_box()["width"]
    right = max(page.locator("#perkey-kbd .k").nth(i).bounding_box()["x"] + page.locator("#perkey-kbd .k").nth(i).bounding_box()["width"]
                for i in range(page.locator("#perkey-kbd .k").count()))
    check("narrow window: the keyboard still fits", right <= page.locator("#perkey-kbd").bounding_box()["x"] + w + 2)
    backend.conf = ["DeviceDriver.exe"]
    page.wait_for_function("document.querySelector('#pk-send').disabled", timeout=15000)
    check("MSI software open: keyboard buttons disabled", page.is_disabled("#pk-send") and page.is_disabled("#settings-send"))
    backend.conf = []
    browser.close()

server.shutdown()
check("no JavaScript error in the page", not errors, "; ".join(errors[:5]))
check("screen flash (SPI) never touched", not emu.flash.ops)
print("%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)

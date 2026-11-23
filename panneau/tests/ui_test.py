#!/usr/bin/env python3
"""
ui_test.py - drives the panel's page in a real browser (headless Chrome, Playwright) against the
emulated keyboard, and saves screenshots: GIF, lighting, home picture with the restart step, boot
animation, repair, about, English, MSI software open.

Usage:  python -I ui_test.py <frieren_v117.bin> "<Forge gk600 tkl wireless.bin>" <anim.gif> <picture.png> <out dir> [chrome]
"""

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

fw_path, dump_path, anim, pic, out = sys.argv[1:6]
chrome = sys.argv[6] if len(sys.argv) > 6 else "/usr/bin/google-chrome"
os.makedirs(out, exist_ok=True)
emu_backend.fw = open(fw_path, "rb").read()
emu_backend.ref = open(dump_path, "rb").read()
emu, backend, panel, server = emu_backend.new_panel()
url = "http://127.0.0.1:%d/" % server.port
errors, results = [], []


def check(name, ok):
    results.append(ok)
    print("%s  %s" % ("PASS" if ok else "FAIL", name))


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=chrome, headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 860}, locale="fr-FR")
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    shot = lambda n: page.screenshot(path=os.path.join(out, n + ".png"), full_page=True)  # noqa: E731

    page.goto(url)
    page.wait_for_function("document.querySelector('#pill-text').textContent.includes('V1.20')", timeout=15000)
    check("status pill shows the keyboard and its firmware", "V1.20" in page.inner_text("#pill-text"))
    check("French by default for a French browser", page.inner_text("#title") == "GIF de l'écran")
    shot("01_gif_empty")

    page.set_input_files("#tab-gif input[type=file]", anim)
    page.wait_for_selector("#gif-screen img", timeout=60000)
    check("GIF preview shown, facts listed", "Images" in page.inner_text("#gif-facts"))
    shot("02_gif_preview")
    page.click("#gif-go")
    page.wait_for_selector("#job-result.result.ok", timeout=300000)
    check("GIF sent: success message", "l'écran joue ton GIF" in page.inner_text("#job-result"))
    shot("03_gif_done")
    page.click("#job-close")

    page.click("nav button[data-tab=light]")
    page.select_option("#effect", "1")
    page.eval_on_selector("#color", "e => { e.value = '#00a0ff'; e.dispatchEvent(new Event('input')); }")
    page.click("#light-go")
    page.wait_for_function("document.querySelector('#light-msg').textContent.length > 0", timeout=30000)
    check("lighting applied", page.inner_text("#light-msg") == "Appliqué.")
    ram = bytes(emu.rb(0x20002980, 8))
    check("lighting reached the firmware (colour 00 a0 ff)", bytes([0x00, 0xA0, 0xFF]) in ram)
    shot("04_light")

    page.click("nav button[data-tab=home]")
    page.set_input_files("#tab-home input[type=file]", pic)
    page.wait_for_selector("#home-screen img", timeout=60000)
    shot("05_home_preview")
    page.click("#home-go")
    page.wait_for_function("document.querySelector('#job-howto').textContent.includes('débranche le câble')", timeout=30000)
    check("restart instructions shown before writing", "Redémarre le clavier" in page.inner_text("#job-howto"))
    shot("06_home_restart")
    backend.present = False
    page.wait_for_function("document.querySelector('#job-howto').textContent.includes('Clavier débranché')", timeout=30000)
    shot("07_home_unplugged")
    backend.present = True
    page.wait_for_selector("#job-progress:not(.hidden)", timeout=60000)
    time.sleep(2)
    shot("08_home_writing")
    page.wait_for_selector("#job-result.result.ok", timeout=600000)
    check("home picture written", "redessine l'écran d'accueil" in page.inner_text("#job-result"))
    shot("09_home_done")
    page.click("#job-close")

    page.click("nav button[data-tab=boot]")
    page.check("#boot-fill")
    page.set_input_files("#tab-boot input[type=file]", anim)
    page.wait_for_selector("#boot-screen img", timeout=60000)
    page.wait_for_function("!document.querySelector('#keep-home').disabled", timeout=10000)
    check("boot animation offers to keep the home picture", page.is_checked("#keep-home"))
    shot("10_boot_preview")

    page.click("nav button[data-tab=repair]")
    shot("11_repair")
    page.click("nav button[data-tab=about]")
    page.click("#show-log")
    shot("12_about")

    page.click(".lang button[data-lang=en]")
    page.click("nav button[data-tab=gif]")
    check("English switch", page.inner_text("#title") == "Screen GIF")
    shot("13_gif_english")

    backend.conf = ["DeviceDriver.exe"]
    page.wait_for_function("!document.querySelector('#banner').classList.contains('hidden')", timeout=15000)
    check("MSI software open: banner and buttons disabled", page.is_disabled("#gif-go"))
    shot("14_conflict")
    backend.conf = []

    page.set_viewport_size({"width": 760, "height": 900})
    page.click(".lang button[data-lang=fr]")
    time.sleep(2)
    shot("15_narrow")
    browser.close()

server.shutdown()
check("no JavaScript error in the page", not errors)
if errors:
    print("\n".join(errors[:10]))
print("%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)

# MSI Forge GK600 TKL — Upload custom GIFs over USB (official software fix)

The **MSI Forge GK600 TKL Wireless** has a small TFT screen. MSI markets it as "no software needed" — you only get the pre-loaded animations you can cycle through from the keyboard. In fact, MSI's own driver lets you **upload your own GIFs** to the screen and set **per-key RGB** — but out of the box it **won't detect the keyboard over USB**. This repo documents the one-line fix.

**No flashing. No firmware changes. Fully reversible.**

---

## TL;DR — the fix

MSI's driver matches the keyboard by its USB **product name**. The `config.xml` shipped with the driver looks for the **wrong name** in USB mode, so the keyboard is never recognized (2.4G works because the name it looks for there happens to be a correct prefix of the real one).

In the driver's `config.xml`, find the `desc="USB"` line and fix `product_name`:

```diff
- <mode value="0" desc="USB" vid="0DB0" pid="EA47" product_name="MSI FORGE GK600 GAMING KEYBOARD" hid_interface="VID_0DB0&PID_EA47&MI_00"/>
+ <mode value="0" desc="USB" vid="0DB0" pid="EA47" product_name="MSI FORGE GK600 TKL WIRELESS Keyboard" hid_interface="VID_0DB0&PID_EA47&MI_00"/>
```

Leave `hid_interface` on `MI_00` — the driver switches to the right channel on its own. Save, plug the keyboard in **wired mode**, launch the driver. Done.

> The product string can vary by unit/firmware revision. If it still isn't detected, read your own keyboard's string and copy it verbatim (see full guide).

---

## Steps

1. **Download** `MSI-FORGE-GK600-Driver-1.0.0.8.zip` from msi.com → Support → *FORGE GK600 TKL WIRELESS* → Download. (Do **not** use MSI Center — it doesn't see the screen. The tool you want is `DeviceDriver.exe` inside the package.)
2. **Install**, then copy the install folder somewhere writable (e.g. Desktop) to avoid Program Files permission issues.
3. **Edit** `config.xml` as shown in the TL;DR. Back it up first.
4. Set the keyboard's 3-way switch to **wired/USB**, connect the USB-C cable.
5. Run **`DeviceDriver.exe`** → the keyboard is detected.
6. **GIF:** screen/GIF section → browse → upload. Format: **160 × 96 px**, **≤ 255 frames**, keep it short for smooth playback.
7. **RGB:** lighting section → per-key colors.

Full beginner walkthrough with screenshots-friendly detail: see [`tuto-gk600-gif-usb.md`](./tuto-gk600-gif-usb.md).

---

## Hardware reference (for the reverse-engineering crowd)

| Item | Value |
|---|---|
| MCU | HFD80CP100 = Sonix **SN32F299** (Cortex-M0, 128 KB flash) |
| Wireless | WCH **CH582F** (BT) |
| External flash | **PY25Q128HA** (16 MB SPI — stores screen assets) |
| Display | **GC9107** TFT, 160×96, RGB565 |
| USB VID/PID | `0DB0:EA47` (bootloader `0C45:7140`) |
| OEM platform | Shaodong Tongchi (DriveAll) — shared with Womier SK80 PRO, Xinmeng M87 Pro, Aula F98 Pro, etc. |
| Config channel | HID class requests on **MI_03 / usage page FF13** (64-byte Feature reports); image data on EP03 (4096-byte blocks) |

The firmware is fully functional over USB — the only problem was the driver's config, not the device.

---

## Why MSI shipped it broken

The USB `product_name` in `config.xml` (`MSI FORGE GK600 GAMING KEYBOARD`) matches no real device; the keyboard reports `MSI FORGE GK600 TKL WIRELESS Keyboard`. In 2.4G mode the configured name is a correct prefix of the real string, so matching succeeds — which is why only wireless ever worked.

---

*Community guide, not affiliated with MSI. Verified on a GK600 TKL WIRELESS (firmware V1.20) with driver 1.0.0.8. Restore your backup `config.xml` to revert.*

# MSI Forge GK600 TKL Wireless — technical reference

← [Main page](README.md) · 🇫🇷 [Page principale](README.fr.md) (l'annexe technique en français est
dans [restauration/RESTAURATION_MENUS.md](restauration/RESTAURATION_MENUS.md#annexe-technique))

For the reverse-engineering crowd: what's inside, how the screen's memory is laid out, the USB
commands the tools use, and how the boot animation is played. Everything here comes from the
firmware code run in an emulator, MSI's driver, and tests on real keyboards.

## Hardware

| Item | Value |
|---|---|
| MCU | HFD80CP100 = Sonix **SN32F299** (Cortex-M0, 128 KB flash) |
| Wireless | WCH **CH582F** (BT) |
| External flash | **PY25Q128HA** (16 MB SPI, stores every screen picture) |
| Display | **GC9107** TFT, 160 × 96, RGB565 |
| USB VID/PID | `0DB0:EA47` (bootloader `0C45:7140`) |
| OEM platform | Shaodong Tongchi (DriveAll), shared with the Womier SK80 PRO, Xinmeng M87 Pro, AULA F98 Pro, etc. |
| Firmware versions tested | V1.04, V1.20 (and the Frieren Edition's V1.17, run in emulation) |

## Why MSI's driver didn't see the keyboard over USB

MSI's driver (`DeviceDriver.exe`, installed as "Erazer MK85Pro Driver") matches the keyboard by
its USB product name. In `config.xml`, the USB entry (`desc="USB"`) asks for
`MSI FORGE GK600 GAMING KEYBOARD`, which matches no real device: the keyboard reports
`MSI FORGE GK600 TKL WIRELESS Keyboard`. In 2.4G mode the configured name is a correct prefix of
the real string, so matching succeeds, which is why only wireless ever worked. Fixing
`product_name` is enough; `hid_interface` stays on `MI_00` and the driver switches to the right
channel on its own. The firmware itself works fine over USB.

## USB channels and commands

| Item | Value |
|---|---|
| Command interface | MI_03, usage page `FF13`, 64-byte FEATURE reports (+ report ID 0) |
| Data interface | MI_02, usage page `FF68`, 4096-byte output, 64-byte input (acknowledgement) |
| Delay between commands | 35 ms, like the driver (`cmd_delaytime`) |
| Acknowledgement per page | `01 5A 02 00…` on the `FF68` input |

| Command | What it does |
|---|---|
| `04 18` | opens a transfer; byte 3 of the answer is `01` when the keyboard is idle (`00` or `FF` = busy) |
| `04 72` | GIF upload, pages written from `0x3C0000` (what MSI's software uses) |
| `04 38` | raw write, pages written from `0x000000`: `04 38 00 00 00 00 00 00 <page count, LE> 00…` (what the tools in `restauration/` use) |
| `04 02` | closes the transfer |
| `04 13` | lighting block: one effect for the whole keyboard (see below) |
| `04 28` | time sync, followed by a frame marked `0x5A` (the TKL stores the time but never draws it, see below) |

While it receives pages from `04 38`, the keyboard draws its own progress screen,
"LOADING xx %".

## Flash map (16 MB)

| Address | Content |
|---|---|
| `0x000000` | home screen background, 160 × 96, RGB565 little-endian, black |
| `0x007800` – `0x010806` | home screen icons (battery, connection, WIN/MAC, locks) |
| `0x007A8A` – `0x1868A2` | menus and icons (41 full screens, icons, gauges) |
| around `0x17A1CE` | home picture (the dragon), 160 px wide, specific to the GK600 |
| `0x1A0000` | boot animation header |
| `0x1A0100` | boot animation frames |
| `0x3C0000` | user GIF header; frames from `0x3C0100` |

On a factory keyboard, the GIF slot holds MSI's default GIF: 125 frames, header byte 0 = `0x7D`
and no frame times in the header. Its frames are identical to `0.gif` from the driver
(`gif\MSI FORGE GK600\0.gif`, 160 × 96, 125 frames at 40 ms).

The reference image is the public dump of a healthy GK600 by Flonfli
(`Forge gk600 tkl wireless.bin`, SHA-256
`d3a7359a69692e2d25994b8c886cdd87444342b509eaf505cb197664ab671b50`). Because `04 38` always starts
at `0x000000`, each tool rewrites everything from the start of the chip up to the end of its own
area, using the dump for what it doesn't change:

| Tool | Area rewritten | Pages |
|---|---|---|
| `gk600_restore.py restore` | `[0x000000, 0x1A0000)` | 416 |
| `gk600_restore.py restore --with-boot` | `[0x000000, 0x3C0000)` | 960 |
| `gk600_home_picture.py` | `[0x000000, 0x180000)` | 384 |
| `gk600_boot_animation.py` | `[0x000000, 0x1A0100 + N × 0x7800)`, rounded up to a page | up to 957 |

## Lighting

One effect for the whole keyboard, on the command interface (64-byte feature reports):

| Step | Bytes | Answer |
|---|---|---|
| open | `04 18` | byte 3 = `01` |
| select the lighting block | `04 13 00 00 00 00 00 00 01` | byte 3 = `01` |
| settings | 64 bytes: `[0]` effect, `[1:4]` R G B, `[8]` multicolour, `[9]` brightness 1–5, `[10]` speed 1–5, `[11]` direction 0–3, `[14:16]` `AA 55` | echoed |
| apply | `04 02` | byte 3 = `01` |

Effects, in the order of MSI's software (strings 521 to 539 of its language files): 0 off,
1 Static, 2 SingleOn, 3 SingleOff, 4 Glittering, 5 Falling, 6 Colourful, 7 Breath, 8 Spectrum,
9 Outward, 10 Scrolling, 11 Rolling, 12 Rotating, 13 Explode, 14 Launch, 15 Ripples, 16 Flowing,
17 Pulsating, 18 Tilt, 19 Shuttle. MSI's defaults (`rgb-keyboard.xml`): effect 11, brightness 5,
speed 3. Run on the Frieren V1.17 firmware in an emulator, every step is acknowledged and the
keyboard stores the settings in its MCU flash. Source: ahmettahaklc's open-source panel (MIT),
which checked it on a GK600 and took it from the AULA F75 Max.

## Home screen

The dragon is a 160 px wide picture drawn from the top-left corner of the screen. Rows 0 to 64 are
shown (160 × 65), above the icon bar; the battery is drawn on top of it at x 131–155, y 10–22.

## Boot animation

**Format.** A 256-byte header at `0x1A0000`, then the frames:

- byte 0: frame count N (1 to 72);
- bytes 1 to N−2: time of frames 1 to N−2, in 2 ms steps (a value of 15 or less means 50 ms);
- the rest of the header is 0;
- frame i at `0x1A0100 + i × 0x7800`, 160 × 96, RGB565 little-endian.

72 frames is the maximum: `0x1A0100 + 72 × 0x7800 = 0x3BC100`, just below the GIF at `0x3C0000`.
The original MSI animation has 51 frames (header byte `0x33`), the first four black, and lasts
3.5 seconds.

**Playback** (Frieren V1.17 code run in an emulator):

| Frame | Time on screen |
|---|---|
| 0 | 50 ms |
| 1 to N−2 | header value × 2 ms |
| last | 1 s |
| single frame (N = 1) | 3 s |

Then the home screen is drawn. The routines involved:

- `0xF104`, called from `main` (`0x888`) and after a reset (`0xB926`), initialises the screen,
  copies the header with `0xFE04(0x1A0000)` and draws frame 0;
- `0x11428`, a 2 ms timer, loads the next frame time and posts an event when it runs out;
- `0xFE7E` / `0xFEDE` move to the next frame; `0xFE74(500)` sets 1 second for the last one;
- `0xF868` draws the home screen at the end.

MSI's driver stores GIF frame delays the same way (ms / 2 at header byte `1 + i`,
`0x422E99`–`0x422EB1`).

**Measured on a real keyboard** (V1.20, filmed on 22 November 2026 with a 53-frame animation):

- frame 0 is drawn during start-up, before the backlight comes on (it can be seen faintly on the
  dark screen);
- the screen backlight and the key lighting come on together, at about the moment the animation
  timer starts;
- the frames then follow the programmed times (about 100 ms each for that GIF), and the home
  screen appears 6.57 s after the screen lit up, for 6.5 s programmed.

So the tool's default half-second lead-in, meant to cover a backlight delay, only makes the first
frame last longer; `--lead-in 0` gives the GIF's exact timing.

## How a long GIF wipes the menus

The firmware writes the GIF sequentially from `0x3C0000` and never checks for the end of the chip.
Addresses are 24-bit, so past the end, writing wraps to `0x000000`, over the menus. With a 16 MB
chip, a GIF of 420 frames or more reaches the menus, and from 474 frames the boot animation too.
MSI's software caps GIFs at 255 frames (`gif_maxframes`), so this only happens when that limit is
raised. It also stores the frame count in a single byte, so a 300-frame GIF loops after 44 frames.
Full analysis: [restauration/RESTORE_MENUS.md](restauration/RESTORE_MENUS.md).

## The clock: GK600 DUKE vs TKL

MSI's driver has a "Time Syns" button (string 827, also sent on its own when the driver pushes its
settings). It sends `04 28` and a frame marked `0x5A`. On the TKL firmware (handler `0x3D8C` in
Frieren V1.17), the keyboard stores the time, writes its PCF8563-type real-time clock (I²C `0xA2`),
switches the screen to mode 1 and redraws, but the drawing cases for the clock (`0x49`–`0x4E`) are
empty. The AULA F98 Pro firmware of the same platform does draw them. A V1.20 keyboard behaves the
same way as Frieren V1.17: the screen goes back to the home screen, with no digits.

## Tests

[restauration/tests/](restauration/tests/README.md) holds the emulator (Unicorn running the real
Frieren V1.17 firmware with an emulated SPI flash), the replayable scenarios, their results, and
the logs of the sessions on real keyboards.

## Sources

- Flonfli, public dump of a healthy GK600:
  [Flonfli/Forge-gk600-tkl-wireless.bin](https://github.com/Flonfli/Forge-gk600-tkl-wireless.bin)
- parsiya, AULA F108 Pro LCD upload investigation:
  [lcd-upload-investigation.md](https://github.com/parsiya/f108-pro/blob/main/ai-docs/lcd-upload-investigation.md)
- MSI driver 1.0.0.8 and "FRIEREN KB ISP Program V1.17" (the firmware image run in emulation),
  from MSI's official download server

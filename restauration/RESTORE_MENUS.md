# Repairing the GK600 screen menus (experimental)

> **Status: experimental.** Verified by running the real code of the Frieren V1.17 firmware (same
> platform, same protocol) in an emulator, then on a real GK600 (`0DB0:EA47`, firmware V1.20) on
> 18 November 2026: probe and undo, a 384-page write. The full restore has not been run on a
> damaged keyboard yet. What you do with your keyboard remains your responsibility.
>
> **Beginner?** No need to read further: double-click `GK600-Repair.bat` and follow the prompts
> (see [README.md](README.md)). This guide explains what the tool does and how to run it by hand.

## Symptom

After a GIF upload, the menu screens (brightness, effects, colours, connection…) show pieces of an
old GIF, or black. The boot animation still plays and new GIFs can still be uploaded. `Fn + Esc`
(reset) changes nothing.

## Cause

Everything the screen shows lives in a separate flash chip. The menus sit at the start of the chip
(`0x000000` to `0x1A0000`); the GIF starts at `0x3C0000`.

The firmware writes the GIF sequentially and never checks for the end of the chip. Addresses are
24-bit: past the end, writing wraps to the start of the chip, **over the menus**. This is shown in
the platform firmware code and reproduced in emulation. A sibling keyboard, the AULA F108 Pro, lost
its menus the same way after an oversized GIF
([parsiya's write-up](https://github.com/parsiya/f108-pro/blob/main/ai-docs/lcd-upload-investigation.md)).

| Chip size | The GIF spills over the menus from |
|---|---|
| 16 MB (size of the public GK600 dump) | 419 frames: impossible with MSI's software (limit 255) **unless `gif_maxframes` was raised** |
| 8 MB (hypothesis, never observed so far) | 146 frames, which MSI's software accepts |

On the only documented damaged keyboard (MSI forum), `gif_maxframes` had been set to 10005 and GIFs
longer than 255 frames were sent. With a 16 MB chip, the one in the public dump:

- from 256 to 418 frames, nothing spills over, but the animation restarts early: MSI's software
  stores the frame count in a single byte, so 300 frames become 44;
- from 420 frames on, the GIF spills over the menus;
- from 474 on, it reaches the boot animation too.

That is exactly what was observed: first the menus alone, with the boot animation still playing,
then the boot animation as well. Only the last GIF sent still works. An 8 MB chip would give the same
story with lower thresholds (146 and 201 frames): the chip size remains unknown, but the repair works
either way.

### Keep your menus safe

- **Never raise `gif_maxframes`** in `layouts\rgb-keyboard.xml` (255 by default): that is what broke
  the documented keyboard.
- To be safe, until the chip size is checked on other units, **stay at 145 frames or fewer** per GIF
  (160 × 96). MSI's stock GIF has 125.

## What the tool does

`gk600_restore.py` rewrites the original menus over the USB cable, without opening the keyboard.
It uses exactly the path MSI's software uses to send a GIF, except for one command:

| Step | MSI software (GIF) | `gk600_restore.py` |
|---|---|---|
| open | `04 18` | `04 18` (same) |
| write | `04 72` → from `0x3C0000` | `04 38` → from `0x000000` |
| data | 4096-byte pages | 4096-byte pages, each acknowledged by the keyboard (`01 5A 02`) |
| close | `04 02` | `04 02` (same) |

`restore` writes 416 pages, i.e. `[0x000000, 0x1A0000)`: every menu and icon, home screen included
(the dragon in front of the laptop, the battery, the WIN/MAC, connection and lock bar), stopping
right before the boot animation. Your GIF is not touched.

The original pictures come from the public dump of a healthy GK600 published by Flonfli. The tool
does not ship them: you download the dump and the tool checks its fingerprint before using it.

## What you need

- Windows 10 or 11, the USB cable, the keyboard in **wired mode**.
- Python 3.8 or newer, then in a command prompt: `pip install hidapi`
- `gk600_restore.py` (this folder).
- The reference dump: `Forge gk600 tkl wireless.bin` from
  <https://github.com/Flonfli/Forge-gk600-tkl-wireless.bin>, placed **next to** `gk600_restore.py`.
  Expected SHA-256: `d3a7359a69692e2d25994b8c886cdd87444342b509eaf505cb197664ab671b50`
- **Close MSI's software**, including from the system tray (it talks to the keyboard and would mix
  its commands with ours). Same for OpenRGB or SignalRGB.

**Before every write** (steps 1 and 2): unplug the cable, switch the keyboard off, wait 10 seconds,
switch it on, plug the cable back. **The boot animation must play** (if yours is broken, the screen
stays black: just keep the keyboard off for 10 seconds). This matters: an earlier
interrupted transfer can leave the keyboard in a state where data would land shifted, with no
error anywhere. The tool reminds you.

Without `--write`, nothing is written: the tool only shows what it would do.

## Step 0 — check that the keyboard answers (no write)

```
python gk600_restore.py check
```

Expected: the keyboard name, its firmware version, then `Handshake OK`. Note the version shown
(for example `V1.20`): it helps when you report a result.

## Step 1 — the probe (17 pages, reversible)

Validated on 18 November 2026 on a GK600 running `V1.20`: the icons get striped, `unprobe` brings
the original screen back and the boot animation is not touched. **If `check` shows `V1.20`, this
step is optional.** For any other version, do it.

```
python gk600_restore.py probe --write
```

It only touches the first 68 KB of the chip. That area holds the background and every icon of the
home screen, the one with the dragon in front of the laptop:

- the battery, top right;
- the bottom bar: WIN/MAC, connection (USB, 2.4 GHz, BT), Windows lock, Caps Lock and Num Lock.

The probe turns all these icons into magenta and yellow stripes and puts colour bars in the black
background. The dragon itself is not touched and may hide part of the background. Preview:
`images/probe_preview.png`.

- **The icons are striped**: your firmware's `04 38` does write at the start of the chip. If the
  home screen is not showing, press Caps Lock or Num Lock to force a redraw. Put the original icons
  back, then go to step 2:
  ```
  python gk600_restore.py unprobe --write
  ```
  If you go straight on to step 2, `unprobe` is optional: the restore rewrites that area too.
- **Nothing changed, or something else changed**: stop here and report it (firmware version, what
  you see, the `gk600_restore.log` file). Do not run step 2. If your GIF got damaged, upload it
  again with MSI's software.

## Step 2 — the restore (416 pages)

```
python gk600_restore.py restore --write
```

Allow about one minute (on a real GK600, one page takes 120 to 180 ms). Then go through every menu
and compare with `images/reference_screens_0_1A0000.png` (the 41 original menu screens). Switch the
keyboard off and on, and check again.

### If the boot animation is damaged too

If the MSI startup logo is replaced or broken as well, add `--with-boot`:

```
python gk600_restore.py restore --with-boot --write
```

The tool then rewrites `[0x000000, 0x3C0000)`: menus and boot animation, 960 pages, 2 to 3 minutes.
The full 16 MB dump is needed. Your GIF is still not touched.

Right after the probe or the restore the keyboard shows its home screen instead of your GIF: the
firmware does this after this kind of write, and your saved setting comes back at the next power-on.
If your GIF does not come back, upload it again with MSI's software (145 frames at most).

## Option: change the home-screen picture

The dragon in front of the laptop is a 160 px wide picture stored at `0x17A1CE`, drawn from the
top-left corner of the screen. Rows 0 to 64 are shown (160 × 65), above the bottom bar; the
battery is drawn on top of it at x 131–155, y 10–22. `gk600_home_picture.py` replaces it with your
picture. Easiest: drag the picture onto `GK600-Home-Picture.bat`, which sets everything up and shows
a preview before writing. By hand:

```
python gk600_home_picture.py my_picture.png            # dry run, nothing sent
python gk600_home_picture.py my_picture.png --write
```

- The picture: a raw little-endian RGB565 file of 160 × 65 (20,800 bytes), or a PNG / JPG when
  Pillow is installed (`pip install pillow`). A picture of exactly 160 × 65 is used as it is;
  otherwise its plain margins are trimmed and it is scaled down to fit 160 × 65 on black. Keep the
  battery corner empty. `--preview preview.png` shows the result without sending anything.
- `04 38` always writes from `0x000000`: the tool rewrites `[0x000000, 0x180000)`, 384 pages,
  about one minute, with the dump and your picture in place of the dragon. Your GIF and the boot
  animation are not touched. Same precautions as step 2: MSI software closed, keyboard switched
  off and on before the write.
- Back to the dragon: `python gk600_restore.py restore --write`.
- Validated on 18 November 2026 on a GK600 running `V1.20`: 384 pages acknowledged in 54 seconds,
  picture complete and in place.

## If something goes wrong

The tool stops at the **first** anomaly and sends nothing more.

| Message | What to do |
|---|---|
| `no GK600 / Frieren keyboard found` | cable plugged in, wired mode, MSI software closed |
| `keyboard not idle` | switch the keyboard off and on (boot animation), run again |
| `04 38 refused` | **no page was sent**: your firmware does not accept this command. Switch the keyboard off and on, then please report it |
| `page N/416: no ACK` | unplug, switch off, switch on, then run **the same command** again: it rewrites everything from the start |

After an interrupted transfer, the lighting or some keys may stay frozen until the keyboard is
restarted: that is expected.

## Proven, and not yet proven

Proven by running the real Frieren V1.17 firmware code in emulation with the tool itself:

- `04 38` writes from address `0x000000`, page after page, with no header added;
- the restore erases and rewrites exactly `[0x000000, 0x1A0000)` and nothing else;
- the probe only touches `[0x000000, 0x11000)`, and the home-screen drawing code reads every icon
  from that area, where the GK600 dump holds exactly those icons;
- starting from destroyed menus, the whole chip ends up byte-identical to the reference dump;
- a 200-frame GIF destroys the menus of an 8 MB chip and leaves the boot animation intact, and the
  tool repairs them;
- a 500-frame GIF also destroys the boot animation of a 16 MB chip, and `--with-boot` repairs it;
- an interrupted transfer, or a keyboard that was not restarted, is either detected or recoverable
  as described above.

Checked on a real GK600 (`0DB0:EA47`, firmware `V1.20`, Windows 11) on 18 November 2026:

- `check` finds the `FF13` and `FF68` collections with the expected report sizes
  (65 / 4097 / 65), and `04 18` answers `01` (idle);
- `04 38` is accepted and echoes the page count; all 17 probe pages are acknowledged, in about
  2 seconds;
- the home-screen icons get striped, the boot animation stays intact, and `unprobe` brings the
  original screen back.

Log: `tests/real_gk600_V1.20_2026-11-18.log`.

Not yet proven:

- the full restore (416 or 960 pages) on a damaged keyboard: same command and same page-by-page
  mechanism as the probe, not yet run outside emulation. A 384-page write through the same path
  (home-screen picture) worked on a real GK600;
- how `04 38` behaves on firmware versions other than `V1.20`: that is what step 1 checks. Why it
  is likely: the USB descriptors, the command filter and the `04 18` / `04 72` / `04 02` commands
  are identical across the platform, the same `04 38` path exists in another firmware of the family
  (AULA F98 Pro V1.20), and the GK600's V1.20 behaves like Frieren V1.17;
- the chip size on the damaged keyboards (8 or 16 MB);
- exactly where the GK600 firmware reads its dragon: the Frieren one shows its own picture
  elsewhere. No consequence for the restore, which copies the whole area from a GK600 dump.

The replayable tests are in `tests/` (emulator, scenarios, results).

## Technical appendix

| Item | Value |
|---|---|
| Command interface | MI_03, usage page `FF13`, 64-byte FEATURE reports (+ ID 0) |
| Data interface | MI_02, usage page `FF68`, 4096-byte output, 64-byte input (ACK) |
| Delay between commands | 35 ms, like the driver (`cmd_delaytime`) |
| `04 38` | `04 38 00 00 00 00 00 00 <pages LE> 00…` |
| Expected reply | byte 3 = `01`; `00` or `FF` = keyboard busy |
| Per-page ACK | `01 5A 02 00…` on the `FF68` input |
| Home screen: background | `0x000000`, 160 × 96, RGB565 little-endian, black |
| Home screen: icons | `0x007800` to `0x010806` (battery, connection, WIN/MAC, locks) |
| Home screen: dragon | around `0x17A1CE`, 160 px wide (GK600-specific) |
| Menus and icons | `0x007A8A` to `0x1868A2` (41 full screens, icons, gauges) |
| Boot animation | header `0x1A0000`, frames `0x1A0100` |
| User GIF | header `0x3C0000`, frames `0x3C0100` |

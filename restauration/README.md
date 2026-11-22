# GK600 — réparer l'écran / repair the screen

**Expérimental / experimental.** Réparation complète confirmée sur un GK600 TKL Wireless abîmé
(firmware V1.04) et essais sur un autre en V1.20, après validation en émulation sur le vrai code
du firmware. Full repair confirmed on a damaged GK600 TKL Wireless (firmware V1.04) and tests on
another one running V1.20, after validation in emulation against the real firmware code.

---

## 🇫🇷 Pour les débutants (Windows, 5 minutes)

**Le problème :** après l'envoi d'un très long GIF (avec `gif_maxframes` relevé au-delà de 255), les
menus de l'écran sont devenus noirs ou remplis d'images du GIF, parfois le logo MSI du démarrage
aussi. Une réinitialisation d'usine n'y change rien.

1. **Téléchargez** ce dépôt : bouton vert **Code** → **Download ZIP**, puis clic droit sur le ZIP →
   **Extraire tout**.
2. **Fermez le logiciel MSI** (aussi dans la zone de notification, près de l'horloge). Branchez le
   clavier avec son **câble USB**, interrupteur sur **filaire**.
3. Ouvrez le dossier `restauration` et **double-cliquez sur `GK600-Repair.bat`**. Si Windows affiche
   « Windows a protégé votre PC » : **Informations complémentaires** → **Exécuter quand même**.
4. **Suivez les instructions** de la fenêtre. Elle télécharge ce qu'il faut (un Python portable,
   rien n'est installé), vérifie le clavier, vous fait le redémarrer, puis remet les images
   d'origine (2 à 3 minutes). Votre GIF n'est pas touché.
5. Éteignez le clavier 10 secondes et rallumez-le : l'animation MSI et les menus sont revenus.

**Changer l'image de l'écran d'accueil (le dragon) :** glissez une image PNG ou JPG sur
**`GK600-Home-Picture.bat`**. Un aperçu s'ouvre avant toute écriture (environ 1 minute ensuite).
Zone affichée : 160 × 65 pixels ; la batterie s'affiche par-dessus le coin en haut à droite. Pour
remettre le dragon : `GK600-Repair.bat`.

**Changer l'animation de démarrage (le logo MSI) :** glissez un GIF, ou une image PNG ou JPG, sur
**`GK600-Boot-Animation.bat`**. Un aperçu s'ouvre avant toute écriture (1 à 3 minutes ensuite).
Écran de 160 × 96 pixels, 72 images au maximum ; la dernière reste 1 seconde, puis l'écran
d'accueil s'affiche. L'écran ne s'allume qu'une demi-seconde après la mise sous tension : la
première image est tenue pendant ce temps. Si vous avez mis votre propre image d'accueil, la
fenêtre vous propose de la garder. Pour remettre l'animation MSI : `GK600-Repair.bat`.

**Pour que ça n'arrive plus :** laissez `gif_maxframes` à **255** dans `rgb-keyboard.xml`.

---

## 🇬🇧 For beginners (Windows, 5 minutes)

**The problem:** after uploading a very long GIF (with `gif_maxframes` raised above 255), the screen
menus went black or got filled with GIF frames, sometimes the MSI boot logo too. A factory reset
does not help.

1. **Download** this repository: green **Code** button → **Download ZIP**, then right-click the ZIP →
   **Extract All**.
2. **Close MSI's software** (check the system tray too, next to the clock). Plug the keyboard in with
   its **USB cable**, switch set to **wired**.
3. Open the `restauration` folder and **double-click `GK600-Repair.bat`**. If Windows shows "Windows
   protected your PC": **More info** → **Run anyway**.
4. **Follow the prompts.** The window downloads what it needs (a portable Python, nothing gets
   installed), checks the keyboard, has you restart it, then puts the original pictures back
   (2 to 3 minutes). Your GIF is not touched.
5. Switch the keyboard off for 10 seconds and back on: the MSI animation and the menus are back.

**Change the home-screen picture (the dragon):** drag a PNG or JPG onto
**`GK600-Home-Picture.bat`**. A preview opens before anything is written (about 1 minute after
that). Shown area: 160 × 65 pixels; the battery is drawn over the top-right corner. To get the
dragon back: `GK600-Repair.bat`.

**Change the boot animation (the MSI logo):** drag a GIF, or a PNG or JPG picture, onto
**`GK600-Boot-Animation.bat`**. A preview opens before anything is written (1 to 3 minutes after
that). Screen of 160 × 96 pixels, 72 frames at most; the last one stays 1 second, then the home
screen shows. The screen only lights up half a second after power-on: the first frame is held
during that time. If you set your own home picture, the window offers to keep it. To get the MSI
animation back: `GK600-Repair.bat`.

**To keep it from happening again:** leave `gif_maxframes` at **255** in `rgb-keyboard.xml`.

![before / after](images/home_picture_example.png)

---

## How it works / comment ça marche

The keyboard stores its GIF in the screen's flash chip at a fixed address and never checks where the
chip ends: a GIF of about 420 frames or more runs past the end and wraps around to the start of the
chip, where every menu picture lives, then the boot animation. The tool talks to the keyboard over
USB with the same commands as MSI's software and rewrites the original pictures, taken from the
public backup of a working GK600 ([Flonfli/Forge-gk600-tkl-wireless.bin](https://github.com/Flonfli/Forge-gk600-tkl-wireless.bin)).
Nothing to open, no firmware flashing, the GIF area is never touched.

Le clavier range son GIF dans la puce de l'écran à une adresse fixe sans jamais vérifier où la puce
se termine : un GIF d'environ 420 images ou plus déborde et repart au début de la puce, là où sont
toutes les images des menus, puis l'animation de démarrage. L'outil parle au clavier en USB avec les
mêmes commandes que le logiciel MSI et réécrit les images d'origine, prises dans la sauvegarde
publique d'un GK600 qui marche. Rien à ouvrir, aucun flashage de firmware, la zone du GIF n'est
jamais touchée.

Validated on real keyboards: on 18 November 2026 on a GK600 running V1.20 (keyboard check, 17-page
probe and undo, 384-page home picture), and on 19 November 2026 on a damaged GK600 running V1.04
(full repair: menus and MSI boot animation back, GIF untouched), and on 22 November 2026 on the
V1.20 keyboard again (custom boot animation: 36 frames, 687 pages, plays at power-on, home picture
kept). If your firmware is neither V1.04
nor V1.20, `GK600-Repair.bat` first runs a 3-second reversible test and stops if it does not
behave the same.

## Detailed guides / guides détaillés

- Français : [RESTAURATION_MENUS.md](RESTAURATION_MENUS.md)
- English: [RESTORE_MENUS.md](RESTORE_MENUS.md)

Manual use (Python 3.8+ and `pip install hidapi`, the dump `Forge gk600 tkl wireless.bin` next to
the scripts):

```
python gk600_restore.py check                         # no write
python gk600_restore.py probe --write                 # 17 pages, striped icons, reversible
python gk600_restore.py unprobe --write
python gk600_restore.py restore --write               # menus, 416 pages
python gk600_restore.py restore --with-boot --write   # menus + boot animation, 960 pages
python gk600_home_picture.py picture.png --preview preview.png   # needs: pip install pillow
python gk600_home_picture.py picture.png --write      # home picture, 384 pages
python gk600_boot_animation.py anim.gif --preview preview.gif   # needs: pip install pillow
python gk600_boot_animation.py anim.gif --write       # boot animation, up to 957 pages
python gk600_boot_animation.py anim.gif --home picture.png --write   # and keep your home picture
```

## Files / fichiers

| File | Role |
|---|---|
| `GK600-Repair.bat` | double-click: repair menus and boot animation / réparation |
| `GK600-Home-Picture.bat` | drop a picture on it: home-screen picture / image d'accueil |
| `GK600-Boot-Animation.bat` | drop a GIF on it: boot animation / animation de démarrage |
| `gk600_easy.ps1` | what the three `.bat` files run: downloads (SHA-256 checked), prompts |
| `gk600_restore.py` | the restore tool (check, probe, unprobe, restore) |
| `gk600_home_picture.py` | the home-screen picture tool |
| `gk600_boot_animation.py` | the boot animation tool |
| `images/reference_screens_0_1A0000.png` | the 41 original menu screens, to compare after a repair |
| `images/probe_preview.png` | home screen before and after the probe |
| `tests/` | emulator, replayable scenarios, results, log of the real-keyboard session |

*Community tool, not affiliated with MSI. Use at your own risk.*

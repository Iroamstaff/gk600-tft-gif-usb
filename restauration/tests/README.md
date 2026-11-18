# Tests rejouables / replayable tests

Les tests exécutent le **vrai code** du firmware Frieren V1.17 (Unicorn), avec une puce flash SPI
émulée, derrière l'outil `gk600_restore.py`. Aucun clavier n'est nécessaire.

The tests run the **real code** of the Frieren V1.17 firmware (Unicorn) with an emulated SPI flash
chip, behind `gk600_restore.py`. No keyboard is needed.

## Préparer / set up

```
pip install unicorn
python -I extract_frieren_fw.py "FRIEREN KB_ISP Program_V1.17_20260624_0x8AAD.exe" frieren_v117.bin
```

L'exécutable vient du paquet officiel MSI de la page support « FORGE TKL WIRELESS FRIEREN
EDITION ». Il n'est pas exécuté : le script lit seulement l'image qu'il contient et vérifie son
empreinte. / The executable comes from MSI's official package on the "FORGE TKL WIRELESS FRIEREN
EDITION" support page. It is not run: the script only reads the image it contains and checks its
fingerprint.

## Lancer / run

```
python -I test_on_emulated_firmware.py frieren_v117.bin "Forge gk600 tkl wireless.bin" .. . [--slow]
python -I test_cli_with_fake_hidapi.py frieren_v117.bin "Forge gk600 tkl wireless.bin" .. .
python -I test_home_picture.py frieren_v117.bin "Forge gk600 tkl wireless.bin" .. . <image 160x65 .rgb565>
```

`--slow` ajoute le scénario puce 16 Mio + GIF de 470 images (environ 4 minutes de plus).
Résultats : `results.json`. / `--slow` adds the 16 MiB chip + 470-frame GIF scenario (about 4 more
minutes). Results: `results.json`.

| Fichier / file | Rôle / role |
|---|---|
| `gk600_fw_emu.py` | banc : firmware réel + flash SPI émulée / bench: real firmware + emulated SPI flash |
| `test_on_emulated_firmware.py` | scénarios S0–S11 / scenarios S0–S11 |
| `test_home_picture.py` | `gk600_home_picture.py` sur le firmware émulé, puis retour au dump / on the emulated firmware, then back to the dump |
| `test_cli_with_fake_hidapi.py` | ligne de commande complète, faux module `hid` aux conventions Windows / full CLI with a fake Windows-style `hid` module |
| `extract_frieren_fw.py` | extraction vérifiée du firmware / verified firmware extraction |
| `real_gk600_V1.20_2026-11-18.log` | vrai GK600 (`EA47`, V1.20) : `list`, `check`, essais à blanc, `probe` et `unprobe` réels, puis image d'accueil (384 pages) / real GK600: list, check, dry runs, real probe and unprobe, then home picture (384 pages) |

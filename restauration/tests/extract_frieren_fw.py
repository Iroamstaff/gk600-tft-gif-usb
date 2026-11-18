#!/usr/bin/env python3
"""Extracts the Frieren V1.17 firmware image used by the emulated tests.

Source: MSI "FORGE TKL WIRELESS FRIEREN EDITION" support page, package
FRIEREN KB_ISP Program_V1.17_20260624_0x8AAD.exe (the image is an RCDATA
resource of the ISP tool; nothing is executed).

Usage: python -I extract_frieren_fw.py "<...0x8AAD.exe>" frieren_v117.bin
"""
import hashlib
import sys

OFFSET, SIZE = 0x1BAA4C, 0x40000
SHA256 = "8872d242f8be67ddc078d20e82b074fc036f6526fe3d846657451b8663114d96"

exe = open(sys.argv[1], "rb").read()
img = exe[OFFSET:OFFSET + SIZE]
if hashlib.sha256(img).hexdigest() != SHA256:
    sys.exit("not the expected V1.17 image (wrong file or offset)")
csum = sum(int.from_bytes(img[i:i + 2], "little") for i in range(0, SIZE, 2)) & 0xFFFF
assert csum == 0x8AAD, hex(csum)
open(sys.argv[2], "wb").write(img)
print("OK: %s (checksum 0x%04X, matches the file name)" % (sys.argv[2], csum))

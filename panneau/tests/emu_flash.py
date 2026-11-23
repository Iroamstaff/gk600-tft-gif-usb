"""emu_flash.py - the emulated GK600 (real Frieren V1.17 firmware code) with its own MCU flash
modelled: page erase (1 KiB, 0x8C00) and program (0x8C2E bytes, 0x8D14 / 0x8CBE words) change the
emulated memory with NOR rules, so configuration blocks can be written, checked and read back."""

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2

import gk600_fw_emu as E

ERASE, PROG_BYTES, PROG_WORDS, PROG_WORDS2 = 0x8C00, 0x8C2E, 0x8D14, 0x8CBE
PAGE = 0x400
FLASH_MIN = 0x8000          # the firmware itself refuses anything below
FLASH_END = 0x40000


class FlashEmu(E.FirmwareEmu):
    def __init__(self, fw_bytes, flash):
        self.iflash_ops = []        # ("erase", page) / ("program", address, length)
        self.overprogram = []       # programs over bytes that were not erased
        self.refused = []
        super().__init__(fw_bytes, flash)
        for a in (PROG_WORDS, PROG_WORDS2):
            self.uc.hook_add(UC_HOOK_CODE, self._on_hook, begin=a, end=a)

    def iflash(self, addr, n):
        return self.rb(addr, n)

    def _on_hook(self, uc, addr, size, user):
        if addr not in (ERASE, PROG_BYTES, PROG_WORDS, PROG_WORDS2):
            return super()._on_hook(uc, addr, size, user)
        r0 = uc.reg_read(UC_ARM_REG_R0)
        r1 = uc.reg_read(UC_ARM_REG_R1)
        r2 = uc.reg_read(UC_ARM_REG_R2)
        if addr in E.STUBS:
            self.calls.append((addr, E.STUBS[addr], r0))
        if addr == ERASE:
            if FLASH_MIN <= r0 < FLASH_END:
                base = r0 & ~(PAGE - 1)
                uc.mem_write(base, b"\xFF" * PAGE)
                self.iflash_ops.append(("erase", base))
            else:
                self.refused.append(("erase", r0))
            return self._ret(0)
        n = (r1 + 3) & ~3 if addr == PROG_BYTES else 4 * r1
        if not (FLASH_MIN <= r0 and r0 + n <= FLASH_END):
            self.refused.append(("program", r0, n))
            return self._ret(1)
        data = bytes(uc.mem_read(r2, n))
        old = bytes(uc.mem_read(r0, n))
        new = bytes(a & b for a, b in zip(old, data))
        if new != data:
            self.overprogram.append((r0, n))
        uc.mem_write(r0, new)
        self.iflash_ops.append(("program", r0, n))
        return self._ret(0)

#!/usr/bin/env python3
"""Offline test bench: runs the REAL Frieren V1.17 firmware code (Unicorn, Thumb)
behind a host-side transport, with an emulated SPI NOR flash on the SPI bus.

Real firmware code executed:
  - C runtime start-up (.data copy / .bss zeroing) up to main()
  - SET_REPORT data stage           0x1A3C  (EP0 OUT -> command buffer 0x20001320)
  - GET_REPORT data stage           0x1D50  (command buffer -> EP0 IN)
  - EP3 OUT fragment receiver       0x0C14  (64-byte fragments -> page buffer)
  - protocol state machine          0x4648  (parser 0x4352, dispatcher 0x4204,
                                             states 3 / 5, page writer 0x3DE4)
  - SPI flash driver                0x6ADA / 0x6A06 / 0x6A92 / 0x6A3C
  - protocol timeout                0x4690

Emulated / intercepted (no protocol logic inside):
  - 0x6960  SPI byte exchange  -> SpiFlash model (CS from GPIO 0x40044024/28 bit 13)
  - 0x1330 / 0x134C  USB packet-RAM word read / write -> UsbRam model
  - 0x0B78  EP IN send -> recorded (EP4 = page ACK)
  - 0x128E  endpoint arming -> recorded
  - display, LED/PWM, key-scan and delay helpers -> recorded no-ops
  - internal-flash erase/program 0x8C00 / 0x8C2E -> recorded (must never fire here)

The main-loop glue between those pieces (call 0x4648, then flush the EP4 ACK
flag 0x20000035 exactly like 0x044E-0x0464) is reproduced here.
"""
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)

FW_SHA256 = "8872d242f8be67ddc078d20e82b074fc036f6526fe3d846657451b8663114d96"
RAM_BASE, RAM_SIZE = 0x20000000, 0x10000
PER_BASE, PER_SIZE = 0x40000000, 0x100000
SCS_BASE, SCS_SIZE = 0xE0000000, 0x100000
TRAMP = 0x30000000            # return address used for host-initiated calls
MAIN = 0x84C
STACK_TOP = 0x20002DB0

# RAM variables (from the disassembly)
PROTO = 0x200000B8            # protocol struct: +1 state, +6 flags, +0xC pages left, +0xE timeout, +0x1C SPI address
CMD_FLAGS = 0x20000040        # bit0 = command received, bit1 = response read
CMD_BUF = 0x20001320          # 64-byte command / response buffer
EP0_STAGE = 0x2000131E        # 1 = SET_REPORT data stage pending
FRAG_COUNTER = 0x20000036
BLOCK_READY = 0x20000034
ACK_PENDING = 0x20000035
ACK_BUF = 0x200012B8
DISP_MODE = 0x20000201
DISP_RELOAD = 0x20000203
EP3CTL = 0x4005C024
GPIO_SET, GPIO_CLR, CS_BIT = 0x40044024, 0x40044028, 1 << 13

STUBS = {
    0x6470: "key scan (fallback)", 0x3A20: "key/LED helper", 0x6F12: "delay",
    0x7E24: "LED engine restart (IRQ19 re-enable)", 0x7EF8: "PWM stop", 0x7F16: "timer clocks off",
    0x6332: "LED helper 6332", 0x3BF8: "LED helper 3BF8", 0x3CF2: "LED helper 3CF2",
    0xE0C2: "display E0C2", 0xF868: "display redraw F868", 0xFE20: "user animation reload FE20",
    0x5970: "progress screen 5970", 0x46C4: "NVIC_DisableIRQ",
    0x8C00: "INTERNAL FLASH PAGE ERASE", 0x8C2E: "INTERNAL FLASH PROGRAM",
}


class SpiFlash:
    """Minimal SPI NOR model (PY25Q128HA command subset). Address bits above the
    chip size are ignored, exactly like a real 3-byte-address part."""

    def __init__(self, size=16 << 20, init=None, busy_polls=0):
        assert size & (size - 1) == 0
        self.size = size
        self.mem = bytearray(init) if init is not None else bytearray(b"\xFF" * size)
        assert len(self.mem) == size
        self.cs = False
        self.buf = []
        self.wel = False
        self.busy_polls = busy_polls
        self._busy_left = 0
        self.ops = []            # ("erase"|"program"|"refused", address, length)

    def select(self):
        self.cs = True
        self.buf = []

    def deselect(self):
        if not self.cs:
            return
        self.cs = False
        b = self.buf
        if not b:
            return
        cmd = b[0]
        if cmd == 0x06:
            self.wel = True
        elif cmd == 0x04:
            self.wel = False
        elif cmd == 0x20 and len(b) >= 4:
            addr = ((b[1] << 16) | (b[2] << 8) | b[3]) & (self.size - 1)
            if self.wel:
                base = addr & ~0xFFF
                self.mem[base:base + 0x1000] = b"\xFF" * 0x1000
                self.ops.append(("erase", base, 0x1000))
                self._busy_left = self.busy_polls
            else:
                self.ops.append(("refused", addr, 0))
            self.wel = False
        elif cmd == 0x02 and len(b) >= 4:
            addr = ((b[1] << 16) | (b[2] << 8) | b[3]) & (self.size - 1)
            data = b[4:]
            if self.wel:
                page = addr & ~0xFF
                for i, v in enumerate(data):
                    a = page | ((addr + i) & 0xFF)       # wraps inside the 256-byte page
                    self.mem[a] &= v
                self.ops.append(("program", addr, len(data)))
                self._busy_left = self.busy_polls
            else:
                self.ops.append(("refused", addr, len(data)))
            self.wel = False

    def xfer(self, out):
        if not self.cs:
            return 0xFF
        self.buf.append(out)
        b = self.buf
        cmd = b[0]
        if cmd == 0x05 and len(b) >= 2:
            if self._busy_left:
                self._busy_left -= 1
                return 0x03
            return 0x00
        if cmd == 0x03 and len(b) >= 5:
            addr = ((b[1] << 16) | (b[2] << 8) | b[3]) + (len(b) - 5)
            return self.mem[addr & (self.size - 1)]
        if cmd == 0x9F and len(b) >= 2:
            return [0x85, 0x20, 0x18][min(len(b) - 2, 2)]
        return 0xFF


class FirmwareEmu:
    def __init__(self, fw_bytes, flash):
        import hashlib
        if hashlib.sha256(fw_bytes).hexdigest() != FW_SHA256:
            raise ValueError("unexpected firmware image")
        self.fw = fw_bytes
        self.flash = flash
        self.usbram = bytearray(0x200)
        self.ep_in = []          # (endpoint, bytes)
        self.ep_armed = []
        self.calls = []          # stub calls, in order
        self.uc = uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        uc.mem_map(0, 0x40000)
        uc.mem_write(0, fw_bytes)
        uc.mem_map(RAM_BASE, RAM_SIZE)
        uc.mem_map(PER_BASE, PER_SIZE)
        uc.mem_map(SCS_BASE, SCS_SIZE)
        uc.mem_map(TRAMP, 0x1000)
        uc.mem_write(TRAMP, b"\xFE\xE7" * 8)        # b . (never executed: we stop on arrival)
        for addr in list(STUBS) + [0x6960, 0x1330, 0x134C, 0x0B78, 0x128E, MAIN]:
            uc.hook_add(UC_HOOK_CODE, self._on_hook, begin=addr, end=addr)
        uc.hook_add(UC_HOOK_MEM_WRITE, self._on_gpio, begin=GPIO_SET, end=GPIO_CLR + 3)
        self._boot()

    # ---------------------------------------------------------------- plumbing
    def _ret(self, r0=None):
        uc = self.uc
        if r0 is not None:
            uc.reg_write(UC_ARM_REG_R0, r0 & 0xFFFFFFFF)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR) | 1)

    def _on_hook(self, uc, addr, size, _):
        r0 = uc.reg_read(UC_ARM_REG_R0)
        r1 = uc.reg_read(UC_ARM_REG_R1)
        r2 = uc.reg_read(UC_ARM_REG_R2)
        if addr == MAIN:
            uc.emu_stop()
            return
        if addr == 0x6960:                              # SPI byte exchange
            self._ret(self.flash.xfer(r0 & 0xFF))
        elif addr == 0x1330:                            # USB RAM read word -> [0x20000038]
            w = self.usbram[r0:r0 + 4]
            uc.mem_write(0x20000038, bytes(w))
            self._ret()
        elif addr == 0x134C:                            # USB RAM write word
            self.usbram[r0:r0 + 4] = struct.pack("<I", r1)
            self._ret()
        elif addr == 0x0B78:                            # EP IN send (ep, buf, len)
            data = bytes(uc.mem_read(r1, r2))
            self.ep_in.append((r0, data))
            self._ret(0)
        elif addr == 0x128E:                            # arm endpoint
            self.ep_armed.append((r0, r1))
            self._ret()
        else:
            self.calls.append((addr, STUBS[addr], r0))
            self._ret(0)

    def _on_gpio(self, uc, access, addr, size, value, _):
        if value & CS_BIT:
            if addr == GPIO_CLR:
                self.flash.select()
            elif addr == GPIO_SET:
                self.flash.deselect()

    def call(self, addr, *args, limit=50_000_000):
        uc = self.uc
        for reg, val in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            uc.reg_write(reg, val)
        uc.reg_write(UC_ARM_REG_SP, STACK_TOP)
        uc.reg_write(UC_ARM_REG_LR, TRAMP | 1)
        uc.emu_start(addr | 1, TRAMP, count=limit)
        if uc.reg_read(UC_ARM_REG_PC) & ~1 != TRAMP:
            raise RuntimeError("call 0x%X did not return (pc=0x%X)" % (addr, uc.reg_read(UC_ARM_REG_PC)))
        return uc.reg_read(UC_ARM_REG_R0)

    def _boot(self):
        uc = self.uc
        uc.reg_write(UC_ARM_REG_SP, STACK_TOP)
        uc.emu_start(0xC0 | 1, MAIN, count=5_000_000)  # C runtime: scatter-load then main()
        if uc.reg_read(UC_ARM_REG_PC) & ~1 != MAIN:
            raise RuntimeError("start-up did not reach main()")

    # ---------------------------------------------------------------- memory
    def rb(self, addr, n=1):
        return bytes(self.uc.mem_read(addr, n))

    def u8(self, addr):
        return self.rb(addr)[0]

    def u16(self, addr):
        return struct.unpack("<H", self.rb(addr, 2))[0]

    def u32(self, addr):
        return struct.unpack("<I", self.rb(addr, 4))[0]

    def w8(self, addr, v):
        self.uc.mem_write(addr, bytes([v & 0xFF]))

    @property
    def state(self):
        return self.u8(PROTO + 1)

    @property
    def spi_address(self):
        return self.u32(PROTO + 0x1C)

    @property
    def pages_left(self):
        return self.u16(PROTO + 0xC)

    @property
    def frag_counter(self):
        return self.u8(FRAG_COUNTER)

    # ---------------------------------------------------------------- device side
    def main_step(self):
        """One main-loop pass: protocol state machine, then the EP4 ACK flush (0x044E)."""
        self.call(0x4648)
        if self.u8(ACK_PENDING):
            self.ep_in.append((4, self.rb(ACK_BUF, 64)))
            self.w8(ACK_PENDING, 0)

    def tick_ms(self, n=1):
        """n x (1 ms flag -> timeout routine 0x4690, then a main-loop pass)."""
        for _ in range(n):
            self.call(0x4690)
            self.main_step()

    # ---------------------------------------------------------------- host side
    def host_set_feature(self, payload64):
        assert len(payload64) == 64
        self.usbram[0:64] = payload64
        self.w8(EP0_STAGE, 1)                  # SETUP stage of SET_REPORT seen
        self.call(0x1A3C)                      # data stage
        self.main_step()

    def host_get_feature(self):
        self.usbram[0:64] = b"\x00" * 64
        self.call(0x1D50)                      # GET_REPORT data stage
        resp = bytes(self.usbram[0:64])
        self.main_step()
        return resp

    def host_write_fragment(self, frag):
        n = len(frag)
        assert 0 < n <= 64
        self.usbram[0xC0:0xC0 + 64] = frag.ljust(64, b"\x00")
        self.uc.mem_write(EP3CTL, struct.pack("<I", 0x80000000 | n))
        self.call(0x0C14)

    def host_write_page(self, page, fragment=64):
        assert len(page) == 4096
        for off in range(0, 4096, fragment):
            self.host_write_fragment(page[off:off + fragment])
        self.main_step()

    def host_read_ep4(self):
        for i, (ep, data) in enumerate(self.ep_in):
            if ep == 4:
                del self.ep_in[i]
                return data
        return None


class EmulatedTransport:
    """Same interface as the real hidapi transport of gk600_restore.py."""

    def __init__(self, emu):
        self.emu = emu
        self.log = []

    def set_feature(self, payload64):
        self.log.append(("SET_FEATURE", bytes(payload64)))
        self.emu.host_set_feature(bytes(payload64))

    def get_feature(self):
        r = self.emu.host_get_feature()
        self.log.append(("GET_FEATURE", r))
        return r

    def write_page(self, page4096):
        self.log.append(("PAGE", len(page4096)))
        self.emu.host_write_page(bytes(page4096))

    def read_ack(self, timeout_s):
        r = self.emu.host_read_ep4()
        self.log.append(("ACK", r))
        return r

    def sleep(self, seconds):
        # 1 ms granularity, the firmware timeout runs while the host waits
        self.emu.tick_ms(max(0, int(round(seconds * 1000))))

"""emu_backend.py - an emulated GK600 (real Frieren V1.17 firmware code) behind the panel, for tests."""

import tempfile
import threading

import gk600_restore as g
import gk600_fw_emu as E
import gk600_panel as P

fw = ref = None          # set by the test scripts


class EmuTransport(E.EmulatedTransport):
    def close(self):
        pass


class EmuBackend:
    def __init__(self, emu, version=0x0120):
        self.emu, self.version, self.present, self.conf = emu, version, True, []

    def keyboards(self):
        return [{"pid": 0xEA47, "name": g.KNOWN_PIDS[0xEA47], "product": "MSI FORGE GK600 TKL WIRELESS Keyboard",
                 "version": self.version}] if self.present else []

    def conflicts(self):
        return self.conf

    def select(self, log):
        if self.conf:
            raise g.RestoreError("close %s first (also from the system tray)" % ", ".join(self.conf))
        if not self.present:
            raise g.RestoreError("no GK600 / Frieren keyboard found in wired USB mode")
        return {"pid": 0xEA47, "version": self.version, "name": g.KNOWN_PIDS[0xEA47]}

    def open(self, info):
        return EmuTransport(self.emu)


def new_panel(version=0x0120, flash_model=False):
    if flash_model:                     # the MCU flash modelled too (keys, colours, macros...)
        import emu_flash
        emu = emu_flash.FlashEmu(fw, E.SpiFlash(16 << 20, init=ref))
    else:
        emu = E.FirmwareEmu(fw, E.SpiFlash(16 << 20, init=ref))
    backend = EmuBackend(emu, version)
    state = tempfile.mkdtemp(prefix="gk600_state_")
    panel = P.Panel(backend, state_dir=state, reference=ref)
    server = P.Server(panel, 0)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()
    return emu, backend, panel, server



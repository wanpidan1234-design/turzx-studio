"""macOS/Linux libusb transport for the existing TURZX image protocol.

Enumeration reads descriptors only. Opening claims the current interface without
resetting the device or detaching a kernel driver. An unconfigured device
selects its only advertised configuration; an existing configuration is kept.
"""
from __future__ import annotations

import ctypes.util
from pathlib import Path
import threading
import time

from turzx_usb import (TurzxWinUSB, TurzxUSBError, build_command, validate_ack,
                       TIMEOUT_MS, PACKET_SIZE)


def _usb_modules():
    try:
        import usb.core
        import usb.util
        import usb.backend.libusb1
    except ImportError as exc:
        raise TurzxUSBError("PyUSB is missing. Install this project's requirements.txt.") from exc
    def find_library(name):
        found = ctypes.util.find_library(name)
        if found:
            return found
        for path in ("/opt/homebrew/lib/libusb-1.0.dylib", "/usr/local/lib/libusb-1.0.dylib"):
            if Path(path).is_file():
                return path
        return None
    backend = usb.backend.libusb1.get_backend(find_library=find_library)
    if backend is None:
        raise TurzxUSBError("libusb is missing. On macOS run: brew install libusb")
    return usb.core, usb.util, backend


def _device_path(device):
    return f"libusb:{device.bus}:{device.address}:{device.idVendor:04x}:{device.idProduct:04x}"


def enumerate_device_paths(vid=0x1CBE, pid=0x0050):
    """List present devices without opening or claiming an interface."""
    core, _util, backend = _usb_modules()
    try:
        return [_device_path(device) for device in core.find(
            find_all=True, idVendor=vid, idProduct=pid, backend=backend)]
    except core.USBError as exc:
        raise TurzxUSBError(f"USB enumeration failed: {exc}") from exc


class TurzxLibUSB(TurzxWinUSB):
    """Same public image/brightness API as WinUSB; separate transport ownership."""

    def __init__(self, vid=0x1CBE, pid=0x0050, serial=None):
        self._lock = threading.RLock()
        self._faulted = False
        self._device = None
        self._claimed = False
        self._info = {}
        self.vid, self.pid = int(vid), int(pid)
        self._core, self._util, backend = _usb_modules()
        devices = list(self._core.find(find_all=True, idVendor=vid, idProduct=pid, backend=backend))
        # Do not open arbitrary matching devices merely to read serial numbers.
        # Multiple-panel setups must unplug the unselected panel before opening.
        if len(devices) != 1:
            raise TurzxUSBError(f"Expected one TURZX {vid:04x}:{pid:04x} panel; found {len(devices)}")
        self._device = devices[0]
        self._device.default_timeout = TIMEOUT_MS
        self.device_path = _device_path(self._device)
        try:
            # macOS leaves this vendor-class device unconfigured at attachment.
            # Select the sole configuration only from configuration 0; do not
            # reset an already configured device or write persistent settings.
            current = bytes(self._device.ctrl_transfer(0x80, 8, 0, 0, 1, timeout=TIMEOUT_MS))
            if len(current) != 1:
                raise TurzxUSBError("Invalid USB GET_CONFIGURATION response")
            if current[0] == 0:
                configurations = list(self._device)
                if len(configurations) != 1 or not configurations[0].bConfigurationValue:
                    raise TurzxUSBError("Unconfigured panel must advertise exactly one configuration")
                self._device.set_configuration(configurations[0].bConfigurationValue)
            configuration = self._device.get_active_configuration()
            interface = configuration[(0, 0)]
            if int(interface.bInterfaceNumber) != 0:
                raise TurzxUSBError("Expected USB interface 0")
            pipes = [{"address": int(ep.bEndpointAddress),
                      "address_hex": f"0x{ep.bEndpointAddress:02x}",
                      "type": int(ep.bmAttributes) & 3,
                      "direction": "in" if ep.bEndpointAddress & 0x80 else "out",
                      "max_packet_size": int(ep.wMaxPacketSize),
                      "interval": int(ep.bInterval)} for ep in interface]
            inbound = [p for p in pipes if p["type"] == 2 and p["direction"] == "in"]
            outbound = [p for p in pipes if p["type"] == 2 and p["direction"] == "out"]
            if len(inbound) != 1 or len(outbound) != 1:
                raise TurzxUSBError("Expected exactly one bulk IN and one bulk OUT endpoint")
            self._in, self._out = inbound[0]["address"], outbound[0]["address"]
            actual_serial = self._util.get_string(self._device, self._device.iSerialNumber) if self._device.iSerialNumber else ""
            if serial is not None and actual_serial.casefold() != str(serial).casefold():
                raise TurzxUSBError("Opened USB serial descriptor does not match requested serial")
            self._util.claim_interface(self._device, 0)
            self._claimed = True
            self._info = {
                "transport": "libusb", "device_path": self.device_path,
                "vendor_id": self.vid, "product_id": self.pid,
                "serial_number": actual_serial, "endpoints": pipes,
                "interface": {"bInterfaceNumber": int(interface.bInterfaceNumber)},
                "configuration": {"value": int(configuration.bConfigurationValue)},
                "warnings": [],
                "inferred_panel": {"model": "TURZX 5.2 inch USB", "native_width": 720,
                                   "native_height": 1280, "basis": "public VID/PID mapping"},
            }
        except BaseException as exc:
            self.close()
            if isinstance(exc, self._core.USBError):
                raise TurzxUSBError(f"Cannot open TURZX USB interface (device may be busy): {exc}") from exc
            raise

    def _ensure_open(self):
        if self._device is None or not self._claimed:
            raise TurzxUSBError("Panel is closed")
        if self._faulted:
            raise TurzxUSBError("Previous transfer failed; close and explicitly reconnect before another command")

    def _transact(self, command, parameters=b"", payload=b""):
        packet = build_command(command, parameters) + payload
        with self._lock:
            self._ensure_open()
            try:
                count = self._device.write(self._out, packet, timeout=TIMEOUT_MS)
                if count != len(packet):
                    raise TurzxUSBError(f"Short USB write: {count}/{len(packet)} bytes")
                deadline = time.monotonic() + TIMEOUT_MS / 1000
                for _ in range(3):
                    remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
                    response = bytes(self._device.read(self._in, PACKET_SIZE, timeout=remaining_ms))
                    if response:
                        return validate_ack(response, command=command)
                    if time.monotonic() >= deadline:
                        break
                raise TurzxUSBError(f"Command {command}: no ACK after zero-length USB packets")
            except BaseException as exc:
                self._faulted = True
                if isinstance(exc, self._core.USBError):
                    raise TurzxUSBError(f"USB transfer failed (command={command}): {exc}") from exc
                raise

    def close(self):
        """Release only this object's interface, without resetting the display."""
        with self._lock:
            device, claimed = self._device, self._claimed
            self._device, self._claimed = None, False
            if device is None:
                return
            try:
                if claimed:
                    self._util.release_interface(device, 0)
            finally:
                self._util.dispose_resources(device)

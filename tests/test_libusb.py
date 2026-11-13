"""Transport safety checks with a fake device; no hardware required."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from turzx_libusb import TurzxLibUSB, enumerate_device_paths
from turzx_usb import TurzxUSBError


class USBError(Exception):
    pass


class Interface(list):
    bInterfaceNumber = 0


class Config:
    bConfigurationValue = 1
    def __getitem__(self, key):
        assert key == (0, 0)
        return Interface([SimpleNamespace(bEndpointAddress=a, bmAttributes=2,
                          wMaxPacketSize=512, bInterval=0) for a in (0x81, 1)])


class Device:
    bus, address, idVendor, idProduct, iSerialNumber = 1, 2, 0x1CBE, 0x0050, 0
    def __init__(self, configured=1):
        self.configured = configured
        self.selected = []
        self.writes = []
        self.reads = []
        self.replies = [b'\0\xc8' + b'\0' * 510]
        self.short_write = False
    def ctrl_transfer(self, *args, **kwargs):
        return bytes([self.configured])
    def __iter__(self):
        return iter([Config()])
    def set_configuration(self, value):
        self.selected.append(value)
        self.configured = value
    def get_active_configuration(self):
        return Config()
    def write(self, endpoint, packet, timeout):
        self.writes.append((endpoint, packet, timeout))
        return len(packet) - int(self.short_write)
    def read(self, endpoint, size, timeout):
        self.reads.append((endpoint, size, timeout))
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.device = Device()
        self.claims = []
        self.releases = []
        self.disposals = []
        core = SimpleNamespace(USBError=USBError, find=lambda **kw: [self.device])
        util = SimpleNamespace(claim_interface=lambda *x: self.claims.append(x),
                               release_interface=lambda *x: self.releases.append(x),
                               dispose_resources=lambda *x: self.disposals.append(x))
        self.patch = patch('turzx_libusb._usb_modules', return_value=(core, util, object()))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_enumeration_does_not_claim_or_configure(self):
        self.assertEqual(enumerate_device_paths(), ['libusb:1:2:1cbe:0050'])
        self.assertEqual(self.claims, [])
        self.assertEqual(self.device.selected, [])

    def test_open_keeps_existing_configuration(self):
        with TurzxLibUSB() as panel:
            self.assertEqual(panel.descriptor_info()['transport'], 'libusb')
        self.assertEqual(self.device.selected, [])
        self.assertEqual(len(self.releases), 1)
        self.assertEqual(len(self.disposals), 1)

    def test_unconfigured_selects_only_configuration(self):
        self.device.configured = 0
        with TurzxLibUSB():
            pass
        self.assertEqual(self.device.selected, [1])

    def test_zero_packet_retries_read_but_does_not_resend(self):
        self.device.replies.insert(0, b'')
        with TurzxLibUSB() as panel:
            self.assertEqual(len(panel.sync()), 512)
        self.assertEqual(len(self.device.writes), 1)
        self.assertEqual(len(self.device.reads), 2)
        self.assertTrue(all(0 < r[2] <= 2000 for r in self.device.reads))

    def test_short_write_faults_without_ack_read_or_retry(self):
        self.device.short_write = True
        with TurzxLibUSB() as panel:
            with self.assertRaisesRegex(TurzxUSBError, 'Short USB write'):
                panel.sync()
            with self.assertRaisesRegex(TurzxUSBError, 'Previous transfer failed'):
                panel.sync()
        self.assertEqual(len(self.device.writes), 1)
        self.assertEqual(self.device.reads, [])

    def test_timeout_faults_and_requires_new_session(self):
        self.device.replies = [USBError('timeout')]
        with TurzxLibUSB() as panel:
            with self.assertRaisesRegex(TurzxUSBError, 'USB transfer failed'):
                panel.sync()
            with self.assertRaisesRegex(TurzxUSBError, 'Previous transfer failed'):
                panel.sync()
        self.assertEqual(len(self.device.writes), 1)

    def test_closed_session_does_not_write(self):
        panel = TurzxLibUSB()
        panel.close()
        panel.close()
        with self.assertRaisesRegex(TurzxUSBError, 'closed'):
            panel.sync()
        self.assertEqual(self.device.writes, [])
        self.assertEqual(len(self.releases), 1)

    def test_malformed_ack_faults(self):
        self.device.replies = [b'\0\xc8']
        with TurzxLibUSB() as panel:
            with self.assertRaisesRegex(TurzxUSBError, 'invalid ACK'):
                panel.sync()
            with self.assertRaisesRegex(TurzxUSBError, 'Previous transfer failed'):
                panel.sync()


if __name__ == '__main__':
    unittest.main()

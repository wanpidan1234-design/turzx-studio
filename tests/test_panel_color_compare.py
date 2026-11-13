"""Colour comparison frames and exclusive USB handoff; never accesses hardware."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import panel_color_compare as comparison


class ColorComparisonTests(unittest.TestCase):
    def test_all_candidates_are_opaque_native_pngs_under_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            profiles = comparison.build(output)
            self.assertEqual(len(profiles), 6)
            for path in output.glob('*-native.png'):
                payload = path.read_bytes()
                self.assertLess(len(payload), 1024*1024)
                self.assertEqual(payload[25], 6)
                with Image.open(io.BytesIO(payload)) as image:
                    self.assertEqual(image.size, (720, 1280))
                    self.assertEqual(image.getchannel('A').getextrema(), (255, 255))
            # Only the colour-order chart varies channel mapping.
            self.assertTrue(all(p['panel_color_order'] == 'brg' for p in profiles))
            self.assertTrue(all(p['panel_calibration']['offset_x'] == -60 for p in profiles))
            chart = comparison.channel_chart()
            self.assertEqual(chart.getpixel((120, 122)), (255, 0, 0))
            self.assertEqual(chart.getpixel((120, 122+4*85)), (0, 255, 0))

    def test_send_failure_closes_usb_before_restoring_original_scene(self):
        events = []
        saved = {'rotation': 270, 'streaming': True, 'page': 'cswap', 'auto': False,
                 'brightness': 100, 'panel_color_order': 'brg', 'panel_calibration': {}}
        def api(changes=None):
            if changes:
                events.append(changes.get('action', 'brightness'))
                return {}
            return saved if not events else {**saved, 'streaming': False}
        class Device:
            def __init__(self): events.append('open')
            def sync(self): return b'turzx_test_0000'
            def descriptor_info(self): return {}
            def brightness(self, value): events.append('usb_brightness')
            def draw_png(self, data): raise RuntimeError('simulated failed transfer')
            def close(self): events.append('close')
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            payload = comparison.encode(Image.new('RGBA', (720, 1280), (0, 0, 0, 255)))
            for ident in ['00']+[p['id'] for p in comparison.PROFILES]:
                (output/f'{ident}-native.png').write_bytes(payload)
            with patch.object(comparison, 'api', api), patch('turzx_libusb.TurzxLibUSB', Device), \
                    patch.object(comparison, 'TurzxWinUSB') as windows:
                windows._check_image.side_effect = lambda *_args: None
                windows.side_effect = Device
                with self.assertRaisesRegex(RuntimeError, 'simulated failed'):
                    comparison.run(output, duration=1)
            self.assertLess(events.index('stop'), events.index('open'))
            self.assertLess(events.index('close'), events.index('start'))


if __name__ == '__main__':
    unittest.main()

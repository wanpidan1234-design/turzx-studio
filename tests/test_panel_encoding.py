"""Verify bounded PNG compression without hardware or account access."""
from io import BytesIO
from pathlib import Path
import random
import sys
import unittest

from PIL import Image, ImageChops
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import encode_panel_png


class PanelEncodingTests(unittest.TestCase):
    def test_image_within_budget_keeps_exact_fast_encoding(self):
        source = Image.new('RGBA', (720, 1280), (127, 211, 83, 255))
        original = BytesIO()
        source.save(original, 'PNG', compress_level=1)
        payload, step = encode_panel_png(source)
        self.assertEqual(payload, original.getvalue())
        self.assertEqual(step, 1)

    def test_noisy_low_bits_compress_with_bounded_error_and_keep_source(self):
        rng = random.Random(44)
        source = Image.frombytes('RGB', (720, 1280), bytes(127 + rng.randrange(3) for _ in range(720*1280*3))).convert('RGBA')
        original = source.tobytes()
        exact = BytesIO()
        source.save(exact, 'PNG', compress_level=9)
        payload, step = encode_panel_png(source, limit=200_000)
        self.assertGreaterEqual(len(exact.getvalue()), 200_000)
        self.assertLess(len(payload), 200_000)
        self.assertIn(step, (2, 3, 4))
        decoded = Image.open(BytesIO(payload))
        self.assertEqual(decoded.size, (720, 1280))
        self.assertEqual(decoded.mode, 'RGBA')
        self.assertEqual(payload[25], 6)
        self.assertEqual(decoded.getchannel('A').getextrema(), (255, 255))
        self.assertLessEqual(max(high for low, high in ImageChops.difference(source, decoded).getextrema()), 2)
        self.assertEqual(source.tobytes(), original)

    def test_impossible_budget_is_rejected(self):
        source = Image.new('RGBA', (720, 1280), (1, 2, 3, 255))
        with self.assertRaisesRegex(ValueError, '1 MiB'):
            encode_panel_png(source, limit=20)


if __name__ == '__main__':
    unittest.main()

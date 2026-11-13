"""Physical tone and circular offset compensation, without USB access."""
import io
import colorsys
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel_calibration import DEFAULT_CALIBRATION, apply_tone, prepare_panel_image, validate_calibration
from server import load_display_preferences


class PanelCalibrationTests(unittest.TestCase):
    def test_ratio_preserving_lift_keeps_hue_saturation_and_lifts_gray(self):
        for rgb in ((204, 120, 82), (120, 65, 36), (240, 160, 72),
                    (64, 128, 192), (0, 128, 0)):
            result = apply_tone(Image.new("RGB", (1, 1), rgb), .45, 1, "preserve_rgb")
            actual = result.getpixel((0, 0))
            original_hsv = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
            actual_hsv = colorsys.rgb_to_hsv(*(c / 255 for c in actual))
            self.assertLess(abs(original_hsv[0]-actual_hsv[0]), .005)
            self.assertLess(abs(original_hsv[1]-actual_hsv[1]), .005)
            self.assertGreater(max(actual), max(rgb))
        for value, expected in ((0, 0), (128, 187), (255, 255)):
            result = apply_tone(Image.new("RGB", (1, 1), (value,)*3), .45, 1, "preserve_rgb")
            self.assertEqual(result.getpixel((0, 0)), (expected,)*3)

    def test_optional_tone_mode_is_validated_and_persisted(self):
        profile = {**DEFAULT_CALIBRATION, "tone_mode": "preserve_rgb", "gamma": .45}
        self.assertEqual(validate_calibration(profile), profile)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"prefs.json"
            path.write_text(json.dumps({"panel_calibration": profile}))
            self.assertEqual(load_display_preferences(path)["panel_calibration"], profile)
        for invalid in ("unknown", None, 0, True):
            with self.assertRaises(ValueError):
                validate_calibration({**profile, "tone_mode": invalid})

    def test_neutral_profile_keeps_rgb_and_forces_opaque_alpha(self):
        source = Image.new("RGBA", (720, 1280), (34, 128, 207, 0))
        result = prepare_panel_image(source, 0, "rgb")
        self.assertEqual(result.getpixel((0, 0)), (34, 128, 207, 255))
        self.assertEqual(source.getpixel((0, 0)), (34, 128, 207, 0))

    def test_native_compensation_cancels_measured_roll_in_every_orientation(self):
        for rotation in (0, 90, 180, 270):
            size = (1280, 720) if rotation in (90, 270) else (720, 1280)
            source = Image.new("RGBA", size, (80, 160, 210, 255))
            for point, color in (((0, 0), "red"), ((size[0]-1, 0), "green"),
                                 ((0, size[1]-1), "blue"), ((size[0]-1, size[1]-1), "white")):
                source.putpixel(point, Image.new("RGBA", (1, 1), color).getpixel((0, 0)))
            expected = source.rotate(rotation, expand=True)
            result = prepare_panel_image(source, rotation, "rgb",
                                         {**DEFAULT_CALIBRATION, "offset_x": -60})
            simulated_panel = ImageChops.offset(result, 60, 0)
            self.assertEqual(simulated_panel.tobytes(), expected.tobytes())
            self.assertEqual(result.size, (720, 1280))

    def test_gamma_lifts_midtones_but_preserves_black_white_and_neutral_gray(self):
        for value, expected in ((0, 0), (64, 111), (128, 169), (255, 255)):
            source = Image.new("RGB", (720, 1280), (value,)*3)
            result = prepare_panel_image(source, 0, "brg",
                                         {**DEFAULT_CALIBRATION, "gamma": .6, "saturation": .8})
            self.assertEqual(result.getpixel((0, 0)), (expected,)*3+(255,))
            output = io.BytesIO()
            result.save(output, "PNG")
            self.assertEqual(output.getvalue()[25], 6)

    def test_invalid_settings_are_rejected_and_not_loaded(self):
        for changes in ({"gamma": float("nan")}, {"gamma": True}, {"gamma": .1},
                        {"saturation": 3}, {"offset_x": 720}, {"offset_y": 1280},
                        {"offset_x": 2.5}, {"offset_y": False}):
            candidate = {**DEFAULT_CALIBRATION, **changes}
            with self.assertRaises(ValueError):
                validate_calibration(candidate)
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/"prefs.json"
                path.write_text(json.dumps({"panel_calibration": candidate, "page": "cswap"}))
                with self.assertLogs("turzx", level="WARNING"):
                    self.assertEqual(load_display_preferences(path), {"page": "cswap"})

    def test_confirmed_profile_loads_without_changing_other_devices_defaults(self):
        profile = {"gamma": .6, "saturation": .8, "offset_x": -60, "offset_y": 0}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"prefs.json"
            path.write_text(json.dumps({"panel_calibration": profile}))
            self.assertEqual(load_display_preferences(path), {"panel_calibration": profile})
        self.assertEqual(DEFAULT_CALIBRATION, {"gamma": 1., "saturation": 1., "offset_x": 0, "offset_y": 0})


if __name__ == "__main__":
    unittest.main()

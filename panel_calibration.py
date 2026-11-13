"""Local, reversible compensation applied only to physical screen frames."""
import math

from PIL import Image, ImageChops, ImageEnhance, ImageMath


DEFAULT_CALIBRATION = {"gamma": 1.0, "saturation": 1.0, "offset_x": 0, "offset_y": 0}


def validate_calibration(value):
    if (not isinstance(value, dict) or not set(DEFAULT_CALIBRATION) <= set(value)
            or set(value) - set(DEFAULT_CALIBRATION) - {"tone_mode"}):
        raise ValueError("面板校准必须包含 gamma、saturation、offset_x、offset_y。")
    if value.get("tone_mode", "channels") not in ("channels", "preserve_rgb"):
        raise ValueError("未知提亮模式。")
    for key, low, high in (("gamma", .3, 2.0), ("saturation", 0, 2.0)):
        number = value[key]
        if type(number) not in (int, float) or not math.isfinite(number) or not low <= number <= high:
            raise ValueError(f"面板校准 {key} 超出范围 {low}–{high}。")
    for key, limit in (("offset_x", 719), ("offset_y", 1279)):
        if type(value[key]) is not int or not -limit <= value[key] <= limit:
            raise ValueError(f"面板校准 {key} 必须在 {-limit}–{limit} 像素内。")
    return dict(value)


def apply_tone(image, gamma, saturation, tone_mode="channels"):
    """Lift RGB values; optionally preserve the ratios instead of desaturating.

    The common gain is derived from max(R,G,B), so its largest output stays
    within 255. This avoids channel clipping without an extra dependency.
    Existing profiles retain their old per-channel curve unless opted in.
    """
    image = image.convert("RGB")
    if saturation != 1:
        image = ImageEnhance.Color(image).enhance(saturation)
    if gamma == 1:
        return image
    if tone_mode == "preserve_rgb":
        channels = image.split()
        peak = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
        gains = [255 * (v / 255) ** gamma / v if v else 0 for v in range(256)]
        gain = peak.point(gains, mode="F")
        corrected = [ImageMath.lambda_eval(lambda a: a["channel"] * a["gain"] + .5,
                                          channel=channel.convert("F"), gain=gain).convert("L")
                     for channel in channels]
        return Image.merge("RGB", corrected)
    lookup = [round(255 * (value / 255) ** gamma) for value in range(256)]
    return image.point(lookup * 3)


def prepare_panel_image(source, rotation, color_order, calibration=None):
    """Preserve source pixels; compensate tone before channel mapping and native roll.

    Offsets are in the physical 720x1280 coordinate system, independent of the
    page orientation. Circular movement compensates observed wrap, not cropping.
    """
    settings = validate_calibration(DEFAULT_CALIBRATION if calibration is None else calibration)
    expected = (1280, 720) if rotation in (90, 270) else (720, 1280)
    if rotation not in (0, 90, 180, 270) or source.size != expected:
        raise ValueError(f"画面尺寸 {source.size} 与方向 {rotation} 不匹配。")
    if color_order not in ("rgb", "bgr", "brg"):
        raise ValueError("未知面板色序。")
    image = apply_tone(source, settings["gamma"], settings["saturation"],
                       settings.get("tone_mode", "channels"))
    image = image.convert("RGBA")
    image.putalpha(255)
    if color_order != "rgb":
        red, green, blue, alpha = image.split()
        image = Image.merge("RGBA", (blue, green, red, alpha) if color_order == "bgr"
                            else (blue, red, green, alpha))
    if rotation:
        image = image.rotate(rotation, expand=True)
    if settings["offset_x"] or settings["offset_y"]:
        image = ImageChops.offset(image, settings["offset_x"], settings["offset_y"])
    return image

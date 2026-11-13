"""Bounded, reversible colour comparison. No firmware or persistent USB writes.

Build offline, then explicitly run. The user requested this low-rate slideshow.
Normal rendering releases USB before this process opens it. On exit the handle
is closed before the original scene resumes. Touch OUTPUT/stop to finish early.
"""
import argparse
import io
import json
import os
from pathlib import Path
import re
import signal
import time
import urllib.request

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont, ImageOps

from panel_calibration import prepare_panel_image
from turzx_usb import TurzxWinUSB, MAX_IMAGE_BYTES

ROOT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8765"
PROFILES = [
    {"id": "01", "label": "当前效果", "gamma": .6, "saturation": .8, "css": True},
    {"id": "02", "label": "去掉图片滤镜", "gamma": .6, "saturation": .8, "css": False},
    {"id": "03", "label": "保持原图色彩 · 较亮", "gamma": .6, "saturation": 1., "css": False},
    {"id": "04", "label": "保持原图色彩 · 中等", "gamma": .75, "saturation": 1., "css": False},
    {"id": "05", "label": "保持原图色彩 · 轻微提亮", "gamma": .9, "saturation": 1., "css": False},
    {"id": "06", "label": "原图色彩 · 不提亮", "gamma": 1., "saturation": 1., "css": False},
]
COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
          (0, 255, 255), (255, 0, 255), (204, 120, 82), (240, 192, 160)]
NAMES = ["红", "绿", "蓝", "黄", "青", "品红", "橘棕", "肤色"]
ORDERS = {"A": "rgb", "B": "rbg", "C": "grb", "D": "gbr", "E": "brg", "F": "bgr"}


def font(size):
    for name in ("/System/Library/Fonts/STHeiti Light.ttc", "C:/Windows/Fonts/msyh.ttc",
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if Path(name).is_file():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default(size=size)


def api(changes=None):
    data = None if changes is None else json.dumps(changes).encode()
    request = urllib.request.Request(BASE + ("/api/state" if data is None else "/api/control"),
                                     data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def save_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def encode(image):
    stream = io.BytesIO()
    image.save(stream, "PNG", compress_level=6)
    payload = stream.getvalue()
    TurzxWinUSB._check_image(payload, "PNG")
    if image.getchannel("A").getextrema() != (255, 255):
        raise ValueError("Every calibration pixel must be opaque")
    return payload


def scene(profile):
    image = Image.new("RGB", (1280, 720), "#fffaf5")
    draw = ImageDraw.Draw(image)
    draw.text((28, 18), f'{profile["id"]}   {profile["label"]}', font=font(34), fill="#292929")
    draw.text((880, 25), "12 秒换图 · 记录编号", font=font(22), fill="#555555")
    asset = Image.open(ROOT / "web/assets/claude/claude-v2-landscape.png").convert("RGB")
    # Source artwork, without page opacity/filter; 01 reproduces that old layer.
    crop = asset.crop((int(asset.width * .60), 0, asset.width, asset.height))
    crop = ImageOps.fit(crop, (470, 450))
    if profile["css"]:
        # CSS saturate() uses Rec.709 luma (not Pillow's Rec.601).
        s = .7
        weights = (.2126, .7152, .0722)
        matrix = tuple(value for row in range(3) for value in
                       [*((1-s)*weights[col] + (s if row == col else 0) for col in range(3)), 0])
        crop = crop.convert("RGB", matrix)
        crop = ImageEnhance.Brightness(crop).enhance(1.08)
        crop = Image.blend(Image.new("RGB", crop.size, "#fffaf5"), crop, .72)
    image.paste(crop, (790, 88))
    draw.text((30, 100), "校准样例", font=font(24), fill="#49372b")
    for n, (label, value) in enumerate((("5h", "36%"), ("7d", "62%"), ("Fable", "18%"))):
        x = 30+n*248
        draw.rounded_rectangle((x, 150, x+230, 420), radius=16, fill="#fffdf9", outline="#dfd7cd", width=2)
        draw.text((x+20, 174), label, font=font(28), fill="#49372b")
        draw.text((x+20, 230), value, font=font(56), fill="#a94d31")
        draw.text((x+20, 305), "已使用", font=font(20), fill="#716860")
        draw.rectangle((x+20, 353, x+205, 359), fill="#e8dacb")
        draw.rectangle((x+20, 353, x+90, 359), fill="#bb674c")
        draw.text((x+20, 380), "2 小时后重置", font=font(19), fill="#49372b")
    draw.text((30, 451), "看肤色、橘棕发色和白色衣服是否自然", font=font(24), fill="#333333")
    draw.text((30, 494), "灰阶应保持灰色，不能偏红、偏绿或偏蓝", font=font(23), fill="#555555")
    for i, (color, name) in enumerate(zip(COLORS, NAMES)):
        x = 24 + i*154
        draw.rectangle((x, 550, x+145, 603), fill=color)
        draw.text((x+45, 608), name, font=font(20), fill="#333333")
    for i, level in enumerate((0, 16, 32, 64, 96, 128, 160, 192, 224, 240, 248, 255)):
        x = 24+i*103
        draw.rectangle((x, 645, x+98, 710), fill=(level,)*3)
        draw.text((x+20, 665), str(level), font=font(18), fill="white" if level<128 else "black")
    return image


def channel_chart():
    image = Image.new("RGB", (1280, 720), "#eeeeee")
    draw = ImageDraw.Draw(image)
    draw.text((25, 15), "00   色序核对：哪一行与色名一致？", font=font(32), fill="black")
    for i, name in enumerate(NAMES):
        draw.text((120+i*142, 70), name, font=font(24), fill="black")
    for row, (letter, order) in enumerate(ORDERS.items()):
        y = 112+row*85
        draw.text((28, y+14), letter, font=font(38), fill="black")
        for col, color in enumerate(COLORS):
            mapped = tuple(color["rgb".index(c)] for c in order)
            draw.rectangle((100+col*142, y, 232+col*142, y+66), fill=mapped)
    draw.text((24, 638), "已选色序为 E。白色应白、灰色应灰、黑色应黑。", font=font(23), fill="black")
    for i, level in enumerate((0, 64, 128, 192, 255)):
        draw.rectangle((24+i*248, 678, 259+i*248, 715), fill=(level,)*3)
    return image


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    chart = channel_chart()
    # Each row already has its own channel order: never map BRG a second time.
    native = ImageChops.offset(chart.convert("RGBA").rotate(270, expand=True), -60, 0)
    (output/"00-native.png").write_bytes(encode(native))
    chart.save(output/"00-reference.png")
    for profile in PROFILES:
        source = scene(profile)
        settings = {"gamma": profile["gamma"], "saturation": profile["saturation"], "offset_x": -60, "offset_y": 0}
        native = prepare_panel_image(source, 270, "brg", settings)
        payload = encode(native)
        (output/f'{profile["id"]}-native.png').write_bytes(payload)
        source.save(output/f'{profile["id"]}-reference.png')
        manifest.append({**profile, "panel_color_order": "brg", "panel_calibration": settings,
                         "bytes": len(payload), "max_bytes": MAX_IMAGE_BYTES})
    save_json(output/"profiles.json", manifest)
    return manifest


def run(output, duration=900, interval=12):
    if not 1 <= duration <= 1800 or not 5 <= interval <= 60:
        raise ValueError("Comparison duration 1–1800 seconds; interval 5–60 seconds")
    # Preflight every frame before stopping a working renderer.
    frames = [(ident, (output/f"{ident}-native.png").read_bytes()) for ident in ["00"]+[p["id"] for p in PROFILES]]
    for _, payload in frames:
        TurzxWinUSB._check_image(payload, "PNG")
    saved = api()
    if saved["rotation"] != 270:
        raise ValueError("This device-specific comparison requires the confirmed 270 degree orientation")
    if (output/"stop").exists():
        raise ValueError("Remove the previous stop marker before starting a new comparison")
    device = None
    stopped = False
    external_start = False
    state = {"running": True, "frames": 0, "error": None, "started": time.time(), "pid": os.getpid(), "interval": interval}
    save_json(output/"saved-state.json", {k:saved[k] for k in ("page", "auto", "streaming", "brightness", "panel_color_order", "panel_calibration")})
    try:
        api({"action": "stop"})
        stopped = True
        if os.name == "nt":
            device = TurzxWinUSB()
        else:
            from turzx_libusb import TurzxLibUSB
            device = TurzxLibUSB()
        sync = device.sync()
        versions = re.findall(rb"[ -~]{6,}", sync)
        state["sync_text"] = [v.decode("ascii") for v in versions]
        state["device"] = device.descriptor_info()
        device.brightness(100)
        deadline = time.monotonic()+duration
        index = 0
        while time.monotonic() < deadline and not (output/"stop").exists():
            # Respect a user who resumes the normal app while comparison runs.
            if api()["streaming"]:
                external_start = True
                break
            ident, payload = frames[index % len(frames)]
            device.draw_png(payload)
            state.update(current=ident, frames=state["frames"]+1, last_frame=time.time(), bytes=len(payload))
            save_json(output/"status.json", state)
            print(json.dumps({k:state[k] for k in ("current", "frames", "bytes")}), flush=True)
            until = min(deadline, time.monotonic()+interval)
            while time.monotonic()<until and not (output/"stop").exists():
                time.sleep(.2)
            index += 1
    except BaseException as exc:
        state["error"] = str(exc)
        raise
    finally:
        try:
            if device is not None:
                device.close()
        finally:
            state.update(running=False, finished=time.time())
            if stopped and not external_start and saved["streaming"]:
                try:
                    api({"action": "start", "page": saved["page"], "auto": saved["auto"]})
                    api({"brightness": saved["brightness"] if saved["brightness"] is not None else 100})
                    state["restored"] = True
                except Exception as exc:
                    state["restore_error"] = str(exc)
            save_json(output/"status.json", state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "run"))
    parser.add_argument("--output", type=Path, default=ROOT/"runtime/color-comparison")
    parser.add_argument("--duration", type=int, default=900)
    parser.add_argument("--interval", type=int, default=12)
    args = parser.parse_args()
    if args.action == "build":
        print(json.dumps(build(args.output), ensure_ascii=False, indent=2))
    else:
        def finish(_signum, _frame):
            raise KeyboardInterrupt("Comparison interrupted")
        signal.signal(signal.SIGTERM, finish)
        run(args.output, args.duration, args.interval)

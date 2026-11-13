"""Local-only TURZX Studio bridge. No firmware or persistent screen settings are written."""
from __future__ import annotations

import argparse
from collections import deque
import copy
import io
import json
import logging
import math
import mimetypes
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from PIL import Image
from telemetry import Telemetry
if os.name == "nt":
    from turzx_usb import TurzxWinUSB, enumerate_device_paths
else:
    from turzx_libusb import TurzxLibUSB as TurzxWinUSB, enumerate_device_paths
from animation_state import AnimationState
from subscription import SubscriptionMonitor
from claude_subscription import ClaudeMonitor
from panel_calibration import DEFAULT_CALIBRATION, validate_calibration, prepare_panel_image

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
RUNTIME = ROOT / "runtime"
PAGES = ("system", "network", "clock", "focus", "ambient", "openai", "claude", "cswap", "media", "guide", "calibrate")
SUBSCRIPTION_VIEWS = ("overview", "billing", "entitlements")
SUBSCRIPTION_BACKGROUNDS = ("none", "it", "anime", "dragon")
CLAUDE_BACKGROUNDS = ("stand", "thought", "greeting", "floral", "celestial", "atelier", "botanical", "paperland", "glasswave", "none")
IMAGE_APPEARANCE_DEFAULTS = {"image_brightness": 112, "image_saturation": 85, "image_fade": 12}
IMAGE_APPEARANCE_BOUNDS = {"image_brightness": (80, 140), "image_saturation": (50, 120), "image_fade": (0, 50)}
SCENE_PREFERENCES_DEFAULTS = {
    "auto": False, "interval": 20, "note": "把注意力留给真正重要的事。",
    "subscription_view": "overview", "subscription_auto": False, "subscription_bucket": "codex",
    "focus_duration": 1500,
    "animation": {"preset": "orbit", "speed": 1.0, "detail": "balanced",
                  "show_clock": True, "paused": False, "seed": 52},
}
DISPLAY_PREFERENCES = ("subscription_background", "subscription_background_transparency", "rotation", "page", "fps", "resume_streaming", "brightness", "panel_color_order", "panel_calibration", "claude_background", *IMAGE_APPEARANCE_DEFAULTS, *SCENE_PREFERENCES_DEFAULTS)
LOG = logging.getLogger("turzx")


def load_display_preferences(path):
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        LOG.warning("Unable to read display preferences; using defaults.")
        return {}
    if not isinstance(saved, dict):
        return {}
    result = {}
    for key in ("auto", "subscription_auto"):
        if type(saved.get(key)) is bool:
            result[key] = saved[key]
    for key, low, high in (("interval", 5, 120), ("focus_duration", 60, 10800)):
        value = saved.get(key)
        if type(value) is int and low <= value <= high:
            result[key] = value
    for key, low, high in (("note", 0, 160), ("subscription_bucket", 1, 100)):
        value = saved.get(key)
        if isinstance(value, str) and low <= len(value) <= high:
            result[key] = value
    if saved.get("subscription_view") in SUBSCRIPTION_VIEWS:
        result["subscription_view"] = saved["subscription_view"]
    if "animation" in saved:
        try:
            AnimationState.validate(saved["animation"])
            result["animation"] = {**SCENE_PREFERENCES_DEFAULTS["animation"], **saved["animation"]}
        except ValueError:
            LOG.warning("Invalid animation preferences; using defaults.")
    brightness = saved.get("brightness")
    if type(brightness) is int and 0 <= brightness <= 100:
        result["brightness"] = brightness
    if saved.get("claude_background") in CLAUDE_BACKGROUNDS:
        result["claude_background"] = saved["claude_background"]
    for key, (low, high) in IMAGE_APPEARANCE_BOUNDS.items():
        value = saved.get(key)
        if type(value) is int and low <= value <= high:
            result[key] = value
    if saved.get("subscription_background") in SUBSCRIPTION_BACKGROUNDS:
        result["subscription_background"] = saved["subscription_background"]
    value = saved.get("subscription_background_transparency")
    if type(value) is int and 0 <= value <= 100:
        result["subscription_background_transparency"] = value
    if saved.get("page") in PAGES:
        result["page"] = saved["page"]
    for key, choices in (("rotation", (0, 90, 180, 270)), ("fps", (1, 2, 5, 10))):
        if type(saved.get(key)) is int and saved[key] in choices:
            result[key] = saved[key]
    if type(saved.get("resume_streaming")) is bool:
        result["resume_streaming"] = saved["resume_streaming"]
    if saved.get("panel_color_order") in ("rgb", "bgr", "brg"):
        result["panel_color_order"] = saved["panel_color_order"]
    if "panel_calibration" in saved:
        try:
            result["panel_calibration"] = validate_calibration(saved["panel_calibration"])
        except ValueError:
            LOG.warning("Invalid panel calibration; using defaults.")
    return result


def save_display_preferences(path, state):
    state = {"brightness": None, "claude_background": "stand", **IMAGE_APPEARANCE_DEFAULTS,
             **copy.deepcopy(SCENE_PREFERENCES_DEFAULTS), **state}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="display-preferences-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            json.dump({key: state[key] for key in DISPLAY_PREFERENCES}, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class SessionPaused(Exception):
    """Normal cancellation, not a device error."""


def encode_panel_png(image, limit=1024 * 1024):
    """Keep exact pixels when possible, otherwise bound RGB rounding to ±2.

    Browser scaling and colour controls can increase PNG entropy even when the
    wallpaper asset fits. The final fallback never changes alpha or dimensions.
    """
    for compression in (1, 9):
        stream = io.BytesIO()
        image.save(stream, "PNG", compress_level=compression)
        payload = stream.getvalue()
        if len(payload) < limit:
            return payload, 1
    for step in (2, 3, 4):
        lookup = [min(255, round(value / step) * step) for value in range(256)]
        rounded = image.point(lookup * 3 + list(range(256)))
        stream = io.BytesIO()
        rounded.save(stream, "PNG", compress_level=9)
        payload = stream.getvalue()
        if len(payload) < limit:
            return payload, step
    raise ValueError("RGBA PNG 超过设备单帧 1 MiB 限制，请降低画面复杂度。")


class Studio:
    def __init__(self, port: int):
        self.port = port
        self.state_lock = threading.RLock()
        self.io_lock = threading.RLock()
        self.lifecycle_lock = threading.RLock()
        self.device = None
        self.renderer = None
        self.renderer_log = None
        self.token = secrets.token_urlsafe(32)
        self.focus_deadline = None
        self.last_page_at = time.monotonic()
        self.session_started = None
        self.session_id = 0
        self.stopping = threading.Event()
        self.metrics = Telemetry()
        self.motion = AnimationState()
        self.subscription = SubscriptionMonitor()
        self.claude = ClaudeMonitor()
        self.last_subscription_page_at = time.monotonic()
        self.frame_times = deque(maxlen=30)
        self.state = {
            **IMAGE_APPEARANCE_DEFAULTS,
            **copy.deepcopy(SCENE_PREFERENCES_DEFAULTS),
            "claude_background": "stand",
            "page": "system", "rotation": 270, "fps": 2,
            "streaming": False, "connected": False, "resume_streaming": False,
            "error": None, "brightness": None, "panel_color_order": "rgb",
            "panel_calibration": dict(DEFAULT_CALIBRATION),
            "stats": {"frames": 0, "last_ms": None, "bytes": 0,
                      "effective_fps": 0, "last_ack": None},
            "device": {"name": "TURZX 5.2", "width": 1280, "height": 720,
                       "vid": "1CBE", "pid": "0050"},
            "focus": {"duration": 1500, "remaining": 1500, "running": False},
            "subscription_background": "none",
            "subscription_background_transparency": 25,
        }
        self.preferences_path = RUNTIME / "display-preferences.json"
        self.state.update(load_display_preferences(self.preferences_path))
        self.motion.update(self.state["animation"])
        self.state["focus"].update(duration=self.state["focus_duration"], remaining=self.state["focus_duration"])
        self.reconnect_at = 0.0
        self.reconnect_delay = 2.0
        self.clock = threading.Thread(target=self._clock, name="studio-clock", daemon=True)
        self.clock.start()

    def snapshot(self):
        with self.state_lock:
            result = copy.deepcopy(self.state)
            result["animation"] = self.motion.snapshot()
            result["subscription"] = self.subscription.snapshot()
            result["claude"] = self.claude.snapshot()
            if self.focus_deadline is not None:
                result["focus"]["remaining"] = max(0, math.ceil(self.focus_deadline-time.monotonic()))
            return result

    def _clock(self):
        while not self.stopping.wait(0.2):
            now = time.monotonic()
            with self.state_lock:
                if self.focus_deadline is not None and now >= self.focus_deadline:
                    self.focus_deadline = None
                    self.state["focus"].update(remaining=0, running=False)
                if self.state["auto"] and now-self.last_page_at >= self.state["interval"]:
                    i = PAGES.index(self.state["page"])
                    next_page = PAGES[(i+1) % len(PAGES)]
                    try:
                        save_display_preferences(self.preferences_path, {**self.state, "page": next_page})
                    except OSError:
                        LOG.warning("Unable to save auto-rotation page; keeping current page.")
                    else:
                        self.state["page"] = next_page
                    self.last_page_at = now
                if self.state["page"] == "openai" and self.state["subscription_auto"] and now-self.last_subscription_page_at >= 15:
                    index = SUBSCRIPTION_VIEWS.index(self.state["subscription_view"])
                    next_view = SUBSCRIPTION_VIEWS[(index+1) % len(SUBSCRIPTION_VIEWS)]
                    try:
                        save_display_preferences(self.preferences_path, {**self.state, "subscription_view": next_view})
                    except OSError:
                        LOG.warning("Unable to save subscription view; keeping current view.")
                    else:
                        self.state["subscription_view"] = next_view
                    self.last_subscription_page_at = now
            renderer = self.renderer
            generation = self.session_id
            if renderer and renderer.poll() is not None and renderer is self.renderer and self.snapshot()["streaming"]:
                self.fail(f"页面渲染进程已退出（{renderer.returncode}），请查看 runtime/renderer.log 后重新开始。", generation)

    def _remember_streaming(self, enabled):
        with self.state_lock:
            save_display_preferences(self.preferences_path, {**self.state, "resume_streaming": enabled})
            self.state["resume_streaming"] = enabled

    def maintain_connection(self):
        while not self.stopping.is_set():
            self.try_resume_streaming()
            self.stopping.wait(2)

    def try_resume_streaming(self):
        with self.lifecycle_lock:
            if self.stopping.is_set() or not self.state["resume_streaming"] or self.state["streaming"]:
                return
            if time.monotonic() < self.reconnect_at:
                return
            self.reconnect_at = time.monotonic() + 2
            try:
                # SetupAPI enumeration does not open or write to the device.
                paths = enumerate_device_paths()
                if len(paths) != 1:
                    with self.state_lock:
                        self.state["error"] = ("等待副屏重新连接，接入后将自动恢复投屏。" if not paths
                                               else "检测到多块副屏，无法自动选择设备。")
                    return
                self.start()
            except Exception as exc:
                with self.state_lock:
                    self.state["error"] = str(exc)
                LOG.warning("Display reconnect failed; retrying with backoff: %s", exc)
            # A renderer launch alone does not prove recovery. Only a successful
            # physical frame resets backoff, preventing a render/crash hot loop.
            with self.state_lock:
                self.reconnect_at = time.monotonic() + self.reconnect_delay
                self.reconnect_delay = min(30.0, self.reconnect_delay * 2)

    def start(self):
        with self.lifecycle_lock:
            if self.stopping.is_set():
                raise SessionPaused("工作台正在关闭。")
            if self.snapshot()["streaming"]:
                return
            self.stop()
            with self.state_lock:
                self.session_id += 1
                self.token = secrets.token_urlsafe(32)
            try:
                with self.io_lock:
                    self.device = TurzxWinUSB()
                    info = self.device.descriptor_info()
                    self.device.sync()
                    # Backlight is a volatile device setting; replay the user's
                    # saved value on every connection before rendering frames.
                    brightness = self.state["brightness"]
                    if brightness is not None:
                        self.device.brightness(brightness)
                (RUNTIME / "usb-descriptors.json").write_text(
                    json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
                node = shutil.which("node")
                if not node:
                    raise RuntimeError("找不到 Node.js，无法渲染页面。")
                env = os.environ.copy()
                env["TURZX_RENDER_TOKEN"] = self.token
                self.renderer_log = (RUNTIME / "renderer.log").open("a", encoding="utf-8")
                with self.state_lock:
                    self.state.update(streaming=True, connected=True, error=None)
                    self.state["stats"] = {"frames": 0, "last_ms": None, "bytes": 0,
                                           "effective_fps": 0, "last_ack": None}
                    self.session_started = time.monotonic()
                    self.frame_times.clear()
                self.renderer = subprocess.Popen(
                    [node, str(ROOT / "renderer.cjs"), f"http://127.0.0.1:{self.port}"],
                    cwd=ROOT, env=env, stdout=self.renderer_log, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                self._remember_streaming(True)
                LOG.info("Started display session; renderer pid=%s", self.renderer.pid)
            except Exception as exc:
                self.stop()
                with self.state_lock:
                    self.state["error"] = str(exc)
                raise

    def stop(self, expected_session=None, *, remember=False):
        with self.lifecycle_lock:
            if expected_session is not None and expected_session != self.session_id:
                return
            with self.state_lock:
                self.state["streaming"] = False
            proc = self.renderer
            if proc:
                # Renderer polls state and exits, closing its own Chromium first.
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Terminate only our own process tree, never unrelated browsers.
                    import psutil
                    try:
                        parent = psutil.Process(proc.pid)
                        children = parent.children(recursive=True)
                        for child in reversed(children):
                            try:
                                child.terminate()
                            except psutil.Error:
                                pass
                        parent.terminate()
                        psutil.wait_procs(children+[parent], timeout=2)
                    except psutil.Error:
                        pass
                self.renderer = None
            if self.renderer_log:
                self.renderer_log.close()
                self.renderer_log = None
            with self.io_lock:
                if self.device:
                    self.device.close()
                    self.device = None
            with self.state_lock:
                self.state["connected"] = False
            if remember:
                self._remember_streaming(False)
            LOG.info("Display session stopped; last frame retained")

    def fail(self, message, expected_session):
        with self.state_lock:
            if expected_session != self.session_id or not self.state["streaming"]:
                return
            self.state.update(error=message, streaming=False)
        LOG.error("Session failure: %s", message)
        # Never wait for the renderer from a request it is waiting on.
        threading.Thread(target=self.stop, args=(expected_session,), daemon=True).start()

    def control(self, changes):
        if not isinstance(changes, dict):
            raise ValueError("请求必须为 JSON 对象。")
        allowed = {"panel_calibration", "panel_color_order", "page", "rotation", "fps", "auto", "interval", "note", "brightness", "action", "focus_duration", "animation",
                   "subscription_view", "subscription_auto", "subscription_bucket", "subscription_background", "subscription_background_transparency"}
        allowed.add("claude_background")
        allowed.update(IMAGE_APPEARANCE_DEFAULTS)
        if set(changes)-allowed:
            raise ValueError("存在不支持的设置项。")
        action = changes.get("action")
        if action not in (None, "start", "stop", "focus_start", "focus_pause", "focus_reset", "shutdown", "subscription_refresh", "claude_refresh"):
            raise ValueError("不支持的操作。")
        for key, value in changes.items():
            if key == "claude_background" and value not in CLAUDE_BACKGROUNDS:
                raise ValueError("未知 Claude 背景。")
            if key in IMAGE_APPEARANCE_BOUNDS:
                low, high = IMAGE_APPEARANCE_BOUNDS[key]
                if type(value) is not int or not low <= value <= high:
                    raise ValueError(f"{key} 应为 {low} 到 {high} 的整数。")
            if key == "panel_calibration":
                validate_calibration(value)
            if key == "panel_color_order" and value not in ("rgb", "bgr", "brg"):
                raise ValueError("屏幕颜色顺序应为 rgb、bgr 或 brg。")
            if key == "subscription_background_transparency" and (type(value) is not int or not 0 <= value <= 100):
                raise ValueError("背景透明度应为 0 到 100 的整数。")
            if key == "subscription_background" and value not in SUBSCRIPTION_BACKGROUNDS:
                raise ValueError("未知订阅背景。")
            if key == "subscription_view" and value not in SUBSCRIPTION_VIEWS:
                raise ValueError("未知订阅页面。")
            if key == "subscription_auto" and type(value) is not bool:
                raise ValueError("订阅详情轮播应为布尔值。")
            if key == "subscription_bucket" and (not isinstance(value, str) or not 1 <= len(value) <= 100):
                raise ValueError("无效的额度分组。")
            if key == "animation":
                AnimationState.validate(value)
            if key == "page" and value not in PAGES:
                raise ValueError("未知页面。")
            if key == "rotation" and (type(value) is not int or value not in (0, 90, 180, 270)):
                raise ValueError("方向应为 0/90/180/270。")
            if key == "fps" and (type(value) is not int or value not in (1, 2, 5, 10)):
                raise ValueError("发送帧率应为 1/2/5/10。")
            if key == "auto" and type(value) is not bool:
                raise ValueError("轮播设置应为布尔值。")
            if key in ("interval", "brightness", "focus_duration"):
                bounds = {"interval": (5, 120), "brightness": (0, 100), "focus_duration": (60, 10800)}[key]
                if type(value) is not int or not bounds[0] <= value <= bounds[1]:
                    raise ValueError(f"{key} 超出范围 {bounds}。")
            if key == "note" and (not isinstance(value, str) or len(value) > 160):
                raise ValueError("便签最长 160 字。")
        if "brightness" in changes:
            with self.io_lock:
                if not self.device:
                    raise ValueError("请先开始推送，再调整亮度。")
                self.device.brightness(changes["brightness"])
        with self.state_lock:
            if any(key in changes for key in DISPLAY_PREFERENCES):
                # Persist before publishing the state; a failed write must not
                # report a setting that will be lost after a restart.
                preferences = {**self.state, **changes}
                if "animation" in changes:
                    preferences["animation"] = {**self.motion.settings, **changes["animation"]}
                save_display_preferences(self.preferences_path, preferences)
            if "animation" in changes:
                self.motion.update(changes["animation"])
                self.state["animation"] = dict(self.motion.settings)
            for key in ("panel_calibration", "panel_color_order", "page", "rotation", "fps", "auto", "interval", "note", "brightness",
                        "subscription_view", "subscription_auto", "subscription_bucket", "subscription_background", "subscription_background_transparency", "claude_background", *IMAGE_APPEARANCE_DEFAULTS):
                if key in changes:
                    self.state[key] = changes[key]
            if "page" in changes or "auto" in changes:
                self.last_page_at = time.monotonic()
            if any(key in changes for key in ("page", "subscription_view", "subscription_auto")):
                self.last_subscription_page_at = time.monotonic()
            if "focus_duration" in changes:
                self.state["focus_duration"] = changes["focus_duration"]
                self.state["focus"].update(duration=changes["focus_duration"], remaining=changes["focus_duration"], running=False)
                self.focus_deadline = None
            f = self.state["focus"]
            if action == "focus_start" and not f["running"]:
                if f["remaining"] <= 0:
                    f["remaining"] = f["duration"]
                f["running"] = True
                self.focus_deadline = time.monotonic()+f["remaining"]
            elif action == "focus_pause":
                if self.focus_deadline is not None:
                    f["remaining"] = max(0, math.ceil(self.focus_deadline-time.monotonic()))
                f["running"] = False
                self.focus_deadline = None
            elif action == "focus_reset":
                f.update(remaining=f["duration"], running=False)
                self.focus_deadline = None
        if action == "start":
            self.start()
        elif action == "stop":
            self.stop(remember=True)
        elif action == "shutdown":
            # Release USB while HTTP is still serving the renderer's final poll.
            # A completed shutdown request must not leave the next launch racing
            # an old process that still owns the panel.
            self.stopping.set()
            self.stop()
        elif action == "subscription_refresh":
            self.subscription.refresh()
        elif action == "claude_refresh":
            self.claude.refresh()
        return self.snapshot()

    def frame(self, data, rotation, expected_session, render_ms=None, capture="screenshot"):
        started = time.perf_counter()
        if expected_session != self.session_id or not self.snapshot()["streaming"]:
            raise SessionPaused("推送已暂停。")
        image = Image.open(io.BytesIO(data))
        frame_settings = self.snapshot()
        color_order = frame_settings["panel_color_order"]
        image = prepare_panel_image(image, rotation, color_order,
                                    frame_settings.get("panel_calibration"))
        payload, quantization_step = encode_panel_png(image)
        kind = "png"
        encode_ms = (time.perf_counter()-started)*1000
        with self.io_lock:
            if expected_session != self.session_id or not self.device or not self.snapshot()["streaming"]:
                raise SessionPaused("推送已暂停。")
            usb_started = time.perf_counter()
            if kind == "png":
                reply = self.device.draw_png(payload)
            else:
                reply = self.device.draw_jpeg(payload)
            ms = (time.perf_counter()-usb_started)*1000
        now = time.time()
        with self.state_lock:
            s = self.state["stats"]
            s["frames"] += 1
            s["last_ms"] = round(ms, 2)
            s["bytes"] += len(payload)
            s["last_ack"] = now
            self.reconnect_delay = 2.0
            self.reconnect_at = 0.0
            tick = time.monotonic()
            self.frame_times.append(tick)
            s["effective_fps"] = round((len(self.frame_times)-1)/max(.01, tick-self.frame_times[0]), 2) if len(self.frame_times)>1 else 0
            s["session_fps"] = round(s["frames"]/max(.01, tick-self.session_started), 2)
            s.update(encode_ms=round(encode_ms, 2), render_ms=render_ms, capture=capture,
                     last_frame_bytes=len(payload), quantization_step=quantization_step)
        record = {"time": now, "page": self.snapshot()["page"], "rotation": rotation,
                  "bytes": len(payload), "usb_ms": round(ms, 3), "format": kind, "panel_color_order": color_order,
                  "panel_calibration": frame_settings.get("panel_calibration"),
                  "quantization_step": quantization_step,
                  "animation": self.motion.settings["preset"], "encode_ms": round(encode_ms, 3),
                  "render_ms": render_ms, "capture": capture,
                  "total_ms": round((time.perf_counter()-started)*1000, 3),
                  "ack_prefix": bytes(reply)[:16].hex()}
        with (RUNTIME / "frames.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record)+"\n")
        return {"ok": True, "ms": round(ms, 2), "bytes": len(payload)}

    def close(self):
        self.stopping.set()
        self.stop()
        self.metrics.close()
        self.subscription.close()
        self.claude.close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    @property
    def app(self):
        return self.server.app

    def log_message(self, fmt, *args):
        if not str(args[0]).startswith(("GET /api/", "POST /api/frame")):
            LOG.info(fmt, *args)

    def send(self, code, body, content_type="application/json; charset=utf-8", cache_control="no-store"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-ancestors 'self'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def valid_host(self):
        return self.headers.get("Host") in (f"127.0.0.1:{self.app.port}", f"localhost:{self.app.port}")

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, {"error": "Invalid host"})
        route = urlsplit(self.path).path
        if route == "/api/state":
            return self.send(200, self.app.snapshot())
        if route == "/api/metrics":
            return self.send(200, self.app.metrics.snapshot())
        if route == "/api/subscription":
            return self.send(200, self.app.subscription.snapshot())
        if route == "/api/claude":
            return self.send(200, self.app.claude.snapshot())
        if route == "/api/info":
            return self.send(200, json.loads((ROOT / "device-info.json").read_text(encoding="utf-8")))
        if route.startswith("/api/"):
            return self.send(404, {"error": "Unknown endpoint"})
        name = unquote(route).lstrip("/") or "index.html"
        path = (WEB / name).resolve()
        if not path.is_relative_to(WEB.resolve()) or not path.is_file():
            return self.send(404, {"error": "Not found"})
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if mime.startswith("text/") or mime in ("application/javascript", "application/json"):
            mime += "; charset=utf-8"
        # Only public, fixed wallpaper assets are reusable across display frames.
        wallpaper = path.parent == WEB / "assets" / "subscription" and path.suffix == ".png"
        return self.send(200, path.read_bytes(), mime, "private, max-age=3600" if wallpaper else "no-store")

    def do_POST(self):
        if not self.valid_host():
            return self.send(403, {"error": "Invalid host"})
        origin = self.headers.get("Origin")
        allowed = (f"http://127.0.0.1:{self.app.port}", f"http://localhost:{self.app.port}")
        if origin is not None and origin not in allowed:
            return self.send(403, {"error": "仅允许本机同源操作。"})
        route = urlsplit(self.path).path
        try:
            size = int(self.headers.get("Content-Length", "0"))
            limit = 8*1024*1024 if route == "/api/frame" else 8192
            if not 0 < size <= limit:
                raise ValueError("请求内容长度无效。")
            if route == "/api/frame":
                with self.app.state_lock:
                    generation = self.app.session_id
                    if not secrets.compare_digest(self.headers.get("X-Renderer-Token", ""), self.app.token):
                        return self.send(403, {"error": "Invalid renderer token"})
                data = self.rfile.read(size)
                rotation = int(self.headers.get("X-Frame-Rotation", "270"))
                if rotation not in (0, 90, 180, 270):
                    raise ValueError("Invalid frame rotation")
                render_ms = float(self.headers.get("X-Frame-Render-Ms", "0"))
                if not math.isfinite(render_ms) or not 0 <= render_ms <= 60000:
                    raise ValueError("Invalid frame timing")
                capture = self.headers.get("X-Frame-Capture", "screenshot")
                if capture not in ("canvas", "screenshot"):
                    raise ValueError("Invalid frame capture source")
                try:
                    return self.send(200, self.app.frame(data, rotation, generation, render_ms, capture))
                except SessionPaused as exc:
                    return self.send(409, {"error": str(exc), "cancelled": True})
                except Exception as exc:
                    self.app.fail(str(exc), generation)
                    return self.send(503, {"error": str(exc)})
            if route == "/api/control":
                if not self.headers.get("Content-Type", "").startswith("application/json"):
                    return self.send(415, {"error": "Expected application/json"})
                body = json.loads(self.rfile.read(size))
                state = self.app.control(body)
                self.send(200, state)
                if body.get("action") == "shutdown":
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            return self.send(404, {"error": "Unknown endpoint"})
        except (ValueError, json.JSONDecodeError) as exc:
            return self.send(400, {"error": str(exc)})
        except Exception as exc:
            LOG.exception("Control failed")
            return self.send(503, {"error": str(exc)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    RUNTIME.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(RUNTIME / "server.log", encoding="utf-8"), logging.StreamHandler()])
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    app = Studio(args.port)
    server.app = app
    (RUNTIME / "server.pid").write_text(str(os.getpid()), encoding="ascii")
    LOG.info("TURZX Studio http://127.0.0.1:%s", args.port)
    try:
        # The listening socket and app are ready; keep serving HTTP while USB
        # connects so the renderer and the user's controls remain responsive.
        threading.Thread(target=app.maintain_connection, name="studio-reconnect", daemon=True).start()
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
        server.server_close()
        (RUNTIME / "server.pid").unlink(missing_ok=True)


if __name__ == "__main__":
    main()

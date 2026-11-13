"""Standalone local account app. cswap exclusively owns credential mutations."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote
from urllib.request import build_opener, HTTPRedirectHandler

from claude_subscription import ClaudeMonitor

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
PUBLIC_FILES = {"account-app.html", "account-app.js", "account-app.css", "claude.js",
                "claude.css", "design-tokens.css", "assets/account-panel.svg"}
DEFAULT_STYLE = {"claude_background": "thought", "image_brightness": 112,
                 "image_saturation": 85, "image_fade": 12}


class AppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class AccountApp:
    def __init__(self, monitor=None, command=None):
        self.monitor = monitor if monitor is not None else ClaudeMonitor()
        self.command = command or shutil.which("cswap") or str(Path.home()/".local/bin/cswap")
        self.token = secrets.token_urlsafe(32)
        self.switch_lock = threading.Lock()
        self.lock = threading.Lock()
        self.confirmed = None
        self.style = dict(DEFAULT_STYLE)
        self.stopping = threading.Event()

    def sync_style(self):
        """Read the running screen's appearance; never control its USB session."""
        while not self.stopping.is_set():
            try:
                with build_opener(NoRedirect).open("http://127.0.0.1:8765/api/state", timeout=2) as response:
                    data = json.loads(response.read(512*1024))
                style = dict(DEFAULT_STYLE)
                if data.get("claude_background") in ("stand", "thought", "greeting", "floral", "celestial", "atelier", "botanical", "glasswave", "paperland", "none"):
                    style["claude_background"] = data["claude_background"]
                for key, low, high in (("image_brightness", 80, 140), ("image_saturation", 50, 120), ("image_fade", 0, 50)):
                    value = data.get(key)
                    if type(value) is int and low <= value <= high:
                        style[key] = value
                with self.lock:
                    self.style = style
            except (OSError, ValueError, TypeError):
                pass
            self.stopping.wait(3)

    def snapshot(self):
        data = self.monitor.snapshot()
        with self.lock:
            confirmed = self.confirmed
            if confirmed:
                account_id, completed_at = confirmed
                # Only override an older scheduler snapshot, for at most 30 s.
                # A fresh snapshot is authoritative, including automatic failover.
                sampled = data.get("updated_at") or 0
                if sampled <= completed_at and time.time()-completed_at < 30:
                    data["active_account_id"] = account_id
                    for account in data.get("accounts", []):
                        account["is_active"] = account["id"] == account_id
                else:
                    self.confirmed = None
            style = dict(self.style)
        return {"claude": data, "style": style, "busy": self.switch_lock.locked()}

    def switch(self, body):
        if not isinstance(body, dict) or set(body) != {"account_id"}:
            raise AppError("请选择一个账号。")
        account_id = body["account_id"]
        if not isinstance(account_id, str) or not re.fullmatch(r"[1-9][0-9]{0,5}", account_id):
            raise AppError("账号编号无效。")
        if not self.switch_lock.acquire(blocking=False):
            raise AppError("正在切换账号，请等待结果。", 409)
        try:
            data = self.monitor.snapshot()
            if data.get("stale"):
                raise AppError("账号数据已过期，请等待账号服务恢复。", 409)
            if account_id not in {a["id"] for a in data.get("accounts", [])}:
                raise AppError("账号已移除，请刷新后重试。", 409)
            try:
                result = subprocess.run([self.command, "switch", account_id, "--json"],
                                        stdin=subprocess.DEVNULL, capture_output=True,
                                        text=True, timeout=45)
            except subprocess.TimeoutExpired:
                self.monitor.refresh()
                raise AppError("切换超时，结果尚未确认。请等待当前账号更新后重试。", 504) from None
            except OSError:
                raise AppError("无法启动账号服务，请检查 cswap 安装。", 503) from None
            try:
                payload = json.loads(result.stdout)
                target = payload.get("to") or {}
                success = (result.returncode == 0 and payload.get("schemaVersion") == 1
                           and not payload.get("error") and str(target.get("number")) == account_id
                           and (payload.get("switched") is True or payload.get("reason") == "already-active"))
            except (ValueError, TypeError, AttributeError):
                success = False
            if not success:
                self.monitor.refresh()
                # Do not forward CLI output: it can contain private identities.
                raise AppError("账号服务未确认切换。请在 cswap 检查账号登录状态或会话占用。", 409)
            with self.lock:
                self.confirmed = (account_id, time.time())
            self.monitor.refresh()
            return {"ok": True, "account_id": account_id, "state": self.snapshot()}
        finally:
            self.switch_lock.release()

    def close(self):
        self.stopping.set()
        self.monitor.close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass

    def send(self, status, body, mime="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        for key, value in {"Content-Type": mime, "Content-Length": str(len(body)),
                           "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                           "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'"}.items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def valid_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, {"error": "Invalid host"})
        route = urlsplit(self.path).path
        if route == "/api/app-state":
            return self.send(200, self.server.app.snapshot())
        if route == "/api/session":
            return self.send(200, {"token": self.server.app.token})
        name = unquote(route).lstrip("/") or "account-app.html"
        path = (WEB/name).resolve()
        if (not path.is_relative_to(WEB.resolve()) or not path.is_file()
                or not (name in PUBLIC_FILES or name.startswith(("assets/claude/", "fonts/")))):
            return self.send(404, {"error": "Not found"})
        return self.send(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")

    def do_POST(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if (not self.valid_host() or self.headers.get("Origin") != origin
                or not secrets.compare_digest(self.headers.get("X-App-Token", ""), self.server.app.token)):
            return self.send(403, {"error": "仅允许本机 App 操作。"})
        if urlsplit(self.path).path != "/api/switch":
            return self.send(404, {"error": "Not found"})
        if self.headers.get("Content-Type") != "application/json":
            return self.send(415, {"error": "Expected application/json"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024:
                raise AppError("请求长度无效。")
            body = json.loads(self.rfile.read(size))
            result = self.server.app.switch(body)
            result["state"]["busy"] = False
            return self.send(200, result)
        except AppError as exc:
            return self.send(exc.status, {"error": str(exc)})
        except (ValueError, UnicodeError):
            return self.send(400, {"error": "请求格式无效。"})
        except Exception:
            return self.send(503, {"error": "账号服务暂不可用。"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    app = server.app = AccountApp()
    threading.Thread(target=app.sync_style, daemon=True).start()
    if args.parent_pid:
        def watch_parent():
            while not app.stopping.wait(2):
                if os.getppid() != args.parent_pid:
                    server.shutdown()
                    return
        threading.Thread(target=watch_parent, daemon=True).start()
    print(f"http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    finally:
        app.close()
        server.server_close()


if __name__ == "__main__":
    main()

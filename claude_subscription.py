"""Read cswap's public scheduler snapshot without accessing OAuth credentials.

The cswap daemon owns polling, refresh and account switching. This monitor only
reads its allowlisted snapshot and requests refresh with a fixed signal file.
Neither account secrets nor remote error bodies are forwarded to the browser.
"""
from __future__ import annotations

import copy
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import sys
import threading
import time

POLL_SECONDS = 2
STALE_SECONDS = 300
MAX_SNAPSHOT_BYTES = 256 * 1024
EVENT_LABELS = {"activated": "已启动账号的用量窗口",
                "request_accepted": "启动请求已成功，等待确认重置时间",
                "activation_failed": "用量窗口启动失败",
                "switched": "已切换可用账号", "switch_blocked": "账号切换被阻止",
                "all_unavailable": "当前没有可用账号", "error": "调度服务报告异常"}
WINDOWS = ("five_hour", "seven_day", "seven_day_sonnet", "seven_day_opus",
           "seven_day_fable", "seven_day_haiku")
ERROR_LABELS = {
    "usage_unavailable": "额度待刷新。",
    "quota_at_threshold": "已用额度达到 99%，未启动。",
    "existing_window_cannot_be_moved": "现有窗口尚未结束。",
    "configured_account_changed": "计划账号已变更，请重新配置调度。",
    "configured_account_missing_or_changed": "计划账号缺失或已变更，请重新配置调度。",
    "identity_mismatch": "当前账号与计划账号不一致，请重新配置调度。",
    "credential_unavailable": "账号登录凭据不可用。",
    "http_401": "账号登录已失效，请重新登录。",
    "http_403": "账号无权执行启动请求。",
    "http_429": "请求受限，等待服务端允许重试。",
}
SAFE_STATUSES = {"ok", "stale", "unavailable", "error", "pending", "disabled", "loading",
                 "rate_limited", "auth_error", "success", "active", "waiting", "failed",
                 "deferred", "blocked", "not_due", "not_started", "triggered", "confirmed",
                 "activating", "activated", "already_active", "waiting_reset",
                 "request_accepted", "identity_mismatch"}


def default_snapshot_path():
    explicit = os.environ.get("TURZX_CSWAP_STATUS_PATH")
    if explicit:
        return Path(explicit).expanduser()
    if sys.platform.startswith("linux"):
        xdg = Path(os.path.expanduser(os.environ.get("XDG_DATA_HOME", "")))
        root = xdg if xdg.is_absolute() else Path.home() / ".local" / "share"
        return root / "claude-swap" / "schedule-status.json"
    return Path.home() / ".claude-swap-backup" / "schedule-status.json"


def number(value, minimum=0, maximum=100):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(value) and minimum <= value <= maximum:
            return value
    return None


def timestamp(value):
    numeric = number(value, 0, 253402300799)
    if numeric is not None:
        return numeric
    if isinstance(value, str) and len(value) <= 40:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return number(parsed.timestamp(), 0, 253402300799)
        except (ValueError, OverflowError):
            pass
    return None


def safe_text(value, limit=80):
    if not isinstance(value, str):
        return None
    value = value.strip()
    # Never echo accidental tokens, auth headers or serialized credentials.
    if not value or len(value) > limit or re.search(
            r"sk-|bearer|token|credential|[\x00-\x1f]", value, re.I):
        return None
    return value


def masked_email(value):
    if not isinstance(value, str) or value.count("@") != 1:
        return None
    local, domain = value.rsplit("@", 1)
    if not local or not re.fullmatch(r"[a-zA-Z0-9.-]{1,80}", domain):
        return None
    return f"{local[0]}•••@{domain}"


def identifier(value):
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    text = safe_text(value, 64)
    return text if text and re.fullmatch(r"[a-zA-Z0-9_.:-]+", text) else None


def status(value, default="unavailable"):
    return value if isinstance(value, str) and value in SAFE_STATUSES else default


def error_label(value, fallback):
    """Translate only exact public error codes; never echo an unknown payload."""
    if not value:
        return None
    return ERROR_LABELS.get(value, fallback) if isinstance(value, str) else fallback


def normalize_snapshot(raw):
    """Replace the entire identity set; never merge data between account slots."""
    if not isinstance(raw, dict) or not isinstance(raw.get("accounts"), list):
        raise ValueError("Invalid scheduler snapshot")
    if raw.get("schemaVersion", 1) != 1:
        raise ValueError("Unsupported scheduler snapshot version")
    accounts = []
    seen = set()
    active = identifier(raw.get("active_account_id"))
    for item in raw["accounts"][:32]:
        if not isinstance(item, dict):
            continue
        account_id = identifier(item.get("id"))
        if account_id is None or account_id in seen:
            continue
        seen.add(account_id)
        label = safe_text(item.get("label"))
        if label and "@" in label:
            label = masked_email(label)
        usage = item.get("usage") if isinstance(item.get("usage"), dict) else {}
        windows = {}
        for key in WINDOWS:
            window = usage.get(key)
            if isinstance(window, dict):
                windows[key] = {"utilization": number(window.get("utilization")),
                                "resets_at": timestamp(window.get("resets_at"))}
        slot_raw = item.get("slot") if isinstance(item.get("slot"), dict) else {}
        slot = {key: value if isinstance(value, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) else None
                for key, value in (("start", slot_raw.get("start")), ("end", slot_raw.get("end")))}
        slot["timezone"] = safe_text(slot_raw.get("timezone"), 64)
        activation_raw = item.get("activation") if isinstance(item.get("activation"), dict) else {}
        activation = {"status": status(activation_raw.get("status"), "pending"),
                      "attempted_at": timestamp(activation_raw.get("attempted_at")),
                      "actual_resets_at": timestamp(activation_raw.get("actual_resets_at")),
                      "error": error_label(activation_raw.get("error"), "窗口启动失败，请检查 cswap 调度日志。")}
        accounts.append({"id": account_id, "label": label or f"账号 {len(accounts) + 1}",
                         "email": masked_email(item.get("email")),
                         "subscription_type": safe_text(item.get("subscription_type"), 40),
                         "is_active": account_id == active,
                         "usage": windows, "updated_at": timestamp(item.get("updated_at")),
                         "status": status(item.get("status")),
                         "error": error_label(item.get("error"), "账号同步失败，请检查 cswap 状态。"),
                         "slot": slot, "activation": activation})
    if active not in seen:
        active = None
    scheduler_raw = raw.get("scheduler") if isinstance(raw.get("scheduler"), dict) else {}
    event = scheduler_raw.get("last_event")
    if isinstance(event, dict):
        # Detail may contain remote output; only the event kind is public.
        event_kind = safe_text(event.get("kind"), 40)
        event = EVENT_LABELS.get(event_kind)
    else:
        event = safe_text(event, 100)
    return {"accounts": accounts, "active_account_id": active,
            "updated_at": timestamp(raw.get("updated_at")),
            "status": "ok" if accounts else "unavailable", "error": None,
            "scheduler": {"enabled": scheduler_raw.get("enabled") is True,
                          "timezone": safe_text(scheduler_raw.get("timezone"), 64),
                          "threshold": number(scheduler_raw.get("threshold")),
                          "last_event": event,
                          "error": error_label(scheduler_raw.get("error"), "调度服务报告异常，请检查 cswap 调度日志。")}}


class ClaudeMonitor:
    def __init__(self, path=None, *, poll_seconds=POLL_SECONDS, stale_seconds=STALE_SECONDS,
                 clock=time.time, autostart=True):
        self.path = Path(path) if path is not None else default_snapshot_path()
        self.refresh_path = self.path.with_name("schedule-refresh.request")
        self.poll_seconds = max(.05, poll_seconds)
        self.stale_seconds = stale_seconds
        self.clock = clock
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.data = normalize_snapshot({"accounts": []})
        self.read_error = "cswap 调度数据尚未就绪。"
        self.refresh_error = None
        if autostart:
            self.thread = threading.Thread(target=self._run, name="claude-snapshot", daemon=True)
            self.thread.start()

    def _read_once(self):
        try:
            with self.path.open("rb") as stream:
                payload = stream.read(MAX_SNAPSHOT_BYTES + 1)
            if len(payload) > MAX_SNAPSHOT_BYTES:
                raise ValueError("Snapshot too large")
            result = normalize_snapshot(json.loads(payload))
        except FileNotFoundError:
            error = "未找到 cswap 调度数据，请启动 cswap schedule。"
        except (OSError, ValueError, TypeError, RecursionError):
            error = "cswap 调度数据读取失败，显示上次采样。"
        else:
            with self.lock:
                self.data = result
                self.read_error = None
            return
        with self.lock:
            self.read_error = error

    def _run(self):
        while not self.stopping.is_set():
            self._read_once()
            self.wake.wait(self.poll_seconds)
            self.wake.clear()

    def refresh(self):
        """Signal the existing daemon; never refresh tokens or start inference here."""
        try:
            # Only operate in an existing cswap directory; a missing installation
            # must not be silently created by a display refresh button.
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.refresh_path, flags, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as stream:
                stream.write(f"{self.clock():.6f}\n")
            with self.lock:
                self.refresh_error = None
        except OSError:
            with self.lock:
                self.refresh_error = "无法请求 cswap 刷新，请检查调度服务。"
        self.wake.set()

    def snapshot(self):
        with self.lock:
            result = copy.deepcopy(self.data)
            read_error, refresh_error = self.read_error, self.refresh_error
        now = self.clock()
        sampled = result["updated_at"]
        result["stale"] = bool(read_error) or sampled is None or not -30 <= now - sampled <= self.stale_seconds
        result["error"] = refresh_error or read_error
        if result["stale"]:
            result["status"] = "stale" if result["accounts"] else "unavailable"
            result["error"] = result["error"] or "cswap 调度数据已过期，显示上次采样。"
        for account in result["accounts"]:
            at = account["updated_at"]
            reset_passed = any(window["resets_at"] is not None and at is not None
                               and at < window["resets_at"] <= now for window in account["usage"].values())
            account["stale"] = result["stale"] or at is None or not -30 <= now - at <= self.stale_seconds or reset_passed
            if account["stale"] and account["status"] == "ok":
                account["status"] = "stale"
        # A lost daemon cannot attest which account is currently installed.
        if result["stale"]:
            result["scheduler"]["enabled"] = False
            result["scheduler"]["error"] = "cswap 调度服务失联，无法确认自动调度状态。"
            result["active_account_id"] = None
            for account in result["accounts"]:
                account["is_active"] = False
        return result

    def close(self):
        self.stopping.set()
        self.wake.set()
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=3)

"""Contract checks for the read-only cswap display bridge."""
import json
from pathlib import Path
import tempfile
import time
import unittest

from claude_subscription import ClaudeMonitor, MAX_SNAPSHOT_BYTES, normalize_snapshot


NOW = 1805079600


def sample(account_id="1", utilization=42):
    return {"schemaVersion": 1, "updated_at": NOW, "active_account_id": account_id,
            "accounts": [{"id": account_id, "label": "早班", "email": "alice@example.com",
                          "subscription_type": "max", "is_active": True, "updated_at": NOW,
                          "status": "ok", "usage": {"five_hour": {"utilization": utilization, "resets_at": NOW + 3600},
                                                      "seven_day": {"utilization": 0, "resets_at": NOW + 86400}},
                          "slot": {"start": "07:00", "end": "12:00", "timezone": "Asia/Shanghai"}}],
            "scheduler": {"enabled": True, "timezone": "Asia/Shanghai", "threshold": 99,
                          "last_event": {"kind": "switched", "at": NOW, "detail": "internal detail"}}}


class ClaudeSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "schedule-status.json"
        self.now = NOW
        self.monitor = ClaudeMonitor(self.path, clock=lambda: self.now, autostart=False)
        self.addCleanup(self.monitor.close)

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")
        self.monitor._read_once()

    def test_unknown_and_true_zero_remain_distinct(self):
        raw = sample(utilization=None)
        raw["accounts"][0]["usage"]["seven_day_sonnet"] = {"utilization": True, "resets_at": "bad"}
        self.write(raw)
        result = self.monitor.snapshot()
        usage = result["accounts"][0]["usage"]
        self.assertIsNone(usage["five_hour"]["utilization"])
        self.assertEqual(usage["seven_day"]["utilization"], 0)
        self.assertIsNone(usage["seven_day_sonnet"]["utilization"])
        self.assertIsNone(usage["seven_day_sonnet"]["resets_at"])
        self.assertNotIn("seven_day_opus", usage)
        self.assertFalse(result["stale"])

    def test_whitelist_and_error_sanitizing_prevent_secret_leaks(self):
        raw = sample()
        raw.update(accessToken="TOP_SECRET", credentials={"refreshToken": "SECRET_REFRESH"})
        account = raw["accounts"][0]
        account.update(token="ACCOUNT_SECRET", error="Bearer sk-secret ACCOUNT_SECRET",
                       activation={"status": "failed", "error": "Bearer sk-another"})
        account["usage"]["five_hour"]["authorization"] = "HIDDEN"
        raw["scheduler"]["error"] = "sk-scheduler"
        raw["scheduler"]["last_event"]["detail"] = "SECRET_EVENT"
        self.write(raw)
        encoded = json.dumps(self.monitor.snapshot(), ensure_ascii=False)
        for private in ("TOP_SECRET", "SECRET_REFRESH", "ACCOUNT_SECRET", "HIDDEN", "sk-scheduler", "SECRET_EVENT", "alice@"):
            self.assertNotIn(private, encoded)
        self.assertIn("a•••@example.com", encoded)
        self.assertIn("账号同步失败", encoded)

    def test_identity_replacement_does_not_merge_quota(self):
        self.write(sample("1", 99))
        raw = sample("2", 8)
        raw["accounts"][0]["is_active"] = False
        self.write(raw)
        result = self.monitor.snapshot()
        self.assertEqual(result["active_account_id"], "2")
        self.assertEqual([a["id"] for a in result["accounts"]], ["2"])
        self.assertEqual(result["accounts"][0]["usage"]["five_hour"]["utilization"], 8)
        self.assertTrue(result["accounts"][0]["is_active"])

    def test_invalid_active_id_cannot_label_any_account_active(self):
        raw = sample()
        raw["active_account_id"] = "9"
        self.write(raw)
        result = self.monitor.snapshot()
        self.assertIsNone(result["active_account_id"])
        self.assertFalse(result["accounts"][0]["is_active"])

    def test_expiry_advances_without_new_file_reads(self):
        self.write(sample())
        self.now += 301
        result = self.monitor.snapshot()
        self.assertTrue(result["stale"])
        self.assertEqual(result["status"], "stale")
        self.assertIsNone(result["active_account_id"])
        self.assertFalse(result["accounts"][0]["is_active"])
        self.assertFalse(result["scheduler"]["enabled"])
        self.assertIn("调度服务失联", result["scheduler"]["error"])
        self.assertEqual(result["accounts"][0]["usage"]["five_hour"]["utilization"], 42)

    def test_snapshot_at_300_seconds_remains_current(self):
        self.write(sample())
        self.now += 300
        result = self.monitor.snapshot()
        self.assertFalse(result["stale"])
        self.assertFalse(result["accounts"][0]["stale"])
        self.assertTrue(result["scheduler"]["enabled"])

    def test_missing_snapshot_offers_current_cli_and_disables_scheduler(self):
        self.monitor._read_once()
        result = self.monitor.snapshot()
        self.assertIn("cswap schedule。", result["error"])
        self.assertNotIn("schedule run", result["error"])
        self.assertFalse(result["scheduler"]["enabled"])
        self.assertIn("调度服务失联", result["scheduler"]["error"])

    def test_account_sample_age_and_passed_reset_mark_stale(self):
        raw = sample()
        raw["accounts"][0]["updated_at"] = NOW - 310
        self.write(raw)
        self.assertTrue(self.monitor.snapshot()["accounts"][0]["stale"])
        raw = sample()
        raw["accounts"][0]["usage"]["five_hour"]["resets_at"] = NOW + 20
        self.write(raw)
        self.now += 25
        self.assertTrue(self.monitor.snapshot()["accounts"][0]["stale"])

    def test_missing_broken_oversize_and_future_samples_fail_closed(self):
        self.monitor._read_once()
        self.assertEqual(self.monitor.snapshot()["accounts"], [])
        self.write(sample())
        for payload in (b"{", b"[]", b"x" * (MAX_SNAPSHOT_BYTES + 1)):
            self.path.write_bytes(payload)
            self.monitor._read_once()
            result = self.monitor.snapshot()
            self.assertTrue(result["stale"])
            self.assertEqual(len(result["accounts"]), 1)
            self.assertIsNone(result["active_account_id"])
        raw = sample()
        raw["updated_at"] = NOW + 1000
        self.write(raw)
        self.assertTrue(self.monitor.snapshot()["stale"])

    def test_refresh_only_writes_fixed_signal(self):
        self.write(sample())
        before = self.path.read_bytes()
        self.monitor.refresh()
        self.assertEqual(self.path.read_bytes(), before)
        signal = self.path.with_name("schedule-refresh.request")
        self.assertTrue(signal.exists())
        self.assertEqual(float(signal.read_text()), NOW)
        self.assertEqual(signal.stat().st_mode & 0o777, 0o600)
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()),
                         ["schedule-refresh.request", "schedule-status.json"])

    def test_refresh_failure_is_safe_and_does_not_create_installation(self):
        self.monitor.path = self.path.parent / "missing" / "schedule-status.json"
        self.monitor.refresh_path = self.monitor.path.with_name("schedule-refresh.request")
        self.monitor.refresh()
        self.assertFalse(self.monitor.path.parent.exists())
        self.assertIn("无法请求", self.monitor.snapshot()["error"])

    def test_signal_symlink_is_not_followed(self):
        target = self.path.parent / "unrelated"
        target.write_text("keep")
        self.monitor.refresh_path.symlink_to(target)
        self.monitor.refresh()
        self.assertEqual(target.read_text(), "keep")
        self.assertIn("无法请求", self.monitor.snapshot()["error"])

    def test_activation_contract_and_safe_event_labels(self):
        raw = sample()
        raw["accounts"][0]["activation"] = {"status": "waiting_reset", "actual_resets_at": NOW + 300}
        self.write(raw)
        result = self.monitor.snapshot()
        self.assertEqual(result["accounts"][0]["activation"]["status"], "waiting_reset")
        self.assertEqual(result["accounts"][0]["activation"]["actual_resets_at"], NOW + 300)
        self.assertEqual(result["scheduler"]["last_event"], "已切换可用账号")

    def test_all_scheduler_activation_statuses_survive_normalization(self):
        for activation_status in ("pending", "activated", "already_active", "waiting_reset",
                                  "activating", "unavailable", "failed", "request_accepted"):
            with self.subTest(status=activation_status):
                raw = sample()
                raw["accounts"][0]["activation"] = {"status": activation_status}
                normalized = normalize_snapshot(raw)
                self.assertEqual(normalized["accounts"][0]["activation"]["status"], activation_status)

    def test_error_codes_describe_real_reason_without_inventing_login_failure(self):
        cases = {
            "usage_unavailable": "额度待刷新。",
            "quota_at_threshold": "已用额度达到 99%，未启动。",
            "existing_window_cannot_be_moved": "现有窗口尚未结束。",
            "configured_account_changed": "计划账号已变更，请重新配置调度。",
            "configured_account_missing_or_changed": "计划账号缺失或已变更，请重新配置调度。",
            "identity_mismatch": "当前账号与计划账号不一致，请重新配置调度。",
        }
        for code, message in cases.items():
            with self.subTest(code=code):
                raw = sample()
                raw["accounts"][0].update(error=code, activation={"status": "unavailable", "error": code})
                raw["scheduler"]["error"] = code
                result = normalize_snapshot(raw)
                self.assertEqual(result["accounts"][0]["error"], message)
                self.assertEqual(result["accounts"][0]["activation"]["error"], message)
                self.assertEqual(result["scheduler"]["error"], message)

    def test_request_accepted_does_not_claim_reset_confirmation(self):
        raw = sample()
        raw["accounts"][0].update(status="identity_mismatch", activation={"status": "request_accepted"})
        raw["scheduler"]["last_event"] = {"kind": "request_accepted", "detail": "private response"}
        result = normalize_snapshot(raw)
        self.assertEqual(result["accounts"][0]["status"], "identity_mismatch")
        self.assertEqual(result["accounts"][0]["activation"]["status"], "request_accepted")
        self.assertIsNone(result["accounts"][0]["activation"]["actual_resets_at"])
        self.assertEqual(result["scheduler"]["last_event"], "启动请求已成功，等待确认重置时间")

    def test_additional_model_windows_are_preserved_only_when_present(self):
        raw = sample()
        raw["accounts"][0]["usage"]["seven_day_fable"] = {"utilization": 17, "resets_at": NOW + 500}
        raw["accounts"][0]["usage"]["seven_day_haiku"] = {"utilization": None, "resets_at": None}
        result = normalize_snapshot(raw)
        usage = result["accounts"][0]["usage"]
        self.assertEqual(usage["seven_day_fable"]["utilization"], 17)
        self.assertIsNone(usage["seven_day_haiku"]["utilization"])
        self.assertNotIn("seven_day_opus", usage)

    def test_timestamp_iso_and_snapshot_copy(self):
        raw = sample()
        raw["updated_at"] = "2026-11-13T00:00:00Z"
        result = normalize_snapshot(raw)
        self.assertIsInstance(result["updated_at"], (int, float))
        self.write(sample())
        snapshot = self.monitor.snapshot()
        snapshot["accounts"].clear()
        self.assertEqual(len(self.monitor.snapshot()["accounts"]), 1)

    def test_thread_reads_and_closes_without_network(self):
        self.path.write_text(json.dumps(sample()), encoding="utf-8")
        monitor = ClaudeMonitor(self.path, clock=lambda: NOW, poll_seconds=.05)
        self.addCleanup(monitor.close)
        for _ in range(50):
            if monitor.snapshot()["accounts"]:
                break
            time.sleep(.01)
        self.assertEqual(len(monitor.snapshot()["accounts"]), 1)
        monitor.close()
        self.assertFalse(monitor.thread.is_alive())


if __name__ == "__main__":
    unittest.main()

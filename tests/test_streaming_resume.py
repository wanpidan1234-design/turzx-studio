"""Lifecycle tests without USB hardware, browsers or account access."""
import json
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Studio, load_display_preferences, SessionPaused


class StreamingResumeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.path = self.root / 'display-preferences.json'
        for name in ('Telemetry', 'SubscriptionMonitor', 'ClaudeMonitor', 'threading.Thread', 'shutil.which',
                     'subprocess.Popen', 'TurzxWinUSB', 'enumerate_device_paths'):
            patcher = patch('server.' + name)
            setattr(self, name.split('.')[-1], patcher.start())
            self.addCleanup(patcher.stop)
        patcher = patch('server.RUNTIME', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.SubscriptionMonitor.return_value.snapshot.return_value = {}
        self.ClaudeMonitor.return_value.snapshot.return_value = {}
        self.TurzxWinUSB.return_value.descriptor_info.return_value = {}
        self.which.return_value = 'node'
        self.enumerate_device_paths.return_value = ['panel']

    def create(self, resume=None):
        if resume is not None:
            self.path.write_text(json.dumps({'resume_streaming': resume}), encoding='utf-8')
        app = Studio(8765)
        self.addCleanup(app.close)
        return app

    def test_old_settings_do_not_start_usb(self):
        app = self.create()
        app.try_resume_streaming()
        self.TurzxWinUSB.assert_not_called()
        self.assertFalse(app.state['streaming'])

    def test_saved_backlight_is_restored_on_start_and_reconnect(self):
        for value in (0, 100):
            with self.subTest(value=value):
                self.path.write_text(json.dumps({'resume_streaming': True, 'brightness': value}))
                app = self.create()
                device = self.TurzxWinUSB.return_value
                device.reset_mock()
                app.try_resume_streaming()
                device.brightness.assert_called_once_with(value)
                app.stop()
                app.start()
                self.assertEqual(device.brightness.call_count, 2)
                app.close()

    def test_all_scene_settings_survive_restart_and_later_partial_update(self):
        app = self.create()
        preferences = {
            'page': 'openai', 'auto': True, 'interval': 45, 'rotation': 90, 'fps': 5,
            'note': '保留我的便签', 'subscription_view': 'billing', 'subscription_auto': True,
            'subscription_bucket': 'weekly', 'focus_duration': 2700,
            'claude_background': 'greeting', 'image_brightness': 100,
            'image_saturation': 100, 'image_fade': 0,
            'animation': {'preset': 'stars', 'speed': 1.5, 'detail': 'light',
                          'paused': True, 'show_clock': False, 'seed': 123},
        }
        app.control(preferences)
        app.start()
        app.close()
        reloaded = self.create()
        actual = reloaded.snapshot()
        for key, value in preferences.items():
            if key == 'animation':
                self.assertEqual(reloaded.motion.settings, value)
            else:
                self.assertEqual(actual[key], value, key)
        self.assertEqual(actual['focus']['duration'], 2700)
        self.assertTrue(actual['resume_streaming'])
        reloaded.control({'animation': {'speed': .5}})
        reloaded.control({'note': ''})
        saved = load_display_preferences(self.path)
        self.assertEqual(saved['animation'], {**preferences['animation'], 'speed': .5})
        self.assertEqual(saved['note'], '')

    def test_failed_scene_save_cannot_mutate_animation_or_note(self):
        app = self.create()
        before = dict(app.motion.settings)
        note = app.state['note']
        with patch('server.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                app.control({'animation': {'preset': 'stars'}, 'note': 'not saved'})
        self.assertEqual(app.motion.settings, before)
        self.assertEqual(app.state['note'], note)

    def test_restored_timer_configuration_does_not_restart_a_live_timer(self):
        app = self.create()
        app.control({'focus_duration': 1800, 'action': 'focus_start'})
        self.assertTrue(app.state['focus']['running'])
        app.close()
        reloaded = self.create()
        self.assertEqual(reloaded.state['focus'], {'duration': 1800, 'remaining': 1800, 'running': False})
        self.assertIsNone(reloaded.focus_deadline)

    def test_unknown_backlight_is_not_overwritten(self):
        app = self.create(True)
        app.try_resume_streaming()
        self.TurzxWinUSB.return_value.brightness.assert_not_called()

    def test_backlight_change_survives_service_restart(self):
        app = self.create()
        app.start()
        app.control({'brightness': 76})
        app.close()
        self.assertEqual(load_display_preferences(self.path)['brightness'], 76)
        reloaded = self.create()
        self.TurzxWinUSB.return_value.brightness.reset_mock()
        reloaded.try_resume_streaming()
        self.TurzxWinUSB.return_value.brightness.assert_called_once_with(76)

    def test_failed_backlight_restore_prevents_renderer_start(self):
        self.path.write_text(json.dumps({'resume_streaming': True, 'brightness': 100}))
        app = self.create()
        self.TurzxWinUSB.return_value.brightness.side_effect = OSError('backlight failed')
        with self.assertRaises(OSError):
            app.start()
        self.Popen.assert_not_called()
        self.TurzxWinUSB.return_value.close.assert_called()
        self.assertFalse(app.state['streaming'])

    def test_saved_state_is_not_reported_as_connected_before_resume(self):
        app = self.create(True)
        self.assertFalse(app.state['streaming'])
        self.assertFalse(app.state['connected'])
        app.try_resume_streaming()
        app.try_resume_streaming()
        self.TurzxWinUSB.assert_called_once()
        self.assertTrue(app.state['streaming'])

    def test_close_preserves_resume_but_explicit_stop_clears_it(self):
        app = self.create()
        app.start()
        app.close()
        self.assertTrue(load_display_preferences(self.path)['resume_streaming'])
        next_app = self.create()
        next_app.try_resume_streaming()
        next_app.control({'action': 'stop'})
        next_app.close()
        self.assertFalse(load_display_preferences(self.path)['resume_streaming'])
        self.assertFalse(next_app.state['streaming'])

    def test_stop_before_resume_cancels_pending_start(self):
        app = self.create(True)
        app.control({'action': 'stop'})
        app.try_resume_streaming()
        self.TurzxWinUSB.assert_not_called()

    def test_shutdown_releases_usb_before_returning_and_preserves_resume(self):
        app = self.create()
        app.start()
        response = app.control({'action': 'shutdown'})
        self.assertTrue(app.stopping.is_set())
        self.assertFalse(response['streaming'])
        self.assertFalse(response['connected'])
        self.assertIsNone(app.device)
        self.assertTrue(load_display_preferences(self.path)['resume_streaming'])

    def test_failed_reconnect_is_throttled_and_keeps_manual_retry_available(self):
        app = self.create(True)
        self.TurzxWinUSB.side_effect = OSError('USB unavailable')
        with self.assertLogs('turzx', level='WARNING'):
            app.try_resume_streaming()
        app.try_resume_streaming()
        self.TurzxWinUSB.assert_called_once()
        self.assertFalse(app.state['streaming'])
        self.assertFalse(app.state['connected'])
        self.assertEqual(app.snapshot()['error'], 'USB unavailable')
        self.assertTrue(load_display_preferences(self.path)['resume_streaming'])
        self.TurzxWinUSB.side_effect = None
        app.control({'action': 'start'})
        self.assertTrue(app.state['streaming'])

    def test_failed_first_start_does_not_enable_resume(self):
        app = self.create()
        self.Popen.side_effect = OSError('renderer unavailable')
        with self.assertRaises(OSError):
            app.start()
        self.assertFalse(app.state['streaming'])
        self.assertFalse(app.state['resume_streaming'])
        self.TurzxWinUSB.return_value.close.assert_called()

    def test_stale_session_stop_cannot_clear_new_resume_setting(self):
        app = self.create()
        app.start()
        app.stop(expected_session=app.session_id-1, remember=True)
        self.assertTrue(app.state['streaming'])
        self.assertTrue(load_display_preferences(self.path)['resume_streaming'])

    def test_closed_service_cannot_resume_or_start(self):
        app = self.create(True)
        app.close()
        app.try_resume_streaming()
        with self.assertRaises(SessionPaused):
            app.start()
        self.TurzxWinUSB.assert_not_called()

    def test_resume_setting_requires_a_boolean(self):
        for invalid in ('true', 1, None, []):
            self.path.write_text(json.dumps({'resume_streaming': invalid}), encoding='utf-8')
            self.assertNotIn('resume_streaming', load_display_preferences(self.path))

    def test_absent_device_is_not_opened_and_replug_resumes(self):
        app = self.create(True)
        self.enumerate_device_paths.return_value = []
        with patch('server.time.monotonic', return_value=100):
            app.try_resume_streaming()
        self.TurzxWinUSB.assert_not_called()
        self.assertFalse(app.state['streaming'])
        self.enumerate_device_paths.return_value = ['panel']
        with patch('server.time.monotonic', return_value=102):
            app.try_resume_streaming()
        self.assertTrue(app.state['streaming'])
        self.TurzxWinUSB.assert_called_once()

    def test_transfer_failure_reconnects_without_late_cleanup_killing_it(self):
        app = self.create()
        app.start()
        old_session = app.session_id
        with self.assertLogs('turzx', level='ERROR'):
            app.fail('USB unplugged', old_session)
        app.try_resume_streaming()
        self.assertGreater(app.session_id, old_session)
        self.assertTrue(app.state['streaming'])
        app.stop(expected_session=old_session)
        self.assertTrue(app.state['streaming'])
        self.assertIsNotNone(app.device)

    def test_repeated_connect_errors_back_off_and_stop_cancels_retries(self):
        app = self.create(True)
        self.TurzxWinUSB.side_effect = OSError('device busy')
        with patch('server.time.monotonic', return_value=100), self.assertLogs('turzx', level='WARNING'):
            app.try_resume_streaming()
        self.assertEqual(app.reconnect_at, 102)
        with patch('server.time.monotonic', return_value=101):
            app.try_resume_streaming()
        self.assertEqual(self.TurzxWinUSB.call_count, 1)
        with patch('server.time.monotonic', return_value=102), self.assertLogs('turzx', level='WARNING'):
            app.try_resume_streaming()
        self.assertEqual(app.reconnect_at, 106)
        app.control({'action': 'stop'})
        with patch('server.time.monotonic', return_value=200):
            app.try_resume_streaming()
        self.assertEqual(self.TurzxWinUSB.call_count, 2)

    def test_successful_usb_frame_resets_backoff(self):
        app = self.create()
        app.start()
        app.reconnect_delay = 30
        app.reconnect_at = 10000
        self.TurzxWinUSB.return_value.draw_png.return_value = b'ack'
        image = Image.new('RGB', (1280,720))
        body = io.BytesIO()
        image.save(body, 'PNG')
        app.frame(body.getvalue(), 270, app.session_id, 0)
        self.assertEqual(app.reconnect_delay, 2)
        self.assertEqual(app.reconnect_at, 0)

    def test_panel_color_correction_preserves_alpha_orientation_and_source(self):
        app = self.create()
        app.start()
        self.TurzxWinUSB.return_value.draw_png.return_value = b'ack'
        source = Image.new('RGBA', (1280, 720), (208, 107, 49, 0))
        source.putpixel((0, 0), (255, 0, 0, 255))
        body = io.BytesIO()
        source.save(body, 'PNG')
        original = body.getvalue()
        for order in ('rgb', 'bgr', 'brg'):
            app.control({'panel_color_order': order})
            app.frame(original, 270, app.session_id, 0)
            payload = self.TurzxWinUSB.return_value.draw_png.call_args.args[0]
            sent = Image.open(io.BytesIO(payload))
            self.assertEqual(sent.size, (720, 1280))
            self.assertEqual(payload[25], 6)
            self.assertEqual(sent.getchannel('A').getextrema(), (255, 255))
            self.assertEqual(sent.getpixel((20, 20)), {'rgb': (208, 107, 49, 255), 'bgr': (49, 107, 208, 255), 'brg': (49, 208, 107, 255)}[order])
            self.assertEqual(sent.getpixel((719, 0)), {'rgb': (255, 0, 0, 255), 'bgr': (0, 0, 255, 255), 'brg': (0, 255, 0, 255)}[order])
            self.assertEqual(load_display_preferences(app.preferences_path)['panel_color_order'], order)
        self.assertEqual(body.getvalue(), original)

    def test_invalid_color_order_cannot_change_output_or_saved_setting(self):
        app = self.create()
        for value in (None, True, 'bgra', [], {}):
            with self.assertRaises(ValueError):
                app.control({'panel_color_order': value})
        self.assertEqual(app.state['panel_color_order'], 'rgb')

    def test_ratio_preserving_tone_reaches_real_frame_entry(self):
        app = self.create()
        profile = {'gamma': .45, 'saturation': 1, 'offset_x': -60,
                   'offset_y': 0, 'tone_mode': 'preserve_rgb'}
        app.control({'panel_calibration': profile, 'panel_color_order': 'brg'})
        app.start()
        self.TurzxWinUSB.return_value.draw_png.return_value = b'ack'
        body = io.BytesIO()
        Image.new('RGB', (1280, 720), (204, 120, 82)).save(body, 'PNG')
        app.frame(body.getvalue(), 270, app.session_id)
        payload = self.TurzxWinUSB.return_value.draw_png.call_args.args[0]
        result = Image.open(io.BytesIO(payload))
        self.assertEqual(result.getpixel((0, 0)), (93, 231, 136, 255))
        self.assertEqual(result.size, (720, 1280))
        self.assertEqual(payload[25], 6)
        self.assertEqual(load_display_preferences(app.preferences_path)['panel_calibration'], profile)

    def test_confirmed_calibration_reaches_frame_and_survives_restart(self):
        app = self.create()
        profile = {'gamma': .6, 'saturation': .8, 'offset_x': -60, 'offset_y': 0}
        app.control({'panel_calibration': profile, 'panel_color_order': 'brg'})
        app.start()
        self.TurzxWinUSB.return_value.draw_png.return_value = b'ack'
        source = Image.new('RGBA', (1280, 720), (128, 128, 128, 0))
        source.putpixel((0, 0), (255, 255, 255, 255))
        body = io.BytesIO()
        source.save(body, 'PNG')
        app.frame(body.getvalue(), 270, app.session_id)
        payload = self.TurzxWinUSB.return_value.draw_png.call_args.args[0]
        result = Image.open(io.BytesIO(payload))
        self.assertEqual(result.getpixel((659, 0)), (255, 255, 255, 255))
        self.assertEqual(result.getpixel((0, 0)), (169, 169, 169, 255))
        self.assertEqual(result.getchannel('A').getextrema(), (255, 255))
        self.assertEqual(payload[25], 6)
        app.stop()
        reloaded = self.create()
        self.assertEqual(reloaded.state['panel_calibration'], profile)
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            reloaded.control({'panel_calibration': {**profile, 'gamma': True}})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(reloaded.state['panel_calibration'], profile)


if __name__ == '__main__':
    unittest.main()

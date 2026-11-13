"""Account switching tests use fake cswap; never change the user's login."""
import copy
import json
import subprocess
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from account_app import AccountApp, AppError, Handler, ThreadingHTTPServer


class AccountAppTests(unittest.TestCase):
    def setUp(self):
        self.monitor = Mock()
        self.data = {'accounts': [{'id': str(i), 'label': f'账号 {i}'} for i in range(1, 4)],
                     'active_account_id': '1', 'stale': False, 'updated_at': time.time()-10}
        self.monitor.snapshot.side_effect = lambda: copy.deepcopy(self.data)
        self.app = AccountApp(self.monitor, '/fake/cswap')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.server.app = self.app
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, route, body=None, **headers):
        defaults = {'Origin': self.base, 'X-App-Token': self.app.token, 'Content-Type': 'application/json'}
        defaults.update(headers)
        request = Request(self.base+route, data=json.dumps(body).encode() if body is not None else None, headers=defaults)
        with urlopen(request, timeout=3) as result:
            return json.load(result)

    def result(self, number=2, **extra):
        data = {'schemaVersion': 1, 'switched': True, 'to': {'number': number, 'email': 'private@example.com'}}
        data.update(extra)
        return subprocess.CompletedProcess([], 0, json.dumps(data), '')

    @patch('account_app.subprocess.run')
    def test_switch_confirms_target_and_sanitizes_response(self, run):
        run.return_value = self.result()
        result = self.request('/api/switch', {'account_id': '2'})
        self.assertEqual(result['state']['claude']['active_account_id'], '2')
        self.assertFalse(result['state']['busy'])
        self.assertNotIn('private@example.com', json.dumps(result))
        self.assertEqual(run.call_args.args[0], ['/fake/cswap', 'switch', '2', '--json'])
        self.assertEqual(run.call_args.kwargs['timeout'], 45)
        self.monitor.refresh.assert_called_once()
        self.data['updated_at'] = time.time()+1
        self.data['active_account_id'] = '3'
        self.assertEqual(self.app.snapshot()['claude']['active_account_id'], '3')

    @patch('account_app.subprocess.run')
    def test_already_active_is_confirmed(self, run):
        run.return_value = self.result(1, switched=False, reason='already-active')
        self.assertTrue(self.app.switch({'account_id': '1'})['ok'])

    @patch('account_app.subprocess.run')
    def test_reject_wrong_target_or_blocked_result(self, run):
        for result in (self.result(3), self.result(2, switched=False, reason='blocked'),
                       self.result(error={'message': 'secret'}),
                       subprocess.CompletedProcess([], 1, 'secret', 'secret'),
                       subprocess.CompletedProcess([], 0, '[]', '')):
            run.return_value = result
            with self.assertRaises(AppError) as raised:
                self.app.switch({'account_id': '2'})
            self.assertNotIn('secret', str(raised.exception))
            self.assertIsNone(self.app.confirmed)
            self.assertFalse(self.app.switch_lock.locked())

    @patch('account_app.subprocess.run')
    def test_invalid_and_unknown_ids_never_launch(self, run):
        for body in ({'account_id': '--force'}, {'account_id': 2}, {'account_id': '99'},
                     {'account_id': '2;touch /tmp/x'}, {'account_id': '2', 'force': True}, []):
            with self.assertRaises(AppError):
                self.app.switch(body)
        run.assert_not_called()

    @patch('account_app.subprocess.run')
    def test_stale_snapshot_and_concurrent_switch_block(self, run):
        self.data['stale'] = True
        with self.assertRaises(AppError):
            self.app.switch({'account_id': '2'})
        self.data['stale'] = False
        self.app.switch_lock.acquire()
        try:
            with self.assertRaises(AppError):
                self.app.switch({'account_id': '2'})
        finally:
            self.app.switch_lock.release()
        run.assert_not_called()

    @patch('account_app.subprocess.run')
    def test_timeout_does_not_claim_success(self, run):
        run.side_effect = subprocess.TimeoutExpired('cswap', 45)
        with self.assertRaises(AppError) as raised:
            self.app.switch({'account_id': '2'})
        self.assertEqual(raised.exception.status, 504)
        self.assertIsNone(self.app.confirmed)
        self.assertFalse(self.app.switch_lock.locked())

    @patch('account_app.subprocess.run')
    def test_cross_origin_and_missing_token_are_rejected(self, run):
        for headers in ({'Origin': 'https://example.com'}, {'X-App-Token': ''}, {'Host': 'example.com'}):
            with self.assertRaises(HTTPError) as raised:
                self.request('/api/switch', {'account_id': '2'}, **headers)
            self.assertEqual(raised.exception.code, 403)
            raised.exception.close()
        run.assert_not_called()

    def test_private_files_are_not_served(self):
        for route in ('/account_app.py', '/claude_subscription.py', '/runtime/x', '/%2e%2e/account_app.py'):
            with self.assertRaises(HTTPError) as raised:
                self.request(route)
            self.assertEqual(raised.exception.code, 404)
            raised.exception.close()

    @patch('account_app.build_opener')
    def test_new_screen_background_is_shared_with_app(self, opener):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.read.return_value = json.dumps({
            'claude_background': 'floral', 'image_brightness': 125,
            'image_saturation': 90, 'image_fade': 10}).encode()
        with patch.object(self.app.stopping, 'wait', side_effect=lambda _: self.app.stopping.set()):
            self.app.sync_style()
        self.assertEqual(self.app.snapshot()['style'], {
            'claude_background': 'floral', 'image_brightness': 125,
            'image_saturation': 90, 'image_fade': 10})

    def test_expired_confirmation_returns_to_snapshot(self):
        self.app.confirmed = ('2', time.time()-31)
        self.assertEqual(self.app.snapshot()['claude']['active_account_id'], '1')


if __name__ == '__main__':
    unittest.main()

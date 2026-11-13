"""HTTP integration without account credentials or USB hardware."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import Handler, Studio, ThreadingHTTPServer, load_display_preferences


class ClaudeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        for name in ('Telemetry', 'SubscriptionMonitor', 'ClaudeMonitor'):
            mock = patch('server.' + name).start()
            self.addCleanup(patch.stopall)
            mock.return_value.snapshot.return_value = {}
            setattr(self, name, mock.return_value)
        with patch('server.RUNTIME', Path(self.folder.name)):
            self.app = Studio(self.server.server_port)
        self.ClaudeMonitor.snapshot.return_value = {
            'accounts': [{'id': '2', 'usage': {'five_hour': {'utilization': 99}}}],
            'active_account_id': '2', 'status': 'ok'}
        self.server.app = self.app
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.cleanup)
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def cleanup(self):
        self.server.shutdown()
        self.server.server_close()
        self.app.close()
        self.thread.join(timeout=2)

    def request(self, route, body=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        request = Request(self.base + route, data=json.dumps(body).encode() if body else None,
                          headers=headers)
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def test_claude_endpoint_matches_state_and_does_not_refresh(self):
        direct = self.request('/api/claude')
        self.assertEqual(direct, self.request('/api/state')['claude'])
        self.assertEqual(direct['active_account_id'], '2')
        self.ClaudeMonitor.refresh.assert_not_called()

    def test_page_and_refresh_use_existing_control_and_persist(self):
        for page in ('claude', 'cswap'):
            state = self.request('/api/control', {'page': page})
            self.assertEqual(state['page'], page)
            self.assertEqual(load_display_preferences(self.app.preferences_path)['page'], page)
        self.request('/api/control', {'action': 'claude_refresh'})
        self.ClaudeMonitor.refresh.assert_called_once()
        self.SubscriptionMonitor.refresh.assert_not_called()

    def test_foreign_origin_cannot_trigger_account_refresh(self):
        with self.assertRaises(HTTPError) as caught:
            self.request('/api/control', {'action': 'claude_refresh'}, 'https://example.com')
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
        self.ClaudeMonitor.refresh.assert_not_called()


if __name__ == '__main__':
    unittest.main()

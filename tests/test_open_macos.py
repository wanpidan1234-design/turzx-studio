"""Offline launcher checks; never open a browser or change launchd."""
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from open_macos import URL, launcher_source, open_controller, service_ready


class MacLauncherTests(unittest.TestCase):
    def test_running_service_is_reused_without_launchctl(self):
        with patch('open_macos.service_ready', return_value=True), \
             patch('open_macos.subprocess.run') as run:
            open_controller()
        run.assert_called_once_with(['/usr/bin/open', URL], check=True)

    def test_stopped_service_uses_venv_and_waits_before_opening(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            python = root / '.venv' / 'bin' / 'python'
            python.parent.mkdir(parents=True)
            python.symlink_to(sys.executable)
            with patch('open_macos.ROOT', root), \
                 patch('open_macos.service_ready', side_effect=[False, False, True]), \
                 patch('open_macos.time.sleep'), \
                 patch('open_macos.subprocess.run', return_value=Mock(returncode=0)) as run:
                open_controller()
            self.assertEqual(run.call_args_list[0].args[0], [str(python), str(root / 'autostart_macos.py')])
            self.assertEqual(run.call_args_list[1].args[0], ['/usr/bin/open', URL])

    def test_failed_start_does_not_open_browser(self):
        with patch('open_macos.service_ready', return_value=False), \
             patch('open_macos.Path.is_file', return_value=True), \
             patch('open_macos.time.monotonic', side_effect=[0, 21]), \
             patch('open_macos.subprocess.run', return_value=Mock(returncode=1, stderr='startup error')) as run:
            with self.assertRaisesRegex(RuntimeError, 'startup error'):
                open_controller()
        self.assertEqual(run.call_count, 1)

    def test_applescript_quotes_paths_as_shell_arguments(self):
        root = Path('/tmp/屏幕 $(touch nope) \'quoted\" path')
        source = launcher_source(root)
        encoded = source.splitlines()[1].split('do shell script ', 1)[1]
        command = json.loads(encoded)
        self.assertEqual(shlex.split(command), [str(root / '.venv/bin/python'), str(root / 'open_macos.py')])

    def test_readiness_rejects_unrelated_local_server(self):
        with patch('open_macos.urllib.request.urlopen') as request:
            response = request.return_value.__enter__.return_value
            response.read.return_value = b'{"status":"ok"}'
            self.assertFalse(service_ready())
            response.read.return_value = b'{"device":{"vid":"1CBE"},"streaming":false}'
            self.assertTrue(service_ready())


if __name__ == '__main__':
    unittest.main()

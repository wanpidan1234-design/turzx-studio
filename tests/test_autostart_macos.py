"""Login agent configuration checks; never modify launchd in tests."""
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autostart_macos import agent_config, main


class AutostartTests(unittest.TestCase):
    def test_preserves_venv_symlink_and_paths_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="turzx test ") as directory:
            root = Path(directory)
            python = root / "venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.symlink_to(sys.executable)
            config = plistlib.loads(plistlib.dumps(agent_config(root, python, "/custom node/bin/node")))
            self.assertEqual(config["ProgramArguments"], [str(python), str(root / "server.py")])
            self.assertEqual(config["WorkingDirectory"], str(root))
            self.assertTrue(config["EnvironmentVariables"]["PATH"].startswith("/custom node/bin:"))

    def test_restart_policy_respects_normal_shutdown(self):
        config = agent_config(Path("/tmp/turzx"), "/tmp/venv/bin/python", "/opt/homebrew/bin/node")
        self.assertTrue(config["RunAtLoad"])
        self.assertEqual(config["KeepAlive"], {"SuccessfulExit": False})
        self.assertGreaterEqual(config["ThrottleInterval"], 10)

    def test_existing_login_agent_can_be_reopened_without_killing_it(self):
        with patch('autostart_macos.sys.platform', 'darwin'), \
             patch('autostart_macos.sys.argv', ['autostart_macos.py']), \
             patch('autostart_macos.os.getuid', return_value=501), \
             patch('autostart_macos.subprocess.run', return_value=Mock(returncode=0)) as run:
            main()
        self.assertEqual(run.call_args_list[1].args[0],
                         ['launchctl', 'kickstart', 'gui/501/com.turzx.studio'])
        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()

"""Install or remove the current user's TURZX login agent."""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import socket
import subprocess
import sys

LABEL = "com.turzx.studio"
ROOT = Path(__file__).resolve().parent


def agent_config(root, python, node):
    # Do not resolve Python symlinks: the venv path selects its dependencies.
    return {
        "Label": LABEL,
        "ProgramArguments": [os.path.abspath(python), str(root / "server.py")],
        "WorkingDirectory": str(root),
        "EnvironmentVariables": {
            "PATH": os.pathsep.join(dict.fromkeys([
                str(Path(node).parent), "/opt/homebrew/bin", "/usr/local/bin",
                "/usr/bin", "/bin", "/usr/sbin", "/sbin",
            ])),
            "PYTHONUNBUFFERED": "1",
        },
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "StandardOutPath": str(root / "runtime" / "launchd.stdout.log"),
        "StandardErrorPath": str(root / "runtime" / "launchd.stderr.log"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disable", action="store_true", help="Remove login startup")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("This installer requires macOS.")
    domain = f"gui/{os.getuid()}"
    target = f"{domain}/{LABEL}"
    plist = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    loaded = subprocess.run(["launchctl", "print", target], capture_output=True).returncode == 0
    if args.disable:
        if loaded:
            subprocess.run(["launchctl", "bootout", target], check=True)
        plist.unlink(missing_ok=True)
        print("已取消登录启动，并停止该启动项管理的服务。")
        return
    if loaded:
        # kickstart reopens a normally closed agent, and leaves a running one alone.
        subprocess.run(["launchctl", "kickstart", target], check=True)
        print("登录启动项已加载，服务已启动或正在运行。")
        return
    node = shutil.which("node")
    if not node:
        parser.error("Node.js is required. Install Node.js before enabling startup.")
    subprocess.run([sys.executable, "-c", "import PIL, psutil, usb"], check=True)
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(("127.0.0.1", 8765)) == 0:
            parser.error("Port 8765 is in use. Close the existing service before installing.")
    (ROOT / "runtime").mkdir(exist_ok=True)
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_bytes(plistlib.dumps(agent_config(ROOT, sys.executable, node)))
    plist.chmod(0o600)
    subprocess.run(["launchctl", "enable", target], check=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)
    print(f"已启用登录启动：{plist}")


if __name__ == "__main__":
    main()

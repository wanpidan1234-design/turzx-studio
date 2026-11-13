"""Open the local controller, starting its login agent only when needed."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8765/"


def service_ready():
    try:
        with urllib.request.urlopen(URL + "api/state", timeout=1) as response:
            state = json.loads(response.read(1024 * 1024))
        return (isinstance(state, dict) and isinstance(state.get("device"), dict)
                and state["device"].get("vid") == "1CBE"
                and type(state.get("streaming")) is bool)
    except (OSError, ValueError):
        return False


def open_controller():
    if not service_ready():
        # Preserve the venv symlink: resolving it would lose installed packages.
        python = ROOT / ".venv" / "bin" / "python"
        if not python.is_file():
            raise RuntimeError("项目虚拟环境不存在，请先按 macOS 安装说明创建 .venv。")
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join(dict.fromkeys([
            "/opt/homebrew/bin", "/usr/local/bin", *env.get("PATH", "/usr/bin:/bin").split(os.pathsep),
        ]))
        result = subprocess.run([str(python), str(ROOT / "autostart_macos.py")],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        deadline = time.monotonic() + 20
        while not service_ready():
            if time.monotonic() >= deadline:
                detail = result.stderr.strip() if result.returncode else "请检查 runtime/server.log。"
                raise RuntimeError("副屏服务未能启动。" + detail)
            time.sleep(.2)
    subprocess.run(["/usr/bin/open", URL], check=True)


def launcher_source(root):
    command = shlex.join([str(root / ".venv" / "bin" / "python"), str(root / "open_macos.py")])
    return ("try\n"
            f"    do shell script {json.dumps(command, ensure_ascii=False)}\n"
            "on error errorMessage\n"
            '    display alert "副屏管理启动失败" message errorMessage as critical\n'
            "end try\n")


def install_desktop_launcher():
    destination = Path.home() / "Desktop" / "副屏管理.app"
    if destination.exists():
        raise RuntimeError(f"入口已存在，未覆盖：{destination}")
    subprocess.run(["/usr/bin/osacompile", "-o", str(destination)],
                   input=launcher_source(ROOT), text=True, check=True)
    print(f"已安装桌面入口：{destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-desktop", action="store_true", help="Install a silent desktop app without opening it")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("This launcher requires macOS.")
    if args.install_desktop:
        install_desktop_launcher()
    else:
        open_controller()


if __name__ == "__main__":
    main()

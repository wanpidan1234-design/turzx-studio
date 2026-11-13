"""Build a self-contained UI bundle using the installed Python runtime and cswap."""
import argparse
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'runtime'/'Claude 账号面板.app')
    parser.add_argument('--python', default=sys.executable)
    args = parser.parse_args()
    cswap = shutil.which('cswap')
    if not cswap:
        raise SystemExit('请先安装 cswap。')
    app = args.output.expanduser().resolve()
    if app.exists():
        raise SystemExit(f'输出目录已存在：{app}。请指定新的 --output。')
    contents = app/'Contents'
    resources = contents/'Resources'
    executable = contents/'MacOS'/'ClaudeAccountPanel'
    resources.mkdir(parents=True)
    executable.parent.mkdir()
    for name in ('account_app.py', 'claude_subscription.py'):
        shutil.copy2(ROOT/name, resources/name)
    shutil.copy2(ROOT/'macos'/'AccountPanel.icns', resources/'AccountPanel.icns')
    web = resources/'web'
    web.mkdir()
    for name in ('account-app.html', 'account-app.css', 'account-app.js', 'claude.js', 'claude.css', 'design-tokens.css'):
        shutil.copy2(ROOT/'web'/name, web/name)
    shutil.copytree(ROOT/'web'/'assets'/'claude', web/'assets'/'claude')
    shutil.copytree(ROOT/'web'/'fonts', web/'fonts')
    shutil.copy2(ROOT/'web'/'assets'/'account-panel.svg', web/'assets'/'account-panel.svg')
    with (resources/'Runtime.plist').open('wb') as stream:
        plistlib.dump({'Python': str(Path(args.python).absolute()), 'Cswap': cswap}, stream)
    with (contents/'Info.plist').open('wb') as stream:
        plistlib.dump({'CFBundleIdentifier': 'local.turzx.claude-account-panel',
                      'CFBundleName': 'Claude 账号面板', 'CFBundleDisplayName': 'Claude 账号面板',
                      'CFBundleExecutable': 'ClaudeAccountPanel', 'CFBundlePackageType': 'APPL',
                      'CFBundleShortVersionString': '1.0', 'CFBundleVersion': '2', 'CFBundleIconFile': 'AccountPanel',
                      'NSHighResolutionCapable': True,
                      'NSAppTransportSecurity': {'NSAllowsLocalNetworking': True}}, stream)
    subprocess.run(['swiftc', str(ROOT/'macos'/'AccountApp.swift'), '-o', str(executable),
                    '-framework', 'Cocoa', '-framework', 'WebKit'], check=True)
    subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True)
    print(app)


if __name__ == '__main__':
    main()

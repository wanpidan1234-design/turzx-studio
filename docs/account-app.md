# Claude 账号面板 App

macOS 独立 App 复用副屏的 Claude 多账号页面。当前三个账号分别显示为可点击的卡片。点击卡片切换本机默认 Claude Code 账号。支持鼠标、触摸和 Tab / Enter 键盘操作。

App 从现有副屏服务读取背景选择、图片亮度、色彩浓度和淡化值。App 使用同一份账号快照。副屏服务未运行时，App 仍可读取账号服务的快照，背景保留最近读取的样式；首次启动默认使用「侧望凝思」。App 使用暖橙色三卡片图标。图标覆盖 16–1024 像素，并写入 macOS 应用包与网页 favicon。窗口随尺寸缩放。横屏使用 1280×720 构图，竖屏使用 720×1280 构图。

## 打开与构建

本机安装位置：`~/Applications/Claude 账号面板.app`。双击打开。关闭窗口或按 Command-Q 退出。App 不注册登录启动项。

重新构建时指定尚不存在的输出目录：

```sh
python3 macos/build_account_app.py --output "$HOME/Applications/Claude 账号面板.app"
```

构建需要 macOS Swift 编译器、Python 3.10+ 和已安装的 `cswap`。App 包含网页、图片、Python 服务和原生窗口程序。App 使用构建时的本机 Python 和 cswap 路径，因此不是跨机器分发包。移动本机代码仓库不影响已经构建的 App。Python 或 cswap 的安装路径改变时，需要重新构建。

也可在浏览器使用：

```sh
python3 account_app.py --port 8766
```

打开 `http://127.0.0.1:8766/`。账号服务须已配置账号并生成 `schedule-status.json`。App 不创建示例账号。

## 切换行为

每次点击调用 `cswap switch <账号编号> --json`。cswap 管理凭据、文件锁和切换保护。App 不读取或复制 OAuth 凭据，不使用 `--force`。运行中的 Claude Code 会话可能需要重新打开才能采用新账号。已有自动调度规则继续生效，因此自动调度可以再次变更当前账号。

服务验证账号编号存在于有效快照中。切换请求串行执行。页面在请求期间禁用所有卡片。命令返回目标账号后，页面更新「当前」标记，并请求账号服务刷新。更新后的调度快照优先于命令结果。切换确认最多补偿 30 秒的快照延迟。

命令超时为 45 秒。超时或无法确认目标时，页面显示错误，不宣称切换成功。快照过期或连接中断时，页面禁用切换。

独立服务只监听 `127.0.0.1`。原生 App 每次启动使用系统分配的空闲端口。切换接口检查 Host、Origin、随机会话令牌和 JSON 请求格式。浏览器只能读取公开页面资源及脱敏账号快照。CLI 输出不返回浏览器。

## 验证

```sh
python3 -m py_compile account_app.py macos/build_account_app.py
python3 -m unittest discover -s tests -p test_account_app.py -v
node --check web/account-app.js
node tests/test_claude_ui.cjs
# 启动 account_app.py 后执行：
node tests/test_account_app_ui.cjs
```

后端测试使用模拟命令，覆盖成功、已是当前账号、目标不符、错误返回、超时、无效编号、过期快照、并发请求和跨站请求。浏览器测试使用模拟数据，验证 1280×720、720×1280 和 390×844 布局，以及点击、键盘、焦点、请求锁定和失败显示。测试不切换真实账号。

图标矢量源文件为 `web/assets/account-panel.svg`。macOS 图标为 `macos/AccountPanel.icns`，原始 PNG 为 `macos/AccountPanel.png`。构建脚本自动复制图标并设置 `CFBundleIconFile`。

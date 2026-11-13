# TURZX Studio · 图灵副屏工作台

<img src="web/assets/turzx-studio-256.png" alt="TURZX Studio icon" width="96">

**把 USB 副屏变成可切换的实时看板。**

macOS 可通过 PyUSB/libusb 连接同型号副屏，见 [macOS 运行与设备验证](docs/macos.md)。新增 Claude 订阅屏幕与 1–5 账号总览，见 [Claude 与 cswap 屏幕](docs/claude-cswap.md)。

TURZX Studio 是本地运行的 Windows / macOS 应用：浏览器负责预览和控制，电脑把页面渲染成不透明 RGBA PNG，再通过WinUSB 或 libusb 发送给图灵副屏。包含十一种页面、实时硬件数据、OpenAI 订阅额度、横竖屏重排、自动轮播、专注计时和便签。

A local Windows / macOS control panel and page renderer for the TURZX 5.2-inch USB display. Uses Python, Playwright and WinUSB / libusb. Local scenes work offline; the optional OpenAI subscription scene reads the signed-in account online.

![生成氛围页面](docs/images/ambient.png)

macOS 独立 [Claude 账号面板 App](docs/account-app.md) 复用副屏画面。点击账号卡片即可通过 cswap 切换本机默认 Claude Code 账号。

## 支持范围

| 项目 | 当前支持 |
|---|---|
| 已验证设备 | TURZX 5.2 英寸 USB，`VID:PID 1CBE:0050` |
| 画布 | 横屏 `1280×720`；设备原生帧 `720×1280` |
| 系统 | Windows 10 / 11；macOS（PyUSB/libusb） |
| 传输 | Windows 原生 WinUSB / macOS libusb，完整 RGBA PNG 帧 |
| 控制台 | `http://127.0.0.1:8765/`，仅监听本机 |

这是社区项目，与 TURZX 厂商无隶属关系。旧款串口 5 英寸屏和其他 PID 尚未验证，不应直接套用本驱动。本应用不会自动安装驱动、刷固件或写入设备持久设置；Windows 登录自启动需单独启用。

## 快速开始

准备 Python 3.10+、Node.js 18+ 和 Google Chrome。设备应已使用 Microsoft WinUSB 驱动。

```powershell
git clone https://github.com/wanpidan1234-design/turzx-studio.git
cd turzx-studio
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
.\启动.cmd
```

投屏配置自动保存到本机 `runtime/display-preferences.json`，重新打开后恢复上次页面、背景、颜色、背光、轮播、便签及场景设置。完整字段和恢复规则见 [最后配置记忆](docs/macos.md#最后配置记忆)。

正在投屏时关闭服务，下次启动会自动继续投屏；先点击“停止”再关闭，下次保持停止。USB 断开后服务会等待设备接回并自动恢复：设备缺席时每 2 秒只读检查，连接失败时按 2、4、8、16、30 秒间隔重试，成功发送一帧后重置间隔。手动停止或关闭服务会取消自动重连。

macOS 用户使用 `.venv/bin/python autostart_macos.py` 启用登录启动；取消时加 `--disable`。配置、恢复投屏和日志说明见 [macOS 登录启动](docs/macos.md#登录后自动启动)。

执行 `.venv/bin/python open_macos.py --install-desktop` 安装桌面「副屏管理.app」。该入口会复用或启动服务，再打开管理页；关闭服务后也能通过它重新打开。

### Windows 登录后静默启动

在项目目录执行 `./autostart.ps1` 启用当前 Windows 用户的登录启动项，执行 `./autostart.ps1 -Disable` 取消。启用后直接由 `pythonw.exe` 运行 `background_start.pyw`，不经过 PowerShell、CMD 或浏览器，不弹控制台，也不打开控制页面。后台按保存的选项决定是否投屏；USB 稍后接入也会恢复。启动日志在 `runtime/background-start.log`。

此方式在当前用户登录 Windows 后启动，以便使用该用户的订阅登录信息；它不是登录前的系统服务。手动运行 `启动.cmd` 仍会打开控制台网页。重复的后台启动会复用已有服务，不重复占用副屏。

启动器优先使用项目的 `.venv\Scripts\python.exe`，否则使用 PATH 中的 Python。已有服务时会复用。也可以在终端运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 server.py
```

1. 打开控制台，选择页面并预览，然后点击「开始投屏」。
2. 默认横屏方向为 270°，实物朝向相反可选 90°；竖放可选 0° 或 180°。
3. 数据页从 2 fps 开始，动画可尝试 5 fps。实际发送速度与面板刷新率不同。
4. 「停止」释放 USB，屏幕保留最后一帧。完全退出服务请运行 `停止.cmd`。

选页、计时和便签在服务运行期间保留，退出后恢复默认值。亮度无法读回，初始值标为未知，只有主动调整滑块才发送亮度命令。

## 十一种页面

| 页面 | 内容 |
|---|---|
| 性能脉搏 | CPU、内存、GPU、显存和本地磁盘 |
| 网络航道 | 实体网卡的实时收发与历史曲线 |
| 此时此刻 | 北京时间与东京、伦敦、纽约时间 |
| 专注空间 | 可暂停倒计时和便签 |
| 动画实验室 | 轨道、极光、流场和星际漫游，支持速度、细节、暂停与时钟开关 |
| OpenAI 订阅 | ChatGPT 功能剩余次数、Work / Codex 共享额度、真实订阅周期与续费状态，VS Code 浅色风格 |
| Claude 订阅 | 当前 cswap 账号的 5 小时、7 天与模型独立额度，原创二次元形象 |
| Claude 多账号 | 1–5 个账号同页显示 5h、7d、Fable 已使用额度与单行重置倒计时 |
| 音乐一隅 | 媒体数据源尚未接入时的明确空态 |
| 更多可能 | 已实现、待接入、待验证能力说明 |
| 显示校准 | 四角、色条、灰阶、字号与圆形测试 |

均支持横竖重排。控制发生在电脑浏览器，不假设屏幕具备触控。

### 动画实验室

选择「动画实验室」后，可在右侧切换四种效果，调整 0.25–2 倍运动速度，选择细腻或轻量细节，暂停/继续、隐藏时钟，或用「换一幅」更换可复现的图形种子。速度控制动画本身的节奏，发送帧率控制设备更新频率，两者相互独立。

动画使用共享的时间基准，低发送帧率不会把整体运动拖慢。浏览器预览最高约 30 fps；实体屏仍受图像编码和 USB 事务速度限制。切出动画页、隐藏浏览器标签或启用减少动态效果时，非必要绘制会停止。

实体屏的动画帧直接从 Canvas 获取，其他页面保留浏览器截图路径；两者最终都转换为已经验证的原生不透明 RGBA PNG。控制台显示最近帧率、每帧大小和绘制/转换/传输耗时，便于比较效果与细节设置。

### OpenAI 订阅

本机已安装并登录 ChatGPT 账户的 Codex CLI 后，选择「OpenAI 订阅」即可同时查看 ChatGPT 深度研究、图像生成等实际返回的功能剩余次数，Work / Codex 共享额度，以及订阅账期、下次续费、自动续费和购买渠道。额度每 60 秒同步，账单正常情况下每 30 分钟同步；支持手动刷新全部来源、三页切换和 15 秒轮播，功能明细每页最多四项。

账户和共享额度来自 Codex app-server；ChatGPT 功能额度与续费信息来自 ChatGPT 网页账户接口。后者会读取当前 Codex 的 `auth.json` OAuth 凭据，在内存中使用并校验邮箱一致性，同时通过 OAuth `account_id` 的私有哈希识别同邮箱下的工作区变化；请求前再次校验，身份失效立即清除全部 ChatGPT 来源缓存。只向固定 `chatgpt.com` HTTPS 接口发送，禁止重定向，不另存凭据或向页面暴露 token。额度初始化请求不含 prompt/messages，不执行推理、支付或重置兑换。

网页账户接口不是稳定的公共 API，可能变更；各来源分别记录成功、失败与过期，失败保留旧采样或显示空态。明细页展示普通聊天限制状态和高级语音可用性，但独立剩余条数／分钟数仍未返回；空模型列表或“可用”不代表无限。金额页按当前 USD 月付套餐匹配官方目录，显示“套餐标价”，与实扣金额区分。OpenAI API 用量与账单不纳入本页。详见 [OpenAI 订阅接入与使用](docs/openai-subscription.md)。

## 数据口径

- CPU、内存、实体网卡约每秒采集；固定本地磁盘约每 30 秒采集，排除网络映射盘。
- GPU 使用 DXGI 匹配适配器，再采集对应 PDH 计数器；总显存采用 64 位字段，避免 WMI 的 4 GB 截断。
- 温度、风扇、功耗和实时 CPU 频率未接入时显示缺失，不使用随机数或零代替。
- 容量为 GiB，速率为 B/s、KiB/s、MiB/s。网卡连接不等于互联网服务可达。

## PNG 格式约束

参考设备上，**RGB PNG 虽收到成功 ACK，却出现重复条带和旧背景。** 当前发送路径强制使用 `720×1280`、alpha=255 的 **RGBA PNG（color type 6）**。修复后校准图经人工对照确认完整且方向正确；驱动会拒绝 RGB PNG。

图片上限为 1 MiB，超限不会静默切换到另一个显示层。有限测试中，八页巡回约 2 fps，新动画实验室的竖屏细腻模式约 5.7–6.3 fps；这些结果不是面板刷新上限。详见[硬件、协议与实测说明](docs/hardware-and-protocol.md)及[动画探索记录](docs/animation-exploration.md)。

## 开发与验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m py_compile server.py telemetry.py turzx_usb.py subscription.py chatgpt_account.py
node --check renderer.cjs
node --check web/studio.js
node --check web/display.js
node --check web/subscription.js
node tests/test_subscription_ui.cjs
```

格式测试不需要 USB。硬件更改应先发送一张校准图并目视确认，再进行有限时长的连续测试。

```text
web/                 控制台、展示页、图标和自托管字体
server.py            本地服务、USB 所有权、计时和进程生命周期
renderer.cjs         独立无头 Chrome 渲染
turzx_usb.py         ctypes WinUSB 与图像协议
telemetry.py         psutil / DXGI / PDH 遥测
subscription.py      Codex 账户连接、独立来源同步与脱敏快照
chatgpt_account.py   ChatGPT 网页功能额度、订阅周期和续费信息读取
tests/               无硬件格式回归测试
docs/                公开研究与示例截图
runtime/             本地生成的日志和描述符，不进入 Git
```

图标提供 SVG 和 16–256 px 多尺寸 ICO，位于 `web/assets/`。渲染器优先加载项目的 Playwright，也兼容 Codex 已有的捆绑运行时。

## 边界与后续方向

H.264 直传、离线播放、官方桌面模式及播放器、天气、训练任务、智能家居数据源仍需单独集成或验证。当前 USB 图像模式不是 Windows 原生扩展显示器。触控、音频、面板型号、实际功耗和亮度 nits 尚未确认。

若设备被其他程序占用，停止另一控制软件后手动重连；本应用不会结束未知进程。

## 资料与第三方许可

- [TURZX 官方目录](https://www.turzx.com/)及[5.2 英寸软件下载页](https://www.turzx.com/2025/08/07/52_inch/)。
- [turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python)：型号与兼容性资料；其 GPL 源码未打包进本项目。
- [usausa/turing-smart-screen](https://github.com/usausa/turing-smart-screen)：MIT 协议参考，许可见 [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt)。
- Manrope 字体：SIL OFL 1.1，见 [OFL-Manrope.txt](web/fonts/OFL-Manrope.txt)。


## 设计稿实现

界面已按 2026-11-13 的 TURZX 设计稿改版，覆盖 11 个场景、OpenAI 三页、四种动画、Claude 0–5 账号布局，以及桌面和窄屏管理页。样例账号与额度只用于浏览器验证，不写入运行配置。详见 [设计实现与验证](docs/design/designer-handoff/implementation.md)。

Inter 字体自托管于 `web/fonts/InterVariable.woff2`，许可见 `web/fonts/OFL-Inter.txt`。


人物图片可在管理页「显示 → 背景图片」调整亮度、色彩浓度和淡化程度。设置自动保存，并同步到 Claude 与 OpenAI 背景。默认浅亮参数为 112%、85%、12%。

Claude 背景现可在「显示 → 背景图片」点击缩略图选择：从容站姿、侧望凝思、抬手相伴或纯色。OpenAI 的背景选择与透明度也放在此处。选择自动保存，重启后保留。

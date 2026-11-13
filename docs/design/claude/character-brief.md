# Claude 屏幕形象

## 当前背景选择

管理页可选择三款新版人物（从容站姿、侧望凝思、抬手相伴）或纯色背景。默认保留 01 从容站姿，选择自动保存。图片色彩使用管理页的亮度、色彩浓度和淡化参数，推荐值为 112%、85%、12%。以下内容保留各次素材接入时的历史记录。

新增两张原图分别保存为 `claude-v3-thought-landscape-original.png` 和 `claude-v3-greeting-landscape-original.png`，与用户工作区已交付的 02、03 PNG 字节一致。显示资源缩放到 1280×720，保留 RGB 色彩；横竖屏使用响应式构图，图片由页面根据账号数量定位。

可用 `prepare_assets.py --version v3-thought` 或 `--version v3-greeting` 重新导出资源。缩略图只用于管理页选择。

## v3 接入记录：新版 01－从容站姿

当前显示微调：用户要求「改淡色一点」，人物与背景图片使用 `saturate(.92) brightness(1.04)`，即饱和度 92%、图片亮度系数 1.04。仅处理图片，文字和额度卡片不参与；物理帧 gamma=1、saturation=1，原图文件不改写。下述无滤镜设置是接入 v3 时的初始状态。

2026-11-13，用户明确指出目标是已生成三款新版的对比图，而不是旧版素材的调色变体。此前真实页面仍引用 v2，此次已将单账号页和三账号页同时切换为新版 01－从容站姿。

`claude-v3-landscape-original.png` 与已交付的 `01-从容站姿.png` 字节一致，原尺寸 1672×941。横屏仅等比例近似缩放到 1280×720；竖屏从右侧人物区域裁切适配 720×1280。导出不做 RGB 量化、调色、透明度混合或 AI 重绘。PNG 保存为不透明 RGBA。脚本 `prepare_assets.py --version v3` 可重复导出，默认版本为 v3。原图、旧版素材及另外两张新版保留。

页面使用 `claude-v3-landscape.png`、`claude-v3-portrait.png`，图片 opacity=1、filter=none。物理帧 gamma=1、saturation=1，保留已确认的 BRG 与原生 X=-60、背光 100%。这些设置保持软件源图色彩，不构成屏幕与电脑色彩一致性的实物证明。

两种页面、两个方向均核对了实际加载 URL、无滤镜、不透明、无横向溢出、无脚本错误。4 张完整原生帧为 268534–774525 字节，均小于 1 MiB；背景资源文件自身可以大于该上限，因为 USB 发送的是加入卡片后的完整帧。

## 历史版本 v2

用户指定参考：[大肥鱼：Claude大小姐，我来美国见你了！](https://www.bilibili.com/video/BV1oEWj6qExs/)，作者一颗佩佩。2026-11-13 实际观看视频并检查 22 秒、90 秒画面。以左侧橙发人物为身份参考。

保留铜橙长发、金橙眼睛、金花与黑缎带发饰、垂坠金饰、奶油白披肩、太阳花刺绣、高领褶边、花形胸针、黑领结和黑色裙装。没有使用右侧蓝发人物、视频场景、食物、字幕或水印。

画风和构图参考项目 OpenAI 龙娘背景：浅色留白、细线条、柔光、轻盈衣褶。只参考画风与位置，没有使用龙角、银发或绿色服装。横屏人物靠右，竖屏人物靠右下。人物位置按原图保留；页面信息排版以后续用户指定版本为准。

## 生成方式

用户已授权 CRS 图片接口。使用 imagegen 现有 CLI 的 edit 命令，经 CRS 调用 gpt-image-2，quality=high。输入 1 为对应方向的 OpenAI 背景；输入 2 为视频 90 秒的 Claude 人物裁剪。视频参考截图仅放在工作区 work/，不加入项目资源。

完整提示词：`claude-v2-landscape-prompt.txt`、`claude-v2-portrait-prompt.txt`。两次请求尺寸分别为 1536×864、864×1536。接口实际返回 1672×941、941×1672。导出脚本缩放为屏幕尺寸。

| 资源 | 实际尺寸 | 字节数 |
| --- | --- | --- |
| claude-v2-landscape-original.png | 1672×941 | 1890698 |
| claude-v2-portrait-original.png | 941×1672 | 1818140 |
| ../../../web/assets/claude/claude-v2-landscape.png | 1280×720 | 474785 |
| ../../../web/assets/claude/claude-v2-portrait.png | 720×1280 | 365144 |

运行 `.venv/bin/python docs/design/claude/prepare_assets.py --version v2` 可重复导出历史版本。RGB 每通道间隔 8 量化，输出 RGBA、PNG color type 6，alpha=255。原图保留。

## v2 简洁表格版本验证记录

横竖屏均显示 3 个账号与 6 个额度。没有文字溢出、列间重叠、浏览器脚本错误或可见 cswap 字样。人物面部不被面板遮挡。原生 BRG 校正后的完整页面帧为 737078、691230 字节，小于 1 MiB；尺寸均为 720×1280，RGBA，alpha=255。

两组现有 JavaScript 语义测试、JavaScript 语法检查、导出脚本 Python 编译与 diff 空白检查通过。

## 保留版本 v1

`claude-landscape-original.png`、`claude-portrait-original.png` 和 `prompts.json` 是旧针织背心版本，保留供追溯。导出旧版使用 `prepare_assets.py --version v1`。

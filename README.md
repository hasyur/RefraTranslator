# 游戏屏幕翻译器（原型）

这是 Windows 游戏屏幕翻译软件的实时原型：

1. DXcam 持续采集一个显示器区域，低分辨率变化检测负责限制 OCR 频率；
2. PP-OCRv6 small 识别日文/英文，首轮有效结果即建立 track/revision 并进入翻译；
3. 在跟踪前过滤图标、纯数字、中文/纯汉字及无关文字，避免发送给 LLM；
4. 通过 OpenAI-compatible API 调用 `hy-mt1.5-7b`；
5. 严格校验批量翻译的 `<sn id="...">` 对应关系，失败时自动重试并拆分故障批次；
6. 在鼠标穿透的透明窗口中仅模糊原文字区域，并用带细描边的清晰字体绘制中文译文；
7. 使用 `WDA_EXCLUDEFROMCAPTURE` 排除覆盖层，避免翻译结果被再次 OCR。
8. 可为每个游戏选择独立 Profile，隔离术语表、模型缓存和人工修订。

程序不注入游戏进程、不区分说话人，也不管理 LLM 推理服务器。当前支持普通窗口和无边框窗口；独占全屏不在原型保证范围内。

## 图形化启动器（推荐）

完成环境安装后，可以直接双击项目根目录的 `start_gui.bat`，或运行：

```powershell
.\.venv\Scripts\python.exe -m game_screen_translator --config config.toml gui
```

启动器可以直接完成：

- 新建和切换每游戏 Profile；
- 在“跟随系统 / 浅色 / 深色”之间切换界面色调；
- 编辑 OpenAI-compatible API 服务器地址，并从 `/v1/models` 读取或手填模型 ID；
- 设置 1–32 路 LLM 翻译并发；实际吞吐仍取决于后端能力和显存；
- 在 CPU 与检测到的 NVIDIA GPU 之间切换 OCR 设备；
- 选择显示器，并在屏幕截图上拖拽框选字幕区域；
- 编辑并保存游戏术语表；
- 编辑最高优先级的人工修订；
- 查看模型缓存、人工修订及命中统计；
- 使用当前项目虚拟环境启动实时翻译。

界面色调会立即生效，并保存到项目配置文件旁的 `.gui-settings.toml`；这个文件只属于当前项目，不写 Windows 注册表。浅色和深色主题都会显式设置文字、输入框、表格及背景颜色，避免系统深色模式造成白底白字。

启动页中的“API 服务器”和“API 模型”均可编辑。点击“读取模型列表”会异步请求当前地址的 `/models`（例如地址填写到 `/v1` 时，实际请求 `/v1/models`），不会阻塞 GUI；返回的模型可以下拉选择，也可以保留手填 ID。“LLM 并发”控制同时处理的翻译批次数，“OCR 设备”会列出 CPU 与 `nvidia-smi` 检测到的显卡。“OCR 过滤”可以随时勾选或取消；关闭后图标、数字、中文及其他非源语言 OCR 文本也会进入跟踪和翻译，但 OCR 置信度阈值仍然生效。点击“保存服务与 OCR 设置”或直接启动实时翻译，会原子更新本机 `config.toml` 中 API 地址、模型、并发数、`ocr.device` 和 `ocr.text_filter_enabled`。已有实时翻译进程不会中途切换，设置从下一次启动开始生效。

框选坐标会按照 Windows DPI 缩放换算为屏幕采集像素，并保存到当前 Profile 的 `settings.toml`。启动实时翻译后，启动器会自动最小化；即使 Windows 无法将它排除出采集，也不会长期出现在 OCR 画面中。

## 环境隔离

所有 Python 包都安装在项目目录的 `.venv`，不会写入系统或 Anaconda 的全局 site-packages。脚本和文档中的命令也始终显式调用 `.venv\Scripts\python.exe`，无需激活环境。安装缓存位于 `.cache\pip`，PaddleOCR 模型位于 `.cache\paddlex`，不会使用用户级 `~/.paddlex`。

安装核心与开发依赖：

```powershell
.\bootstrap.ps1
```

需要使用 CPU OCR 时：

```powershell
.\bootstrap.ps1 -WithOcr
```

安装 CPU OCR、GUI 和采集依赖：

```powershell
.\bootstrap.ps1 -WithOcr -WithGui
```

NVIDIA GPU OCR 使用独立开关；它会先移除 `.venv` 中的 CPU Paddle，再从 Paddle 官方 CUDA 仓库安装 GPU 版本及运行库：

```powershell
.\bootstrap.ps1 -WithGpuOcr -WithGui
```

GPU 默认使用 CUDA 12.9 wheel；可通过 `-GpuCuda cu118|cu126|cu129|cu130` 选择其他官方构建。`-WithOcr` 与 `-WithGpuOcr` 互斥，但 GPU Paddle 本身仍可在 GUI 中切回 CPU 推理。首次 GPU 安装需要下载约数 GB 的隔离运行库，不要求向系统 Python 安装包。

`.venv/`、`.cache/`、本机的 `config.toml` 和 `.gui-settings.toml` 都已加入 `.gitignore`。可公开的配置模板是 `config.example.toml`。

## 配置

本机 `config.toml` 已指向当前测试服务：

```toml
[translation]
base_url = "http://192.168.5.2:1234/v1"
model = "hy-mt1.5-7b"

[ocr]
device = "gpu:1" # 第二张 NVIDIA GPU；CPU 使用 "cpu"
```

API key 不是必填。若以后服务器要求鉴权，只通过 `GAME_SCREEN_TRANSLATOR_API_KEY` 环境变量提供，不写进配置文件。

## 每个游戏独立的 Profile

持久化数据不会使用全局共享缓存。先为游戏创建一个稳定 ID：

```powershell
.\.venv\Scripts\python.exe -m game_screen_translator --config config.toml profile init cyberpunk2077 --name "赛博朋克 2077"
```

生成目录为 `profiles\cyberpunk2077\`：

- `profile.toml`：Profile 身份信息；
- `settings.toml`：该游戏使用的显示器和字幕捕获区域；
- `glossary.toml`：可直接编辑的游戏术语表；
- `translations.sqlite3`：该游戏专属的模型缓存与人工修订。

这些内容可以在图形化启动器中维护。术语表也可直接编辑，格式如下；修改后重新启动翻译进程即可加载新版本：

```toml
[[terms]]
source = "フィクサー"
target = "中间人"

[[terms]]
source = "ナイトシティ"
target = "夜之城"
```

人工修订优先级高于术语表和模型缓存，适合固定纠正某一句 OCR 原文：

```powershell
.\.venv\Scripts\python.exe -m game_screen_translator --config config.toml profile correct cyberpunk2077 "待て。" "等等。"
.\.venv\Scripts\python.exe -m game_screen_translator --config config.toml profile info cyberpunk2077
.\.venv\Scripts\python.exe -m game_screen_translator --config config.toml profile uncorrect cyberpunk2077 "待て。"
```

模型缓存键包含规范化原文、源/目标语言、模型、提示词版本、术语表版本和最近上下文指纹；翻译条件变化时不会错误复用旧结果。人工修订只绑定本游戏、规范化原文和语言，因此不会因模型或上下文变化而失效。

`--profile` 必须指向已显式创建的 Profile，拼错名称时程序会停止并提示，不会偷偷新建或回退到其他游戏。省略 `--profile` 时只保留当前进程内的最近上下文，不读取或写入任何持久化翻译缓存。

## 验证和运行

启动实时翻译。若 Profile 已通过启动器保存区域，会优先使用该区域；否则使用 `config.toml`：

```powershell
.\.venv\Scripts\python.exe -m game_screen_translator --config config.toml live --profile cyberpunk2077
```

建议先限制到游戏字幕区域。参数含义是相对于显示器左上角的 `LEFT,TOP,WIDTH,HEIGHT`：

```powershell
.\.venv\Scripts\python.exe -m game_screen_translator --config config.toml live --profile cyberpunk2077 --region 100,700,1800,350
```

运行时右上角会出现一个不会被采集的控制窗口；点击“缩小”后会隐藏状态、过滤和延迟信息，仅保留紧凑的“恢复”和“关闭翻译”按钮，点击“恢复”可重新展开。DXGI 初始化失败时会自动尝试 WinRT。`--monitor 1` 可选择第二个显示器。

控制窗口会持续显示分阶段延迟的最近值和本次运行峰值：

- `OCR`：单轮 PaddleOCR 推理时间；
- `稳定`：文字首次被 OCR 识别到进入翻译队列的时间；默认首轮即入队，因此通常接近 0；
- `排队`：翻译批次等待可用翻译线程的时间；
- `LLM`：`/v1/chat/completions` 从发出请求到收到完整 JSON 响应的时间；命中本游戏缓存时显示“缓存命中”；
- `总计`：从画面变化触发首轮 OCR 到翻译结果可应用于覆盖层的时间。

控制窗口还会显示每轮 OCR 的“识别 / 保留 / 过滤”数量及本轮过滤原因。过滤发生在跟踪之前，因此被过滤的图标、数字和中文不会进入 LLM 队列。调试模式会同时打印每条被过滤文本及原因。

勾选“显示 OCR/翻译区域调试边框”或使用 `--debug-border` 时，同样的分段耗时也会逐批输出到终端。`OCR` 与 `稳定` 可能覆盖不同轮次，因此它们用于定位阶段瓶颈，不应简单相加来推算总延迟。

## OCR 性能与低负载设置

实时模式默认采用面向游戏的限流策略：DXcam 以 15 FPS 保留最新帧，变化检测每秒检查 6 次；变化检测同时关注全局平均值和局部高变化区域，避免一小行新字幕被整屏平均值吞掉。PaddleOCR 将检测输入最长边限制到 1280，首轮有效 OCR 立即入队，并且不再附加固定冷却。画面稳定 500 ms 后会补一次确认扫描，静止画面每 2 秒再做一次低频兜底复查；这两项分别由 `settle_rescan_ms` 和 `idle_rescan_ms` 控制，设为 `0` 可关闭。CPU 模式最多使用 2 个线程；GPU 模式可在启动器中选择具体卡号。翻译器进程在 Windows 上会切换为“低于正常”优先级，让游戏优先获得 CPU 时间。坐标会由 PaddleOCR 还原到原始画面，因此缩放不会改变覆盖层位置。

宽和高都为 `0` 代表整屏 OCR，适合文字位置不固定的游戏，但仍会识别更多无关 UI。限制字幕区域可以减少误识别和后续 LLM 请求。需要进一步降低扫描频率时，优先增大 `idle_rescan_ms`，其次可增大 `ocr_cooldown_ms`，或把 `stable_observations` / `stable_ms` 恢复为 `2` / `150`；代价是偶发漏检的恢复会变慢、短字幕也更容易错过。`cpu_threads` 只影响 CPU 模式。

默认文字过滤针对 `ocr.language = "japan"`：含假名的日文会保留，纯汉字/中文、纯数字、符号图标、单键提示和常见状态缩写会跳过，正常英文仍会翻译。日文与中文的纯汉字短语无法仅靠 OCR 文本可靠区分；游戏确实需要翻译“開始”“勝利”等纯汉字时，可设置 `translate_han_only = true`。不需要英文 UI 时可设置 `translate_latin = false`，要完全关闭这层规则则设置 `text_filter_enabled = false`。

这层规则减少的是稳定 OCR 次数和 LLM 请求数量；检测模型是否扫描整张画面仍由捕获区域决定。若当前 Profile 的宽和高都是 `0`，框选字幕带仍是降低单次 OCR 推理耗时最有效的办法。

可用内置日文样图验证整个实时闭环：

```powershell
.\.venv\Scripts\python.exe .\scripts\create_demo_image.py
.\.venv\Scripts\python.exe -m game_screen_translator --config config.toml live --region 0,0,1280,360 --duration 10 --debug-border --test-source .\output\demo_source.png
```

其余诊断命令如下。

检查服务与模型：

```powershell
.\.venv\Scripts\python.exe -m game_screen_translator --config config.toml doctor
```

直接验证翻译链路：

```powershell
.\.venv\Scripts\python.exe -m game_screen_translator --config config.toml translate "お前、本当に来たんだな。"
```

直接翻译和静态预览也支持 `--profile cyberpunk2077`，并遵守相同的术语与缓存契约。

生成静态截图翻译预览：

```powershell
.\.venv\Scripts\python.exe -m game_screen_translator --config config.toml preview .\sample.png --output .\output\preview.png
```

没有现成截图时，可生成一张日文演示图后跑同一条链路：

```powershell
.\.venv\Scripts\python.exe .\scripts\create_demo_image.py
.\.venv\Scripts\python.exe -m game_screen_translator --config config.toml preview .\output\demo_source.png --output .\output\demo_translated.png
```

运行不访问网络的单元测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

实时服务器联调测试默认跳过。显式设置开关后才会访问本地服务：

```powershell
$env:GAME_TRANSLATOR_LIVE = "1"
.\.venv\Scripts\python.exe -m pytest -m integration
```

## 已实现的实时安全契约

- 每条文字使用 `zone_id + track_id + revision` 标识；
- 多条批次必须完整返回请求中的 ID；格式失败会自动拆小重试，单条重试允许模型直接返回纯译文；
- 新 revision 出现后，旧请求即使晚到也不会覆盖屏幕上的新文字；
- 滚动导致 track 变化时，晚到译文只会接回到仍可见的完全相同原文；已经离屏的排队任务会尽量取消；
- 并发由客户端信号量限制，当前默认最多两个请求；
- 相同文字默认首轮有效 OCR 即发送；仍可通过配置恢复连续两次稳定确认；
- 覆盖层鼠标穿透、拒绝焦点，并从 Windows 屏幕捕获中排除；
- 服务离线或响应异常时明确报错，不会自动转发到云端。
- Profile ID 不能包含路径分隔符，Profile 根目录也只能位于项目配置目录内；
- 不同游戏的 SQLite 文件互不查询，人工修订总是先于模型缓存命中。
- 所有 SQLite 操作都会显式关闭连接，停止程序后可以立即移动或备份 Profile。

## 当前限制

- 每次运行只有一个活动捕获区域；可以通过图形化启动器、配置或 `--region` 选择；
- 游戏窗口移动后不会自动跟随，需要重新启动并更新区域；
- 最近 8 条翻译对照仅保留在当前进程内；
- 暂不自动识别说话人或区分人物语气；
- 暂无自动识别游戏窗口、随窗口移动以及 Profile 删除界面；
- GPU OCR 当前依赖 NVIDIA CUDA 版 Paddle；非 NVIDIA 显卡仍使用 CPU 路径。

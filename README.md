# RefraTranslator

RefraTranslator 是一款 Alpha 阶段的 Windows 游戏屏幕实时翻译工具。它截取指定屏幕区域，使用 PaddleOCR 识别日文或英文，通过用户自己的 OpenAI-compatible LLM 翻译，并将中文译文覆盖回原文字位置。

程序不会注入游戏进程，也不包含、下载或启动任何 LLM 后端及模型权重。

## 主要功能

- 图形化配置 API、模型、OCR 设备、字幕区域和每游戏 Profile；
- 支持 CPU 与 NVIDIA GPU OCR，翻译并发数可调；
- 每个游戏独立保存术语表、人工修订和翻译缓存；
- 原文字区域可选择“黑化模糊”或“仅模糊”，覆盖层鼠标穿透且不会被再次 OCR；
- 变化检测减少无效 OCR，并提供默认关闭的实验性动态 ROI 模式。

## 快速开始

需要：

- 64 位 Windows 10 或 Windows 11；
- 64 位 Python 3.11、3.12 或 3.13，并可在终端运行 `python`；
- 一个提供 `/v1/models` 和 `/v1/chat/completions` 的 OpenAI-compatible 翻译服务。

下载或克隆源码，并放到较短的目录（例如 `C:\RefraTranslator`）；不要让 GitHub ZIP 的长目录名重复嵌套，Paddle 在 Windows 下包含很深的文件路径。然后双击 `install.bat`。安装器会询问 OCR 使用 NVIDIA GPU（默认）还是 CPU。

所有 Python 包都安装到项目内的 `.venv`，不会污染系统环境；首次使用 GPU OCR 会下载数 GB 的运行库。

安装完成后：

1. 启动你自己的 LLM 服务；
2. 双击 `start_gui.bat`；
3. 在 GUI 中填写 API 地址并读取模型列表；
4. 创建游戏 Profile，选择显示器并框选字幕区域；
5. 点击“启动实时翻译”。

模板中的 `http://127.0.0.1:1234/v1` 只是示例地址，不代表程序自带服务。第一次运行 OCR 时还会将 PaddleOCR 模型下载到 `.cache\paddlex`。

## 更新

如果首次使用 `git clone` 获取源码，关闭 RefraTranslator 后双击 `update.bat` 即可增量更新 `main`。已有 `.venv`、OCR 模型、配置、Profile、日志和翻译缓存都会保留；只有 `pyproject.toml` 发生变化时才会更新 Python 环境。

GitHub ZIP 不包含 Git 历史，因此无法使用增量更新。希望长期更新时，建议只进行一次 Git 克隆和安装，之后始终保留同一个目录：

```powershell
git clone https://github.com/hasyur/RefraTranslator.git C:\RefraTranslator
```

更新器发现非 `main` 分支、detached HEAD 或尚未提交的源码改动时会安全停止，不会覆盖本机数据。

也可以显式选择安装类型：

```powershell
# CPU OCR
.\bootstrap.ps1 -WithGui -OcrDevice CPU

# NVIDIA GPU OCR
.\bootstrap.ps1 -WithGui -OcrDevice NVIDIA
```

## 使用建议

- 尽量只框选字幕区域，这是降低 OCR 延迟和无关翻译最有效的方法；
- 普通窗口和无边框窗口兼容性最好，独占全屏暂不保证可用；
- “实验性动态 ROI”默认关闭，适合在具体游戏中对比测试；
- LLM 并发只控制客户端请求数，实际速度仍取决于翻译后端与显存；
- Profile 会隔离不同游戏的术语表、人工修订和缓存；
- 当前不会识别说话人，也不会为不同人物自动生成不同语气。

动态 ROI 的设计、限制和测试结果见 [全屏动态 ROI 实验](docs/dynamic-roi-experiment.md)。所有配置项及默认值见 [config.example.toml](config.example.toml)。

## 排查问题

检查 API 服务与模型：

```powershell
.\.venv\Scripts\python.exe -m game_screen_translator --config config.toml doctor
```

常用日志：

- GUI 无法启动：`output\launcher.log`；
- 实时翻译异常退出或没有译文：`output\live.log`。

如果看不到控制框或译文，请先使用本机屏幕或有线显示器测试；部分无线投屏、虚拟显示器和捕获链路无法正确显示或排除覆盖层。

安装脚本成功后会清理 `.cache\pip` 下载缓存，但保留 OCR 模型。不要为了清理空间直接删除整个 `.cache`，否则下次需要重新下载模型。

## 开发与测试

安装开发环境并运行离线测试：

```powershell
.\bootstrap.ps1 -WithDev -WithGui -OcrDevice None
.\.venv\Scripts\python.exe -m pytest
```

仓库还提供不调用翻译程序的循环字幕靶场，可双击 `start_test_scenes.bat`；场景与按键见 [测试靶场说明](tests/manual/README.md)。

GitHub Actions 会在 Python 3.11、3.12 和 3.13 上运行离线测试，不会下载 OCR 模型或连接 LLM 服务。

## 当前限制

- 每次运行只有一个捕获区域，游戏窗口移动后需要重新框选；
- GPU OCR 目前仅支持 NVIDIA，其他显卡使用 CPU；
- 动态复杂背景可能使实验性 ROI 回退到整帧 OCR；
- 项目仍处于 Alpha 阶段，建议先在非关键环境测试。

## 许可证

RefraTranslator 源代码采用 [Apache License 2.0](LICENSE)。第三方依赖及再分发说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。LLM 后端和模型不属于本项目，其许可证需由使用者自行确认。

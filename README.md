# RefraTranslator

RefraTranslator 是一款 Windows 游戏屏幕翻译工具：它自动识别画面中的日文或英文，并把中文译文显示在原文字附近。

程序不会修改或注入游戏。目前仍是 Alpha 版本，建议先在普通窗口或无边框窗口中试用。

> [!IMPORTANT]
> 当前版本只支持 Windows 10/11 和 NVIDIA 显卡。没有可用的 NVIDIA 显卡时，实时翻译无法启动。

## 安装与启动

普通用户使用 Windows x64 安装包 `RefraTranslator-Setup.exe`。双击后选择安装目录即可，不需要先安装 Python，也不需要手动运行 pip 或 PowerShell。安装完成后从开始菜单或桌面快捷方式打开程序。

### 安装前确认

电脑需要满足以下条件：

- 64 位 Windows 10 或 Windows 11；
- 支持 CUDA 的 NVIDIA 显卡，并已安装可用的 NVIDIA 驱动；
- 首次安装和下载模型时可以访问网络，并有数 GB 可用磁盘空间。

安装前可以打开命令提示符，运行下面的命令确认 NVIDIA 驱动可用：

```powershell
nvidia-smi
```

`nvidia-smi` 应能列出 NVIDIA 显卡。当前版本仅支持 NVIDIA OCR。

### 从源码安装（开发环境）

源码仓库仍保留 `install.bat` 和 `bootstrap.ps1`，供开发和维护使用：

1. 获取项目文件：
   - 不使用 Git：在 GitHub 页面点击 **Code → Download ZIP**，下载后完整解压；
   - 使用 Git：运行 `git clone https://github.com/hasyur/RefraTranslator.git C:\RefraTranslator`。
2. 将项目放在较短、可写的本地路径，例如 `C:\RefraTranslator`。不要直接在 ZIP 压缩包内运行，也不建议放在层级很深的目录中；
3. 安装 64 位 Python 3.11、3.12 或 3.13，并确保 `python.exe` 可从 PATH 调用；
4. 双击项目根目录中的 `install.bat`；
5. 保持窗口打开，直到看到 `Installation completed successfully`；
6. 双击 `start_gui.bat` 启动 RefraTranslator。

安装程序会自动：

- 检查 Python 版本；
- 在项目目录创建独立的 `.venv` 虚拟环境；
- 安装图形界面、NVIDIA GPU OCR 和项目依赖；
- 更新时先检查已有 Paddle GPU 和 CUDA 能否正常运算；可用且版本兼容时直接复用，跳过 GPU 大包下载，否则重新安装；
- 首次安装时从 `config.example.toml` 创建本机 `config.toml`，再次安装时保留已有配置；
- 安装成功后清理 `.cache\pip` 中的安装下载缓存。

开发安装会把依赖放在项目目录的 `.venv` 中，不会安装到系统 Python。

### 第一次启动和配置

1. 首次打开会显示 OCR GPU 运行依赖、文字检测模型和文字识别模型的状态与大小；确认后点击 **下载并准备**。已存在并通过校验的资源会复用，失败后可以重试或稍后准备；
2. 工作台左侧固定为 `HOME → CAPTURE → OCR → TRANSLATION → OVERLAY → CACHE → SETTINGS` 七页导航；先在 **HOME / 总览** 的“常规设置”中点击 **＋ 新建**，输入游戏名称；
3. 在 **CAPTURE / 捕获** 中选择游戏所在的显示器；
4. 选择 **自定义区域**，点击 **框选区域**，只框住经常出现字幕的位置；
5. 进入 **OCR / 文字识别**，等待页面显示检测到的 NVIDIA 显卡，只有一张显卡时保持默认即可；
6. 在 **TRANSLATION / 翻译** 中选择 **内置本地模型（CUDA）**；
7. 第一次建议选择 **Hy-MT2 1.8B · Q8_0**，点击 **下载并使用**，等待下载和校验完成；
8. 打开游戏并让字幕出现在刚才框选的区域，然后点击工作台顶部的全局 **开始翻译**。顶部的 **应用更改** 也在所有页面共用。

首次准备只包含 NVIDIA OCR 运行依赖和 OCR 检测、识别模型，不会下载 llama.cpp、CUDA LLM 运行库或翻译模型。内置翻译仍由 **TRANSLATION / 翻译 → 下载并使用** 单独准备。

看到中文覆盖在原文字附近，就说明已经运行成功。工作台在实时翻译就绪后会隐藏，屏幕顶部会出现居中的只读状态条；需要调整或结束时，双击系统托盘中的 RefraTranslator 图标唤回工作台。工作台运行中点击右上角 **×** 会重新隐藏到托盘，翻译继续；点击顶部的 **停止翻译** 才会执行保存并停止流程。

### 日常启动

安装版用户从开始菜单或桌面快捷方式打开程序。开发安装用户可以双击 `start_gui.bat`。程序会自动选择上次使用的游戏配置，再点击 **开始翻译**。上次的配置不存在时会选择列表中的第一个配置；启动页面仍为 HOME。每个配置会独立保存捕获区域、OCR、翻译、覆盖层和运行参数；切换游戏配置时会整套切换，不会沿用另一个游戏的设置。主题、窗口状态、已下载模型文件和设备检测结果仍由本机共享。

在 **HOME / 总览 → 当前配置** 中选中已有配置后，点击 **删除** 并确认即可移除它。删除会一并移除该配置的设置、术语表、翻译缓存、手动修正和运行快照，无法撤销；翻译运行期间需先停止翻译。删除后会选择剩余配置，没有配置时可以点击 **新建**。

若文件占用导致清理未完成，配置仍会从列表移除，界面会提示残留目录；解除文件占用后可删除提示中的目录。

程序已在运行时，再次从开始菜单、桌面快捷方式或开发版 `start_gui.bat` 打开，会唤回已有工作台；如果正在翻译，会先保存并停止当前翻译，再打开工作台。

需要让 CMD 保持可见、实时查看启动输出时，改用 `start_gui(debug).bat`；两个入口调用的是同一个启动后端。

工作台的 **HOME / 总览 → 界面皮肤** 可以在 **Prism（原版）** 和 **Dohna（波普）** 之间切换，选择会保存在配置旁的本机 `.gui-settings.toml`，下次启动自动恢复。Dohna 使用固定的明亮配色；你在 Prism 中选择的跟随系统、深色或浅色偏好会保留，切回 Prism 后恢复。Dohna 的页面切换采用不透明内容组横向推入，按压和错误反馈采用短促的斜切色块，勾选“减少界面动效”或隐藏窗口时会立即收束。

### 安装中断或需要重装

- 首次资源下载中断：重新打开安装版，资源清单会复用已完成和可续传的文件；可以点击 **重试**，也可以先选 **稍后准备**，不影响打开工作台；
- 安装目录需要修复：关闭 RefraTranslator 后再次运行 `RefraTranslator-Setup.exe`，选择原安装目录。配置、游戏 Profile 和模型缓存保存在用户数据目录，不会随应用文件重装而清除；
- 安装版启动失败：检查 `%LOCALAPPDATA%\RefraTranslator\output\launcher.log`；
- 开发安装失败：使用 `start_gui(debug).bat` 查看即时输出，并检查项目目录下的 `output\launcher.log`；虚拟环境损坏时关闭 RefraTranslator，只删除项目根目录中的 `.venv`，再运行 `install.bat`；
- 实时翻译失败：安装版检查用户数据目录中的 `output\live.log`；开发安装检查项目目录下的 `output\live.log`。

### 开发环境（可选）

需要同时安装测试依赖时，在项目根目录打开 PowerShell，运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 -WithGui -WithDev
.\.venv\Scripts\python.exe -m pytest -m "not integration"
```

`bootstrap.ps1` 还支持 `-KeepInstallCache` 保留安装下载缓存；普通用户无需使用这些参数。

通过 ZIP 安装的用户更新时，可先退出程序并备份旧目录，再将新版 ZIP 解压后的文件覆盖到原安装目录，保留 `.venv`、`.cache`、`config.toml`、`.gui-settings.toml`、`profiles` 和 `output`，然后再次双击 `install.bat`。已有可用的 Paddle GPU 和 CUDA 环境会复用；翻译模型和 OCR 模型缓存也会保留。默认安装会保留兼容的现有 CUDA 版本；显式指定 `-GpuCuda` 时，安装程序会检查版本是否匹配，必要时安装指定版本。

## 常见问题

| 现象 | 先这样检查 |
| --- | --- |
| 开发安装无法读取 `WindowsApps\python.exe` 的版本 | 这通常是 Microsoft Store 执行别名，不是真正的 Python。安装 64 位 Python 3.11～3.13 并勾选 **Add python.exe to PATH**；若已安装，在 Windows“应用执行别名”中关闭 `python.exe` 和 `python3.exe` 的商店别名，再运行 `where.exe python` 与 `python --version` 确认 |
| 没有检测到显卡 | 确认电脑使用 NVIDIA 显卡并已安装驱动；当前版本不能改用 CPU OCR |
| 双击安装版后工作台没有打开 | 查看 `%LOCALAPPDATA%\RefraTranslator\output\launcher.log`；开发安装查看项目目录的 `output\launcher.log` |
| 点击开始后退出，或一直没有译文 | 查看 `output\live.log`，并确认框选区域内确实有日文或英文 |
| 内置模型显存不足 | 先使用 1.8B 模型，并把高级设置中的并发槽位保持为 1 |
| 看不到控制框或译文 | 先用本机有线显示器和窗口化游戏测试；部分无线投屏、虚拟显示器或捕获链路不兼容 |

模型下载中断后，可以再次点击 **下载并使用**；模型下载支持断点续传。

## 使用外部 API（可选）

如果你已经有 OpenAI-compatible 翻译服务：

1. 在 **翻译** 中选择 **外部 API**；
2. 填写 API 地址和 API Key；
3. 读取并选择模型，然后点击 **开始翻译**。

服务需要提供 `/v1/models` 和 `/v1/chat/completions`。API Key 会明文保存在当前 Profile 的本机 `settings.toml` 中；如果不想保存，可以留空并使用 `REFRA_TRANSLATOR_API_KEY` 环境变量。

## 更新

如果最初使用 `git clone` 获取的是源码开发目录，关闭 RefraTranslator，在克隆的项目目录打开 PowerShell，然后执行：

```powershell
git pull
```

如果更新修改了 `pyproject.toml` 中的依赖，开发安装更新后再双击 `install.bat` 安装依赖。普通安装版用户应使用对应的新 `RefraTranslator-Setup.exe` 并选择原安装目录。

源码 ZIP 下载不能使用增量更新；想长期更新源码，建议使用下面的方式只克隆一次：

```powershell
git clone https://github.com/hasyur/RefraTranslator.git C:\RefraTranslator
```

## 当前限制
- 内置模型只支持 Windows x64 + NVIDIA CUDA，不会回退到 CPU 或 Vulkan；
- 项目仍处于 Alpha 阶段，请先在非关键环境中试用。

## 许可证

RefraTranslator 源代码采用 [Apache License 2.0](LICENSE)。按需下载的 llama.cpp、NVIDIA CUDA 运行库、Hy-MT2 模型及其他第三方依赖使用各自的许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

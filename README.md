# RefraTranslator

RefraTranslator 是一款 Windows 游戏屏幕翻译工具：它自动识别画面中的日文或英文，并把中文译文显示在原文字附近。

程序不会修改或注入游戏。目前仍是 Alpha 版本，建议先在普通窗口或无边框窗口中试用。

> [!IMPORTANT]
> 当前版本只支持 Windows 10/11 和 NVIDIA 显卡。没有可用的 NVIDIA 显卡时，实时翻译无法启动。

## 最快上手

整个过程不需要输入命令，按照下面的顺序双击和点击即可。

### 1. 准备电脑

你需要：

- 64 位 Windows 10 或 Windows 11；
- 支持 CUDA 的 NVIDIA 显卡，以及可用的 NVIDIA 驱动；
- 64 位 Python 3.11、3.12 或 3.13；
- 首次安装和下载模型时可用的网络，以及数 GB 磁盘空间。

安装 Python 时，请勾选 **Add python.exe to PATH**。如果已经安装，可以在 PowerShell 中输入 `python --version` 检查版本。

### 2. 安装 RefraTranslator

1. 在 GitHub 页面点击 **Code → Download ZIP** 下载源码（会用 Git 的用户也可以直接克隆仓库）；
2. 把项目放到较短的路径，例如 `C:\RefraTranslator`；
3. 双击 `install.bat`；
4. 等到窗口显示 `Installation completed successfully`。

依赖会安装到项目自己的 `.venv` 目录中，不会混入系统 Python。安装和首次运行可能需要下载较大的 OCR 运行库及模型，请耐心等待，不要直接关闭窗口。

### 3. 第一次启动

1. 双击 `start_gui.bat`；
2. 工作台左侧固定为 `HOME → CAPTURE → OCR → TRANSLATION → OVERLAY → CACHE → SETTINGS` 七页导航；先在 **HOME / 总览** 的“常规设置”中点击 **＋ 新建**，输入游戏名称；
3. 在 **CAPTURE / 捕获** 中选择游戏所在的显示器；
4. 选择 **自定义区域**，点击 **框选区域**，只框住经常出现字幕的位置；
5. 进入 **OCR / 文字识别**，等待页面显示检测到的 NVIDIA 显卡，只有一张显卡时保持默认即可；
6. 在 **TRANSLATION / 翻译** 中选择 **内置本地模型（CUDA）**；
7. 第一次建议选择 **Hy-MT2 1.8B · Q8_0**，点击 **下载并使用**，等待下载和校验完成；
8. 打开游戏并让字幕出现在刚才框选的区域，然后点击工作台顶部的全局 **开始翻译**。顶部的 **应用更改** 也在所有页面共用。

看到中文覆盖在原文字附近，就说明已经运行成功。工作台在实时翻译就绪后会隐藏；需要结束时，在保留的实时控制窗口中点击 **关闭翻译**。

以后使用时，只需双击 `start_gui.bat`，选择已经保存的游戏配置，再点击 **开始翻译**。

## 常见问题

| 现象 | 先这样检查 |
| --- | --- |
| `install.bat` 提示找不到 Python | 确认安装的是 64 位 Python 3.11～3.13，并已加入 PATH |
| 没有检测到显卡 | 确认电脑使用 NVIDIA 显卡并已安装驱动；当前版本不能改用 CPU OCR |
| 双击后七页工作台没有打开 | 查看 `output\launcher.log` |
| 点击开始后退出，或一直没有译文 | 查看 `output\live.log`，并确认框选区域内确实有日文或英文 |
| 内置模型显存不足 | 先使用 1.8B 模型，并把高级设置中的并发槽位保持为 1 |
| 看不到控制框或译文 | 先用本机有线显示器和窗口化游戏测试；部分无线投屏、虚拟显示器或捕获链路不兼容 |

安装或下载中断后，可以直接重新运行 `install.bat` 或再次点击 **下载并使用**。模型下载支持断点续传。

## 使用外部 API（可选）

如果你已经有 OpenAI-compatible 翻译服务：

1. 在 **翻译** 中选择 **外部 API**；
2. 填写 API 地址和 API Key；
3. 读取并选择模型，然后点击 **开始翻译**。

服务需要提供 `/v1/models` 和 `/v1/chat/completions`。API Key 会明文保存在本机的 `config.toml` 中；如果不想保存，可以留空并使用 `REFRA_TRANSLATOR_API_KEY` 环境变量。

## 更新

如果最初使用 `git clone` 下载项目，关闭 RefraTranslator 后双击 `update.bat` 即可更新。配置、Profile、模型、日志和翻译缓存会保留。

ZIP 下载的项目不能使用增量更新；想长期更新，建议使用下面的方式只克隆一次：

```powershell
git clone https://github.com/hasyur/RefraTranslator.git C:\RefraTranslator
```

## 当前限制
- 内置模型只支持 Windows x64 + NVIDIA CUDA，不会回退到 CPU 或 Vulkan；
- 项目仍处于 Alpha 阶段，请先在非关键环境中试用。

## 许可证

RefraTranslator 源代码采用 [Apache License 2.0](LICENSE)。按需下载的 llama.cpp、NVIDIA CUDA 运行库、Hy-MT2 模型及其他第三方依赖使用各自的许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

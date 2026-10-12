# Third-Party Notices

RefraTranslator 自身的源代码采用 [Apache License 2.0](LICENSE)。第三方组件仍分别受其上游许可证约束；RefraTranslator 的 Apache-2.0 不会替代、扩展或缩减这些条款。

公开源码仓库不提交第三方 wheel、Windows 运行库或模型权重。`bootstrap.ps1` 仍用于开发安装，将所选依赖安装到项目内的 `.venv`。Windows 安装包内含 CPython 3.13.5 和 GUI 核心依赖；首次打开会先显示固定 Paddle GPU OCR 资源清单，用户确认后才从上游下载缺少的 OCR wheels 和检测、识别模型。内置 LLM 的运行时与模型仍由工作台现有“翻译 → 下载并使用”入口单独准备，不属于首次启动清单。权威条款以对应版本随附的许可证为准。

Windows 安装包保留 CPython 的 `LICENSE.txt`，并将核心 wheel 中声明的许可证文本复制到 `THIRD_PARTY_LICENSES/`。OCR wheels 在首次准备时下载并按固定 SHA-256 校验；安装后的 wheel `*.dist-info` 目录保留各自元数据与上游许可证文件。源码构建脚本从当前 Windows x64 CPython 3.13 构建环境解析 OCR 依赖清单，并将 wheel URL、字节数、SHA-256 和安装体积随安装包发布。清单通过小型发行元数据生成，不会下载 wheel。

## 直接运行时依赖

| 组件 | 用途 | 上游许可证 |
| --- | --- | --- |
| [HTTPX](https://github.com/encode/httpx) | OpenAI-compatible HTTP 客户端 | BSD-3-Clause |
| [Pillow](https://github.com/python-pillow/Pillow) | 图像处理与静态预览 | MIT-CMU |
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | 可选 OCR 引擎 | Apache-2.0 |
| [PaddlePaddle / PaddlePaddle GPU](https://github.com/PaddlePaddle/Paddle) | 可选 OCR 推理运行时 | Apache-2.0 |
| [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/) | 可选 GUI 与覆盖层 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only，另有 Qt 商业许可；以所用 Qt 组件和发行包为准 |
| [DXcam](https://github.com/ra1nty/DXcam) | 可选 Windows DXGI / WinRT 屏幕采集 | MIT |

主要的间接运行时组件包括：

| 组件 | 进入项目的路径 | 上游许可证 |
| --- | --- | --- |
| [PaddleX](https://github.com/PaddlePaddle/PaddleX) | PaddleOCR | Apache-2.0 |
| [NumPy](https://github.com/numpy/numpy) | OCR、采集与图像数组 | BSD-3-Clause |
| [OpenCV Python](https://github.com/opencv/opencv-python) | PaddleOCR / PaddleX 图像处理 | Apache-2.0；打包内容可能另含第三方条款 |

## 构建与测试依赖

| 组件 | 用途 | 上游许可证 |
| --- | --- | --- |
| [setuptools](https://github.com/pypa/setuptools) | 构建后端 | MIT |
| [pytest](https://github.com/pytest-dev/pytest) | 单元测试 | MIT |
| [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio) | 异步单元测试 | Apache-2.0 |

## 按需下载的本地 LLM 后端和模型

以下文件不会提交到源码仓库，而是在用户选择内置后端后直接下载到项目内的 `.cache/local-llm`：

| 组件 | 固定版本或文件 | 下载来源 | 上游许可证 |
| --- | --- | --- | --- |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | `b11146`，对应稳定标签 `v0.5.0` 的同一提交 | [官方 GitHub Release](https://github.com/ggml-org/llama.cpp/releases/tag/b11146) | [MIT](https://github.com/ggml-org/llama.cpp/blob/7fe450e19305b828c199d602c23a8337aaa1f03b/LICENSE) |
| NVIDIA CUDA 运行库 | llama.cpp 官方 Windows CUDA 12.4 运行库包 | [官方 GitHub Release](https://github.com/ggml-org/llama.cpp/releases/tag/b11146) | [NVIDIA Software License Agreement / CUDA Supplement](https://docs.nvidia.com/cuda/eula/index.html) |
| Tencent Hy-MT2 1.8B GGUF | `Hy-MT2-1.8B-Q8_0.gguf` | [Tencent-Hunyuan ModelScope](https://www.modelscope.cn/models/Tencent-Hunyuan/Hy-MT2-1.8B-GGUF/files) | [Apache-2.0](https://github.com/Tencent-Hunyuan/Hy-MT2/blob/main/LICENSE.txt) |
| Tencent Hy-MT2 7B GGUF | `Hy-MT2-7B-Q4_K_M.gguf` | [Tencent-Hunyuan ModelScope](https://www.modelscope.cn/models/Tencent-Hunyuan/Hy-MT2-7B-GGUF/files) | [Apache-2.0](https://github.com/Tencent-Hunyuan/Hy-MT2/blob/main/LICENSE.txt) |

下载器会检查预期字节数和 SHA-256，不会把许可证改变为 RefraTranslator 的 Apache-2.0。用户也可以继续选择自己的 OpenAI-compatible API；该外部服务及其模型不属于本项目。

## 再分发提醒

发布 Windows 安装包时，应针对该次构建实际采用的依赖树检查随包许可证文本和归属声明。尤其是分发 PySide6/Qt、NVIDIA CUDA 运行库或模型权重时，需要分别履行对应条款。本文件记录源码安装器和按需 OCR 资源准备的依赖边界，不代替针对具体发行物的合规审查。

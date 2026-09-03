# Third-Party Notices

RefraTranslator 自身的源代码采用 [Apache License 2.0](LICENSE)。第三方组件仍分别受其上游许可证约束；RefraTranslator 的 Apache-2.0 不会替代、扩展或缩减这些条款。

当前源码仓库不内嵌这些依赖的源代码、二进制文件或模型权重。`bootstrap.ps1` 会通过 Python 包索引将所选依赖安装到项目内的 `.venv`；用户在 GUI 中明确选择“下载并使用”后，程序还会从上游站点按需下载固定版本的本地推理运行时和所选模型。权威条款以对应版本随附的许可证为准。

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
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | `b10621`，对应稳定标签 `v0.3.0` 的同一提交 | [官方 GitHub Release](https://github.com/ggml-org/llama.cpp/releases/tag/b10621) | [MIT](https://github.com/ggml-org/llama.cpp/blob/c1d0e7a004015f23bc0233470b747b596f29b264/LICENSE) |
| NVIDIA CUDA 运行库 | llama.cpp 官方 Windows CUDA 12.4 运行库包 | [官方 GitHub Release](https://github.com/ggml-org/llama.cpp/releases/tag/b10621) | [NVIDIA Software License Agreement / CUDA Supplement](https://docs.nvidia.com/cuda/eula/index.html) |
| Tencent Hy-MT2 1.8B GGUF | `Hy-MT2-1.8B-Q8_0.gguf` | [Tencent-Hunyuan ModelScope](https://www.modelscope.cn/models/Tencent-Hunyuan/Hy-MT2-1.8B-GGUF/files) | [Apache-2.0](https://github.com/Tencent-Hunyuan/Hy-MT2/blob/main/LICENSE.txt) |
| Tencent Hy-MT2 7B GGUF | `Hy-MT2-7B-Q4_K_M.gguf` | [Tencent-Hunyuan ModelScope](https://www.modelscope.cn/models/Tencent-Hunyuan/Hy-MT2-7B-GGUF/files) | [Apache-2.0](https://github.com/Tencent-Hunyuan/Hy-MT2/blob/main/LICENSE.txt) |

下载器会检查预期字节数和 SHA-256，不会把许可证改变为 RefraTranslator 的 Apache-2.0。用户也可以继续选择自己的 OpenAI-compatible API；该外部服务及其模型不属于本项目。

## 再分发提醒

如果以后发布直接包含第三方二进制文件或模型权重的便携版/安装包，应当对最终冻结的完整依赖树重新生成许可证清单，并随包提供相应许可证文本和归属声明。尤其是分发 PySide6/Qt、NVIDIA CUDA 运行库或模型权重时，需要分别履行对应条款。本文件是源码 Alpha 阶段及按需下载模式的依赖边界说明，不代替针对具体发行物的合规审查。

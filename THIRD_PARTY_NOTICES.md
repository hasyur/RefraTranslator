# Third-Party Notices

RefraTranslator 自身的源代码采用 [Apache License 2.0](LICENSE)。第三方组件仍分别受其上游许可证约束；RefraTranslator 的 Apache-2.0 不会替代、扩展或缩减这些条款。

当前源码仓库不内嵌这些依赖的源代码或二进制文件。`bootstrap.ps1` 会通过 Python 包索引将所选依赖安装到项目内的 `.venv`。实际安装版本由 `pyproject.toml` 的版本范围和安装时可用的软件包共同决定，权威条款以对应版本随附的许可证为准。

## 直接运行时依赖

| 组件 | 用途 | 上游许可证 |
| --- | --- | --- |
| [HTTPX](https://github.com/encode/httpx) | OpenAI-compatible HTTP 客户端 | BSD-3-Clause |
| [Pillow](https://github.com/python-pillow/Pillow) | 图像处理与静态预览 | MIT-CMU |
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | 可选 OCR 引擎 | Apache-2.0 |
| [PaddlePaddle / PaddlePaddle GPU](https://github.com/PaddlePaddle/Paddle) | 可选 OCR 推理运行时 | Apache-2.0 |
| [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/) | 可选 GUI 与覆盖层 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only，另有 Qt 商业许可；以所用 Qt 组件和发行包为准 |
| [DXcam](https://github.com/ra1nty/DXcam) | 可选 Windows 屏幕采集 | MIT |

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

## LLM 后端和模型

RefraTranslator **不包含、下载或再分发任何 LLM 推理后端、模型代码或模型权重**。程序只连接用户自行提供的 OpenAI-compatible API。

HY-MT1.5 是开发期间验证过的可选后端之一，并不是 RefraTranslator 的组成部分或必要依赖。使用者需要自行审阅并遵守相应模型及推理软件的许可；例如 HY-MT1.5 使用独立的 [Tencent HY Community License Agreement](https://huggingface.co/tencent/HY-MT1.5-7B/blob/main/License.txt)，其中包含地域和用途限制。

## 再分发提醒

如果以后发布包含第三方二进制文件的便携版或安装包，应当对最终冻结的完整依赖树重新生成许可证清单，并随包提供相应许可证文本和归属声明。尤其是分发 PySide6/Qt 二进制文件时，需要按所选 LGPL、GPL 或商业许可履行对应义务。本文件是源码 Alpha 阶段的依赖边界说明，不代替针对具体发行物的合规审查。

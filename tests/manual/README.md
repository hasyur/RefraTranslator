# 动态字幕靶场

`animated_ocr_scenes.py` 是一个独立的循环画面生成器，只依赖 PySide6，不会导入、启动或调用 RefraTranslator。它的用途是让开发者和使用者在不同电脑上向任意屏幕翻译程序提供相同、可重复的动态输入。

在项目根目录双击 `start_test_scenes.bat`，或运行：

```powershell
.\.venv\Scripts\python.exe .\tests\manual\animated_ocr_scenes.py
```

固定场景如下：

1. 多行打字机：三行日文逐字出现，完成后短暂停留并清空；
2. 整行淡入淡出：测试低对比度阶段何时触发 OCR，以及清晰后能否补全；
3. 菜单上下滚动：文字会移动、停稳并进出裁剪边界；
4. 菜单左右滚动：卡片标题与说明横向移动并停稳；
5. 文字背景变化：字幕本身不变，背景光斑、色带和字幕底色持续变化。

窗口内按键：

- `1`–`5`：切换场景；
- `Space`：暂停或继续；
- `R`：从当前场景开头重播；
- `A`：每 14 秒自动轮换场景；
- `F11`：进入或退出全屏；
- `F1` / `H`：显示或隐藏帮助；
- `Esc`：退出全屏，窗口模式下关闭。

也可以直接选择场景和自动轮换时间：

```powershell
.\.venv\Scripts\python.exe .\tests\manual\animated_ocr_scenes.py --scene fade --fullscreen
.\.venv\Scripts\python.exe .\tests\manual\animated_ocr_scenes.py --auto-cycle 20
.\.venv\Scripts\python.exe .\tests\manual\animated_ocr_scenes.py --duration 30
.\.venv\Scripts\python.exe .\tests\manual\animated_ocr_scenes.py --list-scenes
```

建议先启动靶场，再让 RefraTranslator 框选窗口客户区。默认帮助层是隐藏的，不会额外干扰 OCR。每个场景都会无限循环；测试 OCR/ROI 行为时可以持续观察多轮，测试 LLM 首次端到端延迟时应以每条固定文本第一次出现为准，后续循环可能命中翻译缓存。

这属于人工测试工具，不会被 `pytest` 当成测试用例自动打开窗口。自动测试只离屏渲染固定时间点，确认所有场景仍可启动和绘制。

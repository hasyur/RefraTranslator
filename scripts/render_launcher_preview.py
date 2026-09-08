from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from game_screen_translator.config import load_config
from game_screen_translator.domain import GlossaryEntry
from game_screen_translator.gui.qml_workbench import QmlWorkbenchHost
from game_screen_translator.gui.theme import THEME_DARK, THEME_LIGHT
from game_screen_translator.gui.workbench_controller import WorkbenchController
from game_screen_translator.profiles import (
    ProfileCaptureSettings,
    create_game_profile,
    save_profile_capture_settings,
    save_profile_glossary,
)


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)
    dark_output_path = output_dir / "launcher_preview.png"
    light_output_path = output_dir / "launcher_preview_light.png"
    minimum_output_path = output_dir / "launcher_preview_minimum.png"
    with tempfile.TemporaryDirectory(dir=output_dir) as temporary_dir:
        config_path = Path(temporary_dir) / "config.toml"
        config_path.write_text(
            """
[translation]
provider = "openai_compatible"
backend = "external"
builtin_model = "Hy-MT2-1.8B-Q8_0.gguf"
base_url = "http://127.0.0.1:1234/v1"
model = "hy-mt1.5-7b"
target_language = "简体中文"
""",
            encoding="utf-8",
        )
        config = load_config(config_path)
        profile = create_game_profile(
            config_path,
            config,
            "cyberpunk2077",
            display_name="赛博朋克 2077",
        )
        save_profile_capture_settings(
            profile,
            ProfileCaptureSettings(monitor_index=0, region=(100, 700, 1800, 350)),
        )
        save_profile_glossary(
            profile,
            (
                GlossaryEntry("フィクサー", "中间人"),
                GlossaryEntry("ナイトシティ", "夜之城"),
            ),
        )
        profile.cache.set_manual_correction(
            "待て。",
            "等等。",
            source_language=config.ocr.language,
            target_language=config.translation.target_language,
        )

        app = QApplication.instance() or QApplication([])

        def render(
            theme: str,
            page: str,
            output_path: Path,
            *,
            size: tuple[int, int] = (1440, 960),
        ) -> None:
            controller = WorkbenchController(config_path, probe_ocr_devices=False)
            controller.setTheme(theme)
            controller.setReducedMotion(True)
            controller.setPage(page)
            host = QmlWorkbenchHost(controller, application=app)
            window = host.window
            if window is None:
                raise RuntimeError("QML 工作台没有创建窗口")
            window.resize(*size)
            host.show()
            app.processEvents()
            if not window.grabWindow().save(str(output_path)):
                raise RuntimeError(f"无法保存启动器预览：{output_path}")
            window.close()
            host.shutdown()
            app.processEvents()

        render(THEME_DARK, "HOME", dark_output_path)
        save_profile_capture_settings(
            profile,
            ProfileCaptureSettings(monitor_index=0, region=(0, 0, 0, 0)),
        )
        render(THEME_LIGHT, "CAPTURE", light_output_path)
        render(
            THEME_DARK,
            "SETTINGS",
            minimum_output_path,
            size=(980, 700),
        )
    print(dark_output_path)
    print(light_output_path)
    print(minimum_output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

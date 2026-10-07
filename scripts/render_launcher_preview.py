from __future__ import annotations

import os
import tempfile
from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
from time import monotonic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QPointF, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from game_screen_translator.config import load_config
from game_screen_translator.domain import GlossaryEntry
from game_screen_translator.gui.qml_workbench import QmlWorkbenchHost
from game_screen_translator.gui.theme import THEME_DARK, THEME_LIGHT, SKIN_DOHNA, SKIN_PRISM
from game_screen_translator.gui.workbench_controller import WorkbenchController
from game_screen_translator.profiles import (
    ProfileCaptureSettings,
    create_game_profile,
    save_profile_capture_settings,
    save_profile_glossary,
)


def main() -> int:
    parser = ArgumentParser(description="Render isolated RefraTranslator QML previews")
    parser.add_argument(
        "--motion",
        action="store_true",
        help="also capture a short real-QML Dohna page-transition GIF",
    )
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)
    dark_output_path = output_dir / "launcher_preview.png"
    light_output_path = output_dir / "launcher_preview_light.png"
    minimum_output_path = output_dir / "launcher_preview_minimum.png"
    dohna_home_output_path = output_dir / "launcher_preview_dohna_home.png"
    dohna_home_minimum_output_path = output_dir / "launcher_preview_dohna_home_minimum.png"
    dohna_home_popup_output_path = output_dir / "launcher_preview_dohna_home_popup.png"
    dohna_capture_output_path = output_dir / "launcher_preview_dohna_capture.png"
    dohna_minimum_output_path = output_dir / "launcher_preview_dohna_minimum.png"
    dohna_motion_output_path = output_dir / "launcher_preview_dohna_motion.gif"
    app = QApplication.instance() or QApplication([])

    for font_name in (
        "bahnschrift.ttf",
        "segoeui.ttf",
        "segoeuib.ttf",
        "seguisym.ttf",
        "consola.ttf",
        "msyh.ttc",
        "msyhbd.ttc",
        "ariblk.ttf",
    ):
        font_path = Path("C:/Windows/Fonts") / font_name
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
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

        def render(
            theme: str,
            page: str,
            output_path: Path,
            *,
            size: tuple[int, int] = (1440, 960),
            skin: str = SKIN_PRISM,
        ) -> None:
            controller = WorkbenchController(config_path, probe_ocr_devices=False)
            controller.setTheme(theme)
            controller.setSkin(skin)
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

        def render_dohna_home_popup(output_path: Path) -> None:
            controller = WorkbenchController(config_path, probe_ocr_devices=False)
            controller.setTheme(THEME_DARK)
            controller.setSkin(SKIN_DOHNA)
            controller.setReducedMotion(True)
            controller.setPage("HOME")
            host = QmlWorkbenchHost(controller, application=app)
            window = host.window
            if window is None:
                raise RuntimeError("QML 工作台没有创建窗口")
            window.resize(1280, 820)
            host.show()
            app.processEvents()
            def find_quick_item(item: QQuickItem, object_name: str):
                if item.objectName() == object_name:
                    return item
                for child in item.childItems():
                    match = find_quick_item(child, object_name)
                    if match is not None:
                        return match
                return None

            def find_quick_items(item: QQuickItem, object_name: str):
                matches = []
                if item.objectName() == object_name:
                    matches.append(item)
                for child in item.childItems():
                    matches.extend(find_quick_items(child, object_name))
                return matches

            selector = find_quick_item(window.contentItem(), "homeSkinSelector")
            if selector is None:
                raise RuntimeError("无法找到 Dohna 皮肤下拉框")
            selector_point = selector.mapToScene(
                QPointF(selector.width() / 2, selector.height() / 2)
            ).toPoint()
            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                selector_point,
            )
            popup_ready = False
            for _ in range(100):
                app.processEvents()
                popup_ready = any(
                    item.isVisible()
                    for item in find_quick_items(
                        window.contentItem(), "prismComboBoxDohnaDelegateCut"
                    )
                )
                if popup_ready:
                    break
                QTest.qWait(20)
            if not popup_ready:
                raise RuntimeError("Dohna 皮肤下拉框未展开")
            if not window.grabWindow().save(str(output_path)):
                raise RuntimeError(f"无法保存下拉框预览：{output_path}")
            window.close()
            host.shutdown()
            app.processEvents()

        def render_motion(output_path: Path) -> None:
            controller = WorkbenchController(config_path, probe_ocr_devices=False)
            controller.setTheme(THEME_DARK)
            controller.setSkin(SKIN_DOHNA)
            controller.setReducedMotion(False)
            controller.setPage("HOME")
            host = QmlWorkbenchHost(controller, application=app)
            window = host.window
            if window is None:
                raise RuntimeError("QML 工作台没有创建窗口")
            window.resize(1280, 820)
            host.show()
            app.processEvents()

            frames = []

            def find_quick_item(item: QQuickItem, object_name: str):
                if item.objectName() == object_name:
                    return item
                for child in item.childItems():
                    match = find_quick_item(child, object_name)
                    if match is not None:
                        return match
                return None

            def capture_frame() -> None:
                app.processEvents()
                image = window.grabWindow()
                if image.isNull():
                    raise RuntimeError("无法抓取 QML 动效帧")
                # Keep the native QImage until the interaction is complete;
                # PNG/Pillow conversion in the sampling loop shifts the real
                # animation timestamps and collapses the short middle states.
                frames.append(image.copy())

            def capture_for(duration_ms: int, *, interval_ms: int = 40) -> None:
                deadline = monotonic() + duration_ms / 1000
                while monotonic() < deadline or not frames:
                    capture_frame()
                    wait_until = monotonic() + interval_ms / 1000
                    while True:
                        remaining = int((wait_until - monotonic()) * 1000)
                        if remaining <= 0:
                            break
                        QTest.qWait(min(remaining, 8))

            # Let HOME settle, then drive the same navigation hit target a
            # user sees: hover, press, release, and observe the short page pop.
            capture_for(480)
            navigation_button = find_quick_item(window.contentItem(), "navigationButton1")
            if navigation_button is None:
                raise RuntimeError("无法找到 Dohna 导航命中区")
            navigation_point = navigation_button.mapToScene(
                QPointF(navigation_button.width() / 2, navigation_button.height() / 2)
            ).toPoint()
            QTest.mouseMove(window, navigation_point)
            capture_for(120)
            QTest.mousePress(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                navigation_point,
            )
            capture_for(80)
            QTest.mouseRelease(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                navigation_point,
            )
            capture_for(520)
            capture_for(360)

            def to_pillow(image) -> Image.Image:
                buffer = QBuffer()
                buffer.open(QIODevice.WriteOnly)
                image.save(buffer, "PNG")
                return Image.open(BytesIO(bytes(buffer.data()))).convert("RGB")

            pillow_frames = [to_pillow(image) for image in frames]

            pillow_frames[0].save(
                output_path,
                save_all=True,
                append_images=pillow_frames[1:],
                duration=40,
                loop=0,
                disposal=2,
                optimize=False,
            )
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
        render(
            THEME_DARK,
            "HOME",
            dohna_home_output_path,
            skin=SKIN_DOHNA,
        )
        render(
            THEME_DARK,
            "HOME",
            dohna_home_minimum_output_path,
            size=(980, 700),
            skin=SKIN_DOHNA,
        )
        render_dohna_home_popup(dohna_home_popup_output_path)
        render(
            THEME_DARK,
            "CAPTURE",
            dohna_capture_output_path,
            skin=SKIN_DOHNA,
        )
        render(
            THEME_DARK,
            "SETTINGS",
            dohna_minimum_output_path,
            size=(980, 700),
            skin=SKIN_DOHNA,
        )
        if args.motion:
            render_motion(dohna_motion_output_path)
    print(dark_output_path)
    print(light_output_path)
    print(minimum_output_path)
    print(dohna_home_output_path)
    print(dohna_home_minimum_output_path)
    print(dohna_home_popup_output_path)
    print(dohna_capture_output_path)
    print(dohna_minimum_output_path)
    if args.motion:
        print(dohna_motion_output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

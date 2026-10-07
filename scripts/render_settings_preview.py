"""Render native, isolated SettingsPage evidence without starting translation."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from argparse import ArgumentParser
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtGui import QFontDatabase
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from game_screen_translator.config import load_config
from game_screen_translator.gui.qml_workbench import QmlWorkbenchHost
from game_screen_translator.gui.theme import SKIN_DOHNA, SKIN_PRISM, THEME_DARK
from game_screen_translator.gui.workbench_controller import WorkbenchController
from game_screen_translator.profiles import create_game_profile


def _find_item(root: QQuickItem, name: str) -> QQuickItem:
    pending = [root]
    while pending:
        item = pending.pop()
        if item.objectName() == name:
            return item
        pending.extend(item.childItems())
    raise RuntimeError(f"Missing QML item: {name}")


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("output/settings-layout"))
    parser.add_argument("--log-file", type=Path, help="Read-only copy of an existing real end-of-run log")
    parser.add_argument("--empty", action="store_true", help="Capture the unavailable statistics state")
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    for name in ("bahnschrift.ttf", "segoeui.ttf", "consola.ttf", "msyh.ttc", "msyhbd.ttc"):
        font = Path("C:/Windows/Fonts") / name
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))

    with tempfile.TemporaryDirectory(prefix="settings-preview-", dir=destination) as temporary:
        config_path = Path(temporary) / "config.toml"
        config_path.write_text(
            '[translation]\nprovider = "openai_compatible"\n'
            'base_url = "http://127.0.0.1:1234/v1"\nmodel = "hy-mt1.5-7b"\n',
            encoding="utf-8",
        )
        create_game_profile(
            config_path, load_config(config_path), "preview", display_name="高级设置预览"
        )
        log_path = Path(temporary) / "output" / "live.log"
        log_path.parent.mkdir()
        if args.log_file and not args.empty:
            shutil.copy2(args.log_file.resolve(), log_path)
        else:
            log_path.write_text("[预览夹具] 尚未结束一次运行，无延迟统计。\n", encoding="utf-8")
        for skin in (SKIN_PRISM, SKIN_DOHNA):
            for dynamic_roi in (True, False):
                for size in ((1280, 820), (980, 700)):
                    controller = WorkbenchController(config_path, probe_ocr_devices=False)
                    controller.setSkin(skin)
                    controller.setTheme(THEME_DARK)
                    controller.setReducedMotion(True)
                    controller.setDynamicRoiEnabled(dynamic_roi)
                    controller.setPage("SETTINGS")
                    host = QmlWorkbenchHost(controller, application=app)
                    try:
                        window = host.window
                        if window is None:
                            raise RuntimeError("QML workbench did not create a window")
                        window.resize(max(size[0], window.minimumWidth()), size[1])
                        host.show()
                        QTest.qWait(120)
                        app.processEvents()
                        form = _find_item(window.contentItem(), "settingsFormScroll")
                        debug = _find_item(window.contentItem(), "settingsDebugToggle")
                        log = _find_item(window.contentItem(), "settingsLatencyScroll")
                        prefix = (
                            f"settings-{skin}-{window.width()}x{window.height()}-"
                            f"{'dynamic' if dynamic_roi else 'full'}"
                        )

                        def capture(suffix: str) -> None:
                            window.update()
                            QTest.qWait(60)
                            frame = window.grabWindow()
                            path = destination / f"{prefix}-{suffix}.png"
                            if frame.isNull() or not frame.save(str(path)):
                                raise RuntimeError(f"Cannot save QML screenshot: {path}")
                            print(json.dumps({
                                "screenshot": str(path),
                                "platform": app.platformName(),
                                "log_viewport_height": log.height(),
                                "left_scroll_y": form.property("contentY"),
                                "source": (
                                    f"actual QML host, isolated Profile, copied existing log: {args.log_file.resolve()}"
                                    if args.log_file and not args.empty
                                    else "actual QML host with isolated unavailable-statistics fixture"
                                ),
                            }, ensure_ascii=False))

                        capture("initial")
                        debug.forceActiveFocus()
                        app.processEvents()
                        QTest.qWait(20)
                        app.processEvents()
                        origin = debug.mapToItem(form, QPointF(0, 0))
                        if origin.y() < -0.5 or origin.y() + debug.height() > form.height() + 0.5:
                            raise RuntimeError("Debug toggle cannot be reached in the left viewport")
                        form.setProperty(
                            "contentY", max(0, form.property("contentHeight") - form.height())
                        )
                        app.processEvents()
                        capture("output")
                        flickable = log.property("contentItem")
                        if not args.empty:
                            for group in ("settingsTranslationLatency", "settingsLatencySummary"):
                                text = _find_item(window.contentItem(), group)
                                point = text.mapToItem(flickable.property("contentItem"), QPointF(0, 0))
                                maximum = max(0, flickable.property("contentHeight") - flickable.height())
                                flickable.setProperty("contentY", min(maximum, max(0, point.y() - 24)))
                                app.processEvents()
                                capture("translation" if "Translation" in group else "summary")
                    finally:
                        host.shutdown()
                        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

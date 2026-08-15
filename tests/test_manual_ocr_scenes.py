from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QRawFont
from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENE_SCRIPT = PROJECT_ROOT / "tests" / "manual" / "animated_ocr_scenes.py"


def _load_scene_module():
    spec = importlib.util.spec_from_file_location("manual_ocr_scenes", SCENE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCENE_MODULE = _load_scene_module()


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_manual_scene_script_is_standalone() -> None:
    source = SCENE_SCRIPT.read_text(encoding="utf-8")

    assert "game_screen_translator" not in source
    assert len(SCENE_MODULE.SCENES) == 5
    assert tuple(scene.key for scene in SCENE_MODULE.SCENES) == (
        "typewriter",
        "fade",
        "vertical-menu",
        "horizontal-menu",
        "changing-background",
    )


def test_typewriter_and_fade_timelines_repeat() -> None:
    assert SCENE_MODULE._typewriter_lines(0.0) == ("", "", "")
    assert SCENE_MODULE._typewriter_lines(0.2)[0].startswith("門")
    assert SCENE_MODULE._fade_opacity(0.0) == 0.0
    assert SCENE_MODULE._fade_opacity(1.8) == pytest.approx(1.0)
    assert SCENE_MODULE._motion_progress(0.2) == 0.0
    assert SCENE_MODULE._motion_progress(3.2) == 1.0


def test_scene_font_can_render_japanese() -> None:
    _app()
    window = SCENE_MODULE.AnimatedOcrSceneWindow(fps=30)
    window.set_elapsed_for_test(0.0)

    raw_font = QRawFont.fromFont(window._font(40))

    assert raw_font.isValid()
    assert raw_font.supportsCharacter("門")
    window.close()


@pytest.mark.parametrize("scene_index", range(5))
def test_each_manual_scene_renders_offscreen(scene_index: int) -> None:
    _app()
    window = SCENE_MODULE.AnimatedOcrSceneWindow(scene_index=scene_index, fps=30)
    window.set_elapsed_for_test(2.15)

    image = window.render_scene_to_image(scene_index, 2.15)

    assert not image.isNull()
    assert image.width() == 800
    assert image.height() == 450
    assert image.pixelColor(400, 225) != image.pixelColor(0, 0)
    window.close()

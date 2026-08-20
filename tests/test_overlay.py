import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from game_screen_translator.branding import PRODUCT_NAME
from game_screen_translator.live.tracker import TrackedText
from game_screen_translator.overlay.window import OverlayStyle, TranslationOverlay


def _is_nearly_white(image: QImage, x: int, y: int) -> bool:
    color = image.pixelColor(x, y)
    return min(color.red(), color.green(), color.blue()) >= 245


def test_overlay_renders_only_translated_track_region() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = TranslationOverlay(
        geometry=(0, 0, 320, 120),
        style=OverlayStyle(blur_radius=4),
    )
    assert overlay.windowTitle() == f"{PRODUCT_NAME} Overlay"
    frame = np.full((120, 320, 3), (30, 40, 50), dtype=np.uint8)
    track = TrackedText(
        "track",
        1,
        "原文",
        0.99,
        (40, 30, 280, 90),
        0,
        1,
        2,
        True,
        "覆盖译文",
    )
    overlay.set_scene(frame, (track,))
    target = QImage(320, 120, QImage.Format.Format_ARGB32)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    overlay.render(painter, QPoint())
    painter.end()

    assert target.pixelColor(5, 5).alpha() == 0
    assert target.pixelColor(50, 40).alpha() > 0
    assert target.pixelColor(50, 40).getRgb() == (30, 40, 50, 255)
    assert any(
        target.pixelColor(x, y).red() >= 245
        and target.pixelColor(x, y).green() >= 245
        and target.pixelColor(x, y).blue() >= 245
        for y in range(30, 90)
        for x in range(40, 280)
    )
    app.processEvents()


def test_overlay_uses_restored_translation_font_scale() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = TranslationOverlay(
        geometry=(0, 0, 320, 120),
        style=OverlayStyle(),
    )

    font = overlay._fit_font("短译文", QRect(0, 0, 240, 60))

    assert 32 <= font.pixelSize() <= 38
    app.processEvents()


def test_long_translation_is_clipped_to_its_own_text_region() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = TranslationOverlay(
        geometry=(0, 0, 160, 100),
        style=OverlayStyle(blur_radius=0),
    )
    track = TrackedText(
        "tiny-track",
        1,
        "原文",
        0.99,
        (50, 40, 70, 52),
        0,
        1,
        1,
        True,
        "这是一段远远放不进原文字框的译文",
    )
    overlay.set_scene(None, (track,))
    target = QImage(160, 100, QImage.Format.Format_ARGB32)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    overlay.render(painter, QPoint())
    painter.end()

    assert any(
        target.pixelColor(x, y).alpha() > 0
        for y in range(40, 52)
        for x in range(50, 70)
    )
    assert all(
        target.pixelColor(x, y).alpha() == 0
        for y in range(100)
        for x in range(160)
        if not (50 <= x < 70 and 40 <= y < 52)
    )
    app.processEvents()


def test_later_blur_region_does_not_cover_earlier_translation() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = TranslationOverlay(
        geometry=(0, 0, 320, 120),
        style=OverlayStyle(blur_radius=0),
    )
    frame = np.full((120, 320, 3), (30, 40, 50), dtype=np.uint8)
    first = TrackedText(
        "first-line",
        1,
        "first",
        0.99,
        (40, 20, 280, 60),
        0,
        1,
        1,
        True,
        "第一行译文",
    )

    overlay.set_scene(frame, (first,))
    first_only = QImage(320, 120, QImage.Format.Format_ARGB32)
    first_only.fill(Qt.GlobalColor.transparent)
    painter = QPainter(first_only)
    overlay.render(painter, QPoint())
    painter.end()

    white_pixels = [
        (x, y)
        for y in range(first.bounds[1], first.bounds[3])
        for x in range(first.bounds[0], first.bounds[2])
        if _is_nearly_white(first_only, x, y)
    ]
    assert white_pixels
    overlap_y = max(y for _, y in white_pixels)
    protected_pixels = [(x, y) for x, y in white_pixels if y == overlap_y]
    second = TrackedText(
        "second-line",
        1,
        "second",
        0.99,
        (40, overlap_y + 1, 280, min(110, overlap_y + 31)),
        0,
        1,
        1,
        True,
        "第二行译文",
    )

    overlay.set_scene(frame, (first, second))
    together = QImage(320, 120, QImage.Format.Format_ARGB32)
    together.fill(Qt.GlobalColor.transparent)
    painter = QPainter(together)
    overlay.render(painter, QPoint())
    painter.end()

    assert all(_is_nearly_white(together, x, y) for x, y in protected_pixels)
    app.processEvents()

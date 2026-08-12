import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from game_screen_translator.live.tracker import TrackedText
from game_screen_translator.overlay.window import OverlayStyle, TranslationOverlay


def test_overlay_renders_only_translated_track_region() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = TranslationOverlay(
        geometry=(0, 0, 320, 120),
        style=OverlayStyle(blur_radius=4),
    )
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

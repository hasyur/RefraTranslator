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


def test_overlay_renders_retained_translation_while_replacement_is_pending() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = TranslationOverlay(
        geometry=(0, 0, 320, 120),
        style=OverlayStyle(blur_radius=0),
    )
    frame = np.full((120, 320, 3), (30, 40, 50), dtype=np.uint8)
    track = TrackedText(
        track_id="track",
        revision=2,
        text="新原文",
        confidence=0.99,
        bounds=(40, 30, 280, 90),
        first_seen=0,
        last_seen=1,
        observations=2,
        stable_emitted=True,
        translated_text=None,
        retained_translation="旧译文",
    )

    overlay.set_scene(frame, (track,))
    target = QImage(320, 120, QImage.Format.Format_ARGB32)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    overlay.render(painter, QPoint())
    painter.end()

    assert overlay._tracks == (track,)
    assert any(
        target.pixelColor(x, y).red() >= 245
        and target.pixelColor(x, y).green() >= 245
        and target.pixelColor(x, y).blue() >= 245
        for y in range(30, 90)
        for x in range(40, 280)
    )
    overlay.close()
    app.processEvents()


def test_live_overlay_caches_sampled_blur_pixmap() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = TranslationOverlay(
        geometry=(0, 0, 320, 120),
        style=OverlayStyle(blur_radius=8),
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

    cached = overlay._background_pixmaps[("track", 1)]
    assert cached.source_bounds == (36, 26, 284, 94)
    assert cached.pixmap.width() == 42
    assert cached.pixmap.height() == 12
    overlay.close()
    app.processEvents()


def test_overlay_can_darken_the_blurred_game_frame() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = TranslationOverlay(
        geometry=(0, 0, 320, 120),
        style=OverlayStyle(blur_radius=0, overlay_opacity=0.55),
    )
    frame = np.full((120, 320, 3), (100, 120, 140), dtype=np.uint8)
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

    color = target.pixelColor(38, 28)
    assert color.alpha() == 255
    assert color.red() < 100
    assert color.green() < 120
    assert color.blue() < 140
    app.processEvents()


def test_overlay_keeps_clean_background_when_capture_returns_dimmed() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = TranslationOverlay(
        geometry=(0, 0, 320, 120),
        style=OverlayStyle(blur_radius=8, overlay_opacity=0.0),
    )
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
    clean_frame = np.full((120, 320, 3), (100, 120, 140), dtype=np.uint8)
    overlay.set_scene(clean_frame, (track,))

    # Model the next Desktop Duplication frame after Windows has excluded the
    # overlay window from capture: the painted area can be dimmed without being
    # pure black, so a black-pixel threshold is insufficient.
    excluded_frame = np.full_like(clean_frame, (45, 54, 63))
    jittered_track = TrackedText(
        "track",
        1,
        "原文",
        0.99,
        (42, 31, 282, 91),
        0,
        2,
        3,
        True,
        "覆盖译文",
    )
    overlay.set_scene(excluded_frame, (jittered_track,))
    target = QImage(320, 120, QImage.Format.Format_ARGB32)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    overlay.render(painter, QPoint())
    painter.end()

    color = target.pixelColor(38, 28)
    assert color.getRgb() == (100, 120, 140, 255)
    overlay.close()
    app.processEvents()


def test_overlay_caches_latest_background_before_translation_appears() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = TranslationOverlay(
        geometry=(0, 0, 320, 120),
        style=OverlayStyle(blur_radius=0, overlay_opacity=0.0),
    )
    untranslated_track = TrackedText(
        "track",
        1,
        "原文",
        0.99,
        (40, 30, 280, 90),
        0,
        1,
        2,
        True,
        None,
    )
    overlay.set_scene(
        np.full((120, 320, 3), (100, 120, 140), dtype=np.uint8),
        (untranslated_track,),
    )
    refreshed_untranslated_track = TrackedText(
        "track",
        1,
        "原文",
        0.99,
        (40, 30, 280, 90),
        0,
        2,
        3,
        True,
        None,
    )
    overlay.set_scene(
        np.full((120, 320, 3), (180, 160, 140), dtype=np.uint8),
        (refreshed_untranslated_track,),
    )
    translated_track = TrackedText(
        "track",
        1,
        "原文",
        0.99,
        (40, 30, 280, 90),
        0,
        2,
        3,
        True,
        "覆盖译文",
    )
    overlay.set_scene(
        np.full((120, 320, 3), (45, 54, 63), dtype=np.uint8),
        (translated_track,),
    )
    target = QImage(320, 120, QImage.Format.Format_ARGB32)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    overlay.render(painter, QPoint())
    painter.end()

    assert target.pixelColor(38, 28).getRgb() == (180, 160, 140, 255)
    overlay.close()
    app.processEvents()


def test_untranslated_background_refreshes_only_after_a_new_ocr_observation(
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    overlay = TranslationOverlay(
        geometry=(0, 0, 320, 120),
        style=OverlayStyle(blur_radius=8, overlay_opacity=0.0),
    )
    calls: list[tuple[int, int, int, int]] = []
    original = overlay._background_patch

    def record_background_patch(bounds):
        calls.append(bounds)
        return original(bounds)

    monkeypatch.setattr(overlay, "_background_patch", record_background_patch)
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
        None,
    )
    first_frame = np.full((120, 320, 3), (100, 120, 140), dtype=np.uint8)
    overlay.set_scene(first_frame, (track,))
    overlay.set_scene(np.full_like(first_frame, 180), (track,))
    assert len(calls) == 1

    observed_again = TrackedText(
        "track",
        1,
        "原文",
        0.99,
        (40, 30, 280, 90),
        0,
        2,
        3,
        True,
        None,
    )
    overlay.set_scene(np.full_like(first_frame, 180), (observed_again,))
    assert len(calls) == 2
    overlay.close()
    app.processEvents()


def test_overlay_refreshes_background_when_a_track_moves_to_new_coordinates() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = TranslationOverlay(
        geometry=(0, 0, 320, 120),
        style=OverlayStyle(blur_radius=0, overlay_opacity=0.0),
    )
    untranslated = TrackedText(
        "track",
        1,
        "原文",
        0.99,
        (30, 30, 170, 90),
        0,
        1,
        2,
        True,
        None,
    )
    red_frame = np.full((120, 320, 3), (200, 40, 30), dtype=np.uint8)
    overlay.set_scene(red_frame, (untranslated,))
    translated = TrackedText(
        "track",
        1,
        "原文",
        0.99,
        (30, 30, 170, 90),
        0,
        1,
        2,
        True,
        "旧位置译文",
    )
    overlay.set_scene(red_frame, (translated,))

    moved = TrackedText(
        "track",
        1,
        "原文",
        0.99,
        (140, 30, 280, 90),
        0,
        2,
        3,
        True,
        "新位置译文",
    )
    blue_frame = np.full((120, 320, 3), (30, 50, 210), dtype=np.uint8)
    overlay.set_scene(blue_frame, (moved,))

    cached = overlay._background_pixmaps[("track", 1)]
    assert cached.source_bounds == (136, 26, 284, 94)
    target = QImage(320, 120, QImage.Format.Format_ARGB32)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    overlay.render(painter, QPoint())
    painter.end()
    assert target.pixelColor(138, 28).getRgb() == (30, 50, 210, 255)
    overlay.close()
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


def test_multiline_source_uses_source_line_height_as_font_cap() -> None:
    app = QApplication.instance() or QApplication([])
    overlay = TranslationOverlay(
        geometry=(0, 0, 900, 300),
        style=OverlayStyle(),
    )

    font = overlay._fit_font(
        "这是前两句的短译文。",
        QRect(0, 0, 800, 150),
        source_text="一行目の文章\n二行目の文章\n三行目の文章",
    )

    assert 26 <= font.pixelSize() <= 34
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

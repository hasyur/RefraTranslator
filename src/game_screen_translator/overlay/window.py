from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from game_screen_translator.background import render_background_patch
from game_screen_translator.branding import PRODUCT_NAME
from game_screen_translator.live.tracker import TrackedText


WDA_EXCLUDEFROMCAPTURE = 0x00000011
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

# Sampling every sixth source pixel reduces live Gaussian-blur work to about
# 1/36 of the original pixel count. QPainter scales the cached patch smoothly
# over the native OCR bounds during composition.
_LIVE_BLUR_SAMPLE_STEP = 6


@dataclass(frozen=True, slots=True)
class OverlayStyle:
    blur_radius: float = 8.0
    overlay_opacity: float = 0.0
    font_path: str = ""

    def __post_init__(self) -> None:
        if self.blur_radius < 0:
            raise ValueError("blur_radius 不能为负数")
        if not 0 <= self.overlay_opacity <= 1:
            raise ValueError("overlay_opacity 必须在 0 到 1 之间")


@dataclass(frozen=True, slots=True)
class _CachedBackground:
    source_bounds: tuple[int, int, int, int]
    track_last_seen: float
    pixmap: object


def _load_qt():
    try:
        from PySide6.QtCore import QPoint, QRect, Qt
        from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QImage, QPainter, QPen, QPixmap
        from PySide6.QtWidgets import QApplication, QWidget
    except ImportError as exc:
        raise RuntimeError("尚未安装 GUI 依赖。请运行：.\\bootstrap.ps1 -WithGui") from exc
    return {
        "QPoint": QPoint,
        "QRect": QRect,
        "Qt": Qt,
        "QColor": QColor,
        "QFont": QFont,
        "QFontDatabase": QFontDatabase,
        "QFontMetrics": QFontMetrics,
        "QImage": QImage,
        "QPainter": QPainter,
        "QPen": QPen,
        "QPixmap": QPixmap,
        "QApplication": QApplication,
        "QWidget": QWidget,
    }


QT = _load_qt()
Qt = QT["Qt"]
QWidget = QT["QWidget"]


def _default_font_path(configured: str) -> str:
    if configured and Path(configured).is_file():
        return str(Path(configured))
    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf"):
        candidate = windows_dir / "Fonts" / name
        if candidate.is_file():
            return str(candidate)
    return ""


def exclude_window_from_capture(hwnd: int, *, click_through: bool = False) -> bool:
    if os.name != "nt":
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_window_long = user32.GetWindowLongPtrW
    get_window_long.argtypes = (wintypes.HWND, ctypes.c_int)
    get_window_long.restype = ctypes.c_ssize_t
    set_window_long = user32.SetWindowLongPtrW
    set_window_long.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
    set_window_long.restype = ctypes.c_ssize_t
    if click_through:
        style = get_window_long(hwnd, GWL_EXSTYLE)
        set_window_long(
            hwnd,
            GWL_EXSTYLE,
            style | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
        )
    set_affinity = user32.SetWindowDisplayAffinity
    set_affinity.argtypes = (wintypes.HWND, wintypes.DWORD)
    set_affinity.restype = wintypes.BOOL
    return bool(set_affinity(wintypes.HWND(hwnd), WDA_EXCLUDEFROMCAPTURE))


class TranslationOverlay(QWidget):
    def __init__(
        self,
        *,
        geometry: tuple[int, int, int, int],
        style: OverlayStyle,
        debug_border: bool = False,
    ) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle(f"{PRODUCT_NAME} Overlay")
        self.setGeometry(*geometry)
        self._style = style
        self._debug_border = debug_border
        self._tracks: tuple[TrackedText, ...] = ()
        self._frame: np.ndarray | None = None
        self._background_pixmaps: dict[tuple[str, int], _CachedBackground] = {}
        self._font_family = self._install_font(style.font_path)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt callback name
        super().showEvent(event)
        if os.name == "nt":
            self._apply_windows_capture_exclusion()

    def set_scene(self, frame: np.ndarray | None, tracks: Sequence[TrackedText]) -> None:
        previous_tracks = self._tracks
        previous_backgrounds = self._background_pixmaps
        visible_tracks = tuple(tracks)
        self._tracks = tuple(
            track for track in visible_tracks if track.display_translation
        )
        active_backgrounds = {
            self._background_key(track) for track in visible_tracks
        }
        self._background_pixmaps = {
            key: pixmap
            for key, pixmap in previous_backgrounds.items()
            if key in active_backgrounds
        }
        # DXcam already returns an owned copy. Keep a reference instead of
        # copying a full 4K frame on every overlay refresh.
        self._frame = None if frame is None else np.asarray(frame)
        # Untranslated tracks continuously collect a clean background. Once a
        # translation is visible, freeze its last clean crop: capture APIs can
        # return the excluded overlay as pure black, dimmed pixels, or an empty
        # surface, none of which can be distinguished safely by color alone.
        for track in visible_tracks:
            key = self._background_key(track)
            source_bounds = self._source_bounds(track.bounds)
            cached = self._background_pixmaps.get(key)
            cached_bounds_reusable = (
                cached is not None
                and self._background_bounds_reusable(
                    cached.source_bounds,
                    source_bounds,
                )
            )
            if (
                cached_bounds_reusable
                and (
                    track.display_translation
                    or cached.track_last_seen == track.last_seen
                )
            ):
                continue
            if cached is not None and not cached_bounds_reusable:
                self._background_pixmaps.pop(key, None)

            overlapping_previous = tuple(
                previous
                for previous in previous_tracks
                if self._bounds_overlap(
                    source_bounds,
                    self._source_bounds(previous.bounds),
                )
            )
            if overlapping_previous:
                prior = next(
                    (
                        background
                        for (track_id, _), background in previous_backgrounds.items()
                        if track_id == track.track_id
                        and self._background_bounds_reusable(
                            background.source_bounds,
                            source_bounds,
                        )
                    ),
                    None,
                )
                if prior is not None:
                    self._background_pixmaps[key] = prior
                    continue
                # A genuinely moved track must not stretch its old color patch
                # over the new coordinates. Prefer a fresh aligned sample even
                # though capture exclusion can make that sample imperfect.
                if not any(
                    previous.track_id == track.track_id
                    for previous in overlapping_previous
                ):
                    continue

            patch = self._background_patch(source_bounds)
            if patch is None:
                continue
            self._background_pixmaps[key] = _CachedBackground(
                source_bounds,
                track.last_seen,
                self._pixmap_from_patch(patch),
            )
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt callback name
        if not self._tracks:
            return
        painter = QT["QPainter"](self)
        painter.setRenderHint(QT["QPainter"].RenderHint.Antialiasing, True)
        painter.setRenderHint(QT["QPainter"].RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QT["QPainter"].RenderHint.SmoothPixmapTransform, True)
        layouts = []
        for track in self._tracks:
            rect = self._track_layout(track)
            if rect is not None:
                layouts.append((track, rect))
        # Paint every source-text blur before drawing any translation. Otherwise
        # a later line's padded blur can erase glyphs already drawn for a nearby
        # line.
        for track, rect in layouts:
            self._paint_track_background(painter, track, rect)
        if self._debug_border:
            for _, rect in layouts:
                self._paint_track_border(painter, rect)
        for track, rect in layouts:
            self._paint_track_text(painter, track, rect)
        painter.end()

    def _track_layout(self, track: TrackedText):
        frame_height, frame_width = (
            self._frame.shape[:2] if self._frame is not None else (self.height(), self.width())
        )
        scale_x = self.width() / max(1, frame_width)
        scale_y = self.height() / max(1, frame_height)
        source_left, source_top, source_right, source_bottom = track.bounds
        padding = 4
        rect = QT["QRect"](
            max(0, round((source_left - padding) * scale_x)),
            max(0, round((source_top - padding) * scale_y)),
            max(1, round((source_right - source_left + padding * 2) * scale_x)),
            max(1, round((source_bottom - source_top + padding * 2) * scale_y)),
        ).intersected(self.rect())
        if rect.isEmpty():
            return None
        return rect

    def _paint_track_background(self, painter, track, rect) -> None:
        key = self._background_key(track)
        background = self._background_pixmaps.get(key)
        if background is not None:
            painter.save()
            painter.setClipRect(rect)
            painter.drawPixmap(rect, background.pixmap)
            painter.restore()

    @staticmethod
    def _background_key(track: TrackedText) -> tuple[str, int]:
        return track.track_id, track.revision

    @staticmethod
    def _source_bounds(bounds):
        left, top, right, bottom = bounds
        padding = 4
        return (
            left - padding,
            top - padding,
            right + padding,
            bottom + padding,
        )

    @staticmethod
    def _bounds_overlap(first, second) -> bool:
        return not (
            first[2] <= second[0]
            or second[2] <= first[0]
            or first[3] <= second[1]
            or second[3] <= first[1]
        )

    @staticmethod
    def _background_bounds_reusable(first, second) -> bool:
        first_width = max(1, first[2] - first[0])
        first_height = max(1, first[3] - first[1])
        second_width = max(1, second[2] - second[0])
        second_height = max(1, second[3] - second[1])
        short_side = min(
            first_width,
            first_height,
            second_width,
            second_height,
        )
        tolerance = max(2, min(6, round(short_side * 0.1)))
        return all(
            abs(first_edge - second_edge) <= tolerance
            for first_edge, second_edge in zip(first, second, strict=True)
        )

    @staticmethod
    def _paint_track_border(painter, rect) -> None:
        painter.setPen(QT["QPen"](QT["QColor"](0, 220, 255, 220), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

    def _paint_track_text(self, painter, track: TrackedText, rect) -> None:
        # Keep glyphs inside the original OCR bounds. The surrounding four
        # pixels belong to the blur only; letting text use them makes adjacent
        # subtitle lines paint over one another.
        text_rect = rect.adjusted(4, 4, -4, -4)
        if text_rect.isEmpty():
            return
        translation = track.display_translation or ""
        font = self._fit_font(
            translation,
            text_rect,
            source_text=track.text,
        )
        painter.setFont(font)
        metrics = QT["QFontMetrics"](font)
        lines = self._wrap(translation, metrics, text_rect.width())
        line_height = metrics.lineSpacing()
        y = text_rect.top() + max(0, (text_rect.height() - line_height * len(lines)) // 2)
        painter.save()
        painter.setClipRect(text_rect)
        for line in lines:
            line_width = metrics.horizontalAdvance(line)
            x = text_rect.left() + max(0, (text_rect.width() - line_width) // 2)
            baseline = y + metrics.ascent()
            self._draw_text_line(painter, x, baseline, line)
            y += line_height
        painter.restore()

    @staticmethod
    def _draw_text_line(painter, x: int, baseline: int, text: str) -> None:
        # Native text drawing keeps Windows font hinting. A one-pixel outline
        # remains legible on light and dark frames without closing small glyphs.
        painter.setPen(QT["QColor"](0, 0, 0, 230))
        for dx, dy in (
            (-1, -1),
            (0, -1),
            (1, -1),
            (-1, 0),
            (1, 0),
            (-1, 1),
            (0, 1),
            (1, 1),
        ):
            painter.drawText(QT["QPoint"](x + dx, baseline + dy), text)
        painter.setPen(QT["QColor"](255, 255, 255, 255))
        painter.drawText(QT["QPoint"](x, baseline), text)

    def _background_patch(self, source_bounds):
        frame = self._frame
        if frame is None:
            return None
        rendered = render_background_patch(
            frame,
            source_bounds,
            blur_radius=self._style.blur_radius,
            overlay_opacity=self._style.overlay_opacity,
            sample_step=(
                _LIVE_BLUR_SAMPLE_STEP if self._style.blur_radius > 0 else 1
            ),
        )
        return None if rendered is None else rendered[1]

    @staticmethod
    def _pixmap_from_patch(patch: np.ndarray):
        height, width, channels = patch.shape
        image = QT["QImage"](
            patch.data,
            width,
            height,
            channels * width,
            QT["QImage"].Format.Format_RGB888,
        ).copy()
        return QT["QPixmap"].fromImage(image)

    def _fit_font(self, text: str, rect, *, source_text: str = ""):
        upper = max(12, min(48, int(rect.height() * 0.64)))
        source_lines = tuple(line for line in source_text.splitlines() if line.strip())
        if len(source_lines) > 1 and rect.width() >= rect.height():
            source_line_upper = int(rect.height() / len(source_lines) * 0.64)
            upper = max(12, min(upper, source_line_upper))
        for size in range(upper, 9, -1):
            font = self._make_font(size)
            metrics = QT["QFontMetrics"](font)
            lines = self._wrap(text, metrics, rect.width())
            if metrics.lineSpacing() * len(lines) <= rect.height():
                return font
        return self._make_font(10)

    def _make_font(self, pixel_size: int):
        font = QT["QFont"](self._font_family)
        font.setPixelSize(pixel_size)
        font.setWeight(QT["QFont"].Weight.DemiBold)
        font.setHintingPreference(QT["QFont"].HintingPreference.PreferFullHinting)
        return font

    @staticmethod
    def _wrap(text: str, metrics, width: int) -> list[str]:
        lines: list[str] = []
        current = ""
        for character in text:
            if character == "\n":
                lines.append(current or " ")
                current = ""
                continue
            candidate = current + character
            if current and metrics.horizontalAdvance(candidate) > width:
                lines.append(current)
                current = character
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines or [" "]

    @staticmethod
    def _install_font(configured_path: str) -> str:
        path = _default_font_path(configured_path)
        if not path:
            return "Microsoft YaHei UI"
        font_id = QT["QFontDatabase"].addApplicationFont(path)
        families = QT["QFontDatabase"].applicationFontFamilies(font_id)
        return families[0] if families else "Microsoft YaHei UI"

    def _apply_windows_capture_exclusion(self) -> None:
        if not exclude_window_from_capture(int(self.winId()), click_through=True):
            print("警告：Windows 未能将翻译覆盖层排除出屏幕采集。")

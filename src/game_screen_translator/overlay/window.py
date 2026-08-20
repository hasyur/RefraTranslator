from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageFilter

from game_screen_translator.branding import PRODUCT_NAME
from game_screen_translator.live.tracker import TrackedText


WDA_EXCLUDEFROMCAPTURE = 0x00000011
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000


@dataclass(frozen=True, slots=True)
class OverlayStyle:
    blur_radius: float = 8.0
    font_path: str = ""


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
        self._font_family = self._install_font(style.font_path)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt callback name
        super().showEvent(event)
        if os.name == "nt":
            self._apply_windows_capture_exclusion()

    def set_scene(self, frame: np.ndarray | None, tracks: Sequence[TrackedText]) -> None:
        self._tracks = tuple(track for track in tracks if track.translated_text)
        # DXcam already returns an owned copy. Keep a reference instead of
        # copying a full 4K frame on every overlay refresh.
        self._frame = None if frame is None or not self._tracks else np.asarray(frame)
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
            layout = self._track_layout(track)
            if layout is not None:
                rect, source_bounds = layout
                layouts.append((track, rect, source_bounds))
        # Paint every source-text blur before drawing any translation. Otherwise
        # a later line's padded blur can erase glyphs already drawn for a nearby
        # line.
        for _, rect, source_bounds in layouts:
            self._paint_track_background(painter, rect, source_bounds)
        if self._debug_border:
            for _, rect, _ in layouts:
                self._paint_track_border(painter, rect)
        for track, rect, _ in layouts:
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
        source_bounds = (
            source_left - padding,
            source_top - padding,
            source_right + padding,
            source_bottom + padding,
        )
        return rect, source_bounds

    def _paint_track_background(self, painter, rect, source_bounds) -> None:
        if self._frame is not None:
            pixmap = self._frame_pixmap(source_bounds)
            if pixmap is not None:
                painter.save()
                painter.setClipRect(rect)
                painter.drawPixmap(rect, pixmap)
                painter.restore()

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
        font = self._fit_font(track.translated_text or "", text_rect)
        painter.setFont(font)
        metrics = QT["QFontMetrics"](font)
        lines = self._wrap(track.translated_text or "", metrics, text_rect.width())
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

    def _frame_pixmap(self, source_bounds):
        frame = self._frame
        if frame is None or frame.ndim != 3 or frame.shape[2] < 3:
            return None
        left, top, right, bottom = source_bounds
        top = max(0, min(top, frame.shape[0] - 1))
        bottom = max(top + 1, min(bottom, frame.shape[0]))
        left = max(0, min(left, frame.shape[1] - 1))
        right = max(left + 1, min(right, frame.shape[1]))
        crop = np.ascontiguousarray(frame[top:bottom, left:right, :3])
        if self._style.blur_radius > 0:
            crop = np.asarray(
                Image.fromarray(crop).filter(ImageFilter.GaussianBlur(self._style.blur_radius))
            )
            crop = np.ascontiguousarray(crop)
        height, width, channels = crop.shape
        image = QT["QImage"](
            crop.data,
            width,
            height,
            channels * width,
            QT["QImage"].Format.Format_RGB888,
        ).copy()
        return QT["QPixmap"].fromImage(image)

    def _fit_font(self, text: str, rect):
        upper = max(12, min(48, int(rect.height() * 0.64)))
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

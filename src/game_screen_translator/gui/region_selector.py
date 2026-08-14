from __future__ import annotations

from typing import TYPE_CHECKING

from game_screen_translator.branding import PRODUCT_NAME

try:
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPen
    from PySide6.QtWidgets import QDialog
except ImportError as exc:  # pragma: no cover - exercised only without GUI extra
    raise RuntimeError("尚未安装 GUI 依赖。请运行：.\\bootstrap.ps1 -WithGui") from exc

if TYPE_CHECKING:
    from PySide6.QtGui import QScreen


def scale_selection_region(
    selection: tuple[int, int, int, int],
    logical_size: tuple[int, int],
    capture_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    """Convert a Qt logical-pixel selection into capture-device pixels."""

    logical_width, logical_height = logical_size
    capture_width, capture_height = capture_size
    if min(logical_width, logical_height, capture_width, capture_height) <= 0:
        raise ValueError("屏幕逻辑尺寸和采集尺寸必须大于 0")
    left, top, width, height = selection
    if min(left, top, width, height) < 0 or width == 0 or height == 0:
        raise ValueError("框选区域必须是屏幕内的非空矩形")

    logical_left = min(left, logical_width)
    logical_top = min(top, logical_height)
    logical_right = min(left + width, logical_width)
    logical_bottom = min(top + height, logical_height)
    if logical_right <= logical_left or logical_bottom <= logical_top:
        raise ValueError("框选区域位于屏幕范围之外")

    physical_left = round(logical_left * capture_width / logical_width)
    physical_top = round(logical_top * capture_height / logical_height)
    physical_right = round(logical_right * capture_width / logical_width)
    physical_bottom = round(logical_bottom * capture_height / logical_height)
    return (
        physical_left,
        physical_top,
        max(1, physical_right - physical_left),
        max(1, physical_bottom - physical_top),
    )


class RegionSelector(QDialog):
    """Full-screen screenshot overlay that returns a monitor-relative region."""

    def __init__(self, screen: QScreen) -> None:
        super().__init__(None)
        self._screen = screen
        self._background = screen.grabWindow(0)
        self._origin: QPoint | None = None
        self._selection = QRect()
        self.selected_region: tuple[int, int, int, int] | None = None
        self.setWindowTitle(f"{PRODUCT_NAME} - 框选游戏字幕区域")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setGeometry(screen.geometry())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self.reject()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._origin = event.position().toPoint()
        self._selection = QRect(self._origin, self._origin)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._origin is None:
            return
        self._selection = QRect(self._origin, event.position().toPoint()).normalized()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        self._selection = QRect(self._origin, event.position().toPoint()).normalized()
        self._origin = None
        if self._selection.width() < 8 or self._selection.height() < 8:
            self._selection = QRect()
            self.update()
            return

        capture_width = self._background.width()
        capture_height = self._background.height()
        if self._background.isNull():
            ratio = max(1.0, float(self._screen.devicePixelRatio()))
            capture_width = round(self.width() * ratio)
            capture_height = round(self.height() * ratio)
        self.selected_region = scale_selection_region(
            (
                self._selection.x(),
                self._selection.y(),
                self._selection.width(),
                self._selection.height(),
            ),
            (self.width(), self.height()),
            (capture_width, capture_height),
        )
        self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        if not self._background.isNull():
            painter.drawPixmap(self.rect(), self._background)
        else:
            painter.fillRect(self.rect(), QColor(30, 30, 30))
        painter.fillRect(self.rect(), QColor(0, 0, 0, 115))

        if not self._selection.isNull():
            painter.fillRect(self._selection, QColor(255, 255, 255, 45))
            painter.setPen(QPen(QColor(0, 220, 255), 3))
            painter.drawRect(self._selection)

            label = f"{self._selection.width()} × {self._selection.height()}"
            label_rect = QRect(
                self._selection.left(),
                max(48, self._selection.top()) - 34,
                220,
                30,
            )
            painter.fillRect(label_rect, QColor(0, 0, 0, 190))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(
                label_rect.adjusted(8, 0, -8, 0),
                Qt.AlignmentFlag.AlignVCenter,
                label,
            )

        instruction = QRect(24, 24, min(620, max(200, self.width() - 48)), 58)
        painter.fillRect(instruction, QColor(0, 0, 0, 205))
        painter.setPen(QColor(255, 255, 255))
        font = QFont(painter.font())
        font.setPointSize(max(11, font.pointSize()))
        painter.setFont(font)
        painter.drawText(
            instruction.adjusted(16, 0, -16, 0),
            Qt.AlignmentFlag.AlignVCenter,
            "按住左键拖出字幕区域 · 右键或 Esc 取消",
        )

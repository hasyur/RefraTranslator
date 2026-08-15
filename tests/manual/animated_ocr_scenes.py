"""Standalone looping scenes for manually exercising screen OCR and translation.

This module deliberately imports no RefraTranslator package code.  It only draws a
predictable game-like window that any screen translator can capture.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
    from PySide6.QtGui import (
        QColor,
        QFont,
        QFontDatabase,
        QFontMetricsF,
        QImage,
        QLinearGradient,
        QPainter,
        QPainterPath,
        QPen,
        QRadialGradient,
    )
    from PySide6.QtWidgets import QApplication, QWidget
except ImportError as exc:  # pragma: no cover - exercised by a manual launcher
    raise SystemExit(
        "PySide6 is required. Run bootstrap.ps1 -WithGui in the project root."
    ) from exc


CANVAS_WIDTH = 1600
CANVAS_HEIGHT = 900
DEFAULT_AUTO_CYCLE_SECONDS = 14.0


@dataclass(frozen=True, slots=True)
class SceneDefinition:
    key: str
    title: str
    purpose: str


SCENES = (
    SceneDefinition(
        "typewriter",
        "多行打字机",
        "三行日文逐字出现，完成后短暂停留并清空重来",
    ),
    SceneDefinition(
        "fade",
        "整行淡入淡出",
        "同一行文字从近乎不可见逐渐变清晰，再淡出",
    ),
    SceneDefinition(
        "vertical-menu",
        "菜单上下滚动",
        "菜单列表在停顿后上下平滑滚动，文字会进出裁剪边界",
    ),
    SceneDefinition(
        "horizontal-menu",
        "菜单左右滚动",
        "卡片式菜单在停顿后左右滚动，模拟横向选择界面",
    ),
    SceneDefinition(
        "changing-background",
        "文字背景变化",
        "字幕保持不变，背后的光斑、色带和字幕底色持续变化",
    ),
)


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def _motion_progress(
    elapsed_s: float,
    *,
    hold_s: float = 1.0,
    travel_s: float = 2.0,
) -> float:
    """Return a deterministic 0 -> 1 -> 0 motion with pauses at both ends."""

    period = 2.0 * (hold_s + travel_s)
    phase = elapsed_s % period
    if phase < hold_s:
        return 0.0
    phase -= hold_s
    if phase < travel_s:
        return _smoothstep(phase / travel_s)
    phase -= travel_s
    if phase < hold_s:
        return 1.0
    phase -= hold_s
    return 1.0 - _smoothstep(phase / travel_s)


def _typewriter_lines(elapsed_s: float) -> tuple[str, ...]:
    lines = (
        "門は真夜中に開く。",
        "川岸に沿って進み、",
        "失われた鍵を探せ。",
    )
    character_s = 0.105
    between_lines_s = 0.34
    hold_complete_s = 1.8
    blank_s = 0.75
    writing_s = sum(len(line) * character_s + between_lines_s for line in lines)
    phase = elapsed_s % (writing_s + hold_complete_s + blank_s)
    if phase >= writing_s + hold_complete_s:
        return tuple("" for _ in lines)

    result: list[str] = []
    cursor_s = 0.0
    for line in lines:
        line_duration_s = len(line) * character_s
        if phase <= cursor_s:
            result.append("")
        elif phase >= cursor_s + line_duration_s:
            result.append(line)
        else:
            visible = max(1, math.ceil((phase - cursor_s) / character_s))
            result.append(line[:visible])
        cursor_s += line_duration_s + between_lines_s
    return tuple(result)


def _fade_opacity(elapsed_s: float) -> float:
    blank_before_s = 0.55
    fade_s = 1.25
    hold_s = 1.55
    blank_after_s = 0.65
    period = blank_before_s + fade_s + hold_s + fade_s + blank_after_s
    phase = elapsed_s % period
    if phase < blank_before_s:
        return 0.0
    phase -= blank_before_s
    if phase < fade_s:
        return _smoothstep(phase / fade_s)
    phase -= fade_s
    if phase < hold_s:
        return 1.0
    phase -= hold_s
    if phase < fade_s:
        return 1.0 - _smoothstep(phase / fade_s)
    return 0.0


class AnimatedOcrSceneWindow(QWidget):
    def __init__(
        self,
        *,
        scene_index: int = 0,
        fps: int = 60,
        auto_cycle_seconds: float = 0.0,
    ) -> None:
        super().__init__()
        self._scene_index = scene_index
        self._elapsed_s = 0.0
        self._last_tick = time.perf_counter()
        self._paused = False
        self._help_visible = False
        self._auto_cycle_seconds = max(0.0, auto_cycle_seconds)
        self._last_nonzero_auto_cycle = (
            self._auto_cycle_seconds or DEFAULT_AUTO_CYCLE_SECONDS
        )
        self._font_family = self._choose_font_family()
        self._font_cache: dict[tuple[int, int], QFont] = {}

        self.setMinimumSize(800, 450)
        self.resize(1280, 720)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(max(4, round(1000 / fps)))
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._update_title()

    @staticmethod
    def _choose_font_family() -> str:
        # Qt's offscreen backend and some stripped-down Windows installations do
        # not enumerate DirectWrite fonts until a concrete font file is loaded.
        # Registering a known CJK font also prevents silent tofu-box rendering.
        font_root = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for filename in (
            "YuGothR.ttc",
            "meiryo.ttc",
            "msgothic.ttc",
            "msyh.ttc",
        ):
            path = font_root / filename
            if not path.is_file():
                continue
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id < 0:
                continue
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]

        available = set(QFontDatabase.families())
        for family in (
            "Yu Gothic UI",
            "Yu Gothic",
            "Meiryo UI",
            "Meiryo",
            "Noto Sans CJK JP",
        ):
            if family in available:
                return family
        return QApplication.font().family()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt virtual method
        return QSize(1280, 720)

    @property
    def scene(self) -> SceneDefinition:
        return SCENES[self._scene_index]

    def set_scene(self, scene_index: int) -> None:
        self._scene_index = scene_index % len(SCENES)
        self._elapsed_s = 0.0
        self._last_tick = time.perf_counter()
        self._update_title()
        self.update()

    def set_elapsed_for_test(self, elapsed_s: float) -> None:
        """Set a deterministic timestamp for offscreen smoke tests."""

        self._timer.stop()
        self._elapsed_s = max(0.0, elapsed_s)
        self.update()

    def _tick(self) -> None:
        now = time.perf_counter()
        delta_s = min(0.25, max(0.0, now - self._last_tick))
        self._last_tick = now
        if self._paused:
            return
        self._elapsed_s += delta_s
        if (
            self._auto_cycle_seconds > 0.0
            and self._elapsed_s >= self._auto_cycle_seconds
        ):
            self.set_scene(self._scene_index + 1)
            return
        self.update()

    def _update_title(self) -> None:
        state = " · 已暂停" if self._paused else ""
        auto = " · 自动轮换" if self._auto_cycle_seconds > 0.0 else ""
        self.setWindowTitle(
            f"动态字幕靶场 · {self._scene_index + 1} {self.scene.title}{state}{auto}"
        )

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt virtual method
        key = event.key()
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_5:
            self.set_scene(key - Qt.Key.Key_1)
            return
        if key == Qt.Key.Key_Space:
            self._paused = not self._paused
            self._last_tick = time.perf_counter()
            self._update_title()
            return
        if key == Qt.Key.Key_R:
            self.set_scene(self._scene_index)
            return
        if key == Qt.Key.Key_A:
            if self._auto_cycle_seconds > 0.0:
                self._last_nonzero_auto_cycle = self._auto_cycle_seconds
                self._auto_cycle_seconds = 0.0
            else:
                self._auto_cycle_seconds = self._last_nonzero_auto_cycle
                self._elapsed_s = 0.0
            self._update_title()
            return
        if key in (Qt.Key.Key_F1, Qt.Key.Key_H):
            self._help_visible = not self._help_visible
            self.update()
            return
        if key == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            return
        if key == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt virtual method
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(self.rect(), QColor(5, 7, 12))

        scale = min(self.width() / CANVAS_WIDTH, self.height() / CANVAS_HEIGHT)
        draw_width = CANVAS_WIDTH * scale
        draw_height = CANVAS_HEIGHT * scale
        painter.translate(
            (self.width() - draw_width) / 2.0,
            (self.height() - draw_height) / 2.0,
        )
        painter.scale(scale, scale)
        painter.setClipRect(QRectF(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT))
        self._paint_scene(painter, self._scene_index, self._elapsed_s)
        if self._help_visible:
            self._paint_help(painter)
        painter.end()

    def render_scene_to_image(
        self,
        scene_index: int,
        elapsed_s: float,
        *,
        width: int = 800,
        height: int = 450,
    ) -> QImage:
        """Render a frame without showing the window; used only by smoke tests."""

        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(QColor(5, 7, 12))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        scale = min(width / CANVAS_WIDTH, height / CANVAS_HEIGHT)
        painter.translate(
            (width - CANVAS_WIDTH * scale) / 2.0,
            (height - CANVAS_HEIGHT * scale) / 2.0,
        )
        painter.scale(scale, scale)
        self._paint_scene(painter, scene_index % len(SCENES), elapsed_s)
        painter.end()
        return image

    def _paint_scene(
        self,
        painter: QPainter,
        scene_index: int,
        elapsed_s: float,
    ) -> None:
        if scene_index == 4:
            self._paint_changing_background(painter, elapsed_s)
            return

        self._paint_static_background(painter)
        if scene_index == 0:
            self._paint_typewriter(painter, elapsed_s)
        elif scene_index == 1:
            self._paint_fade(painter, elapsed_s)
        elif scene_index == 2:
            self._paint_vertical_menu(painter, elapsed_s)
        elif scene_index == 3:
            self._paint_horizontal_menu(painter, elapsed_s)

    @staticmethod
    def _paint_static_background(painter: QPainter) -> None:
        gradient = QLinearGradient(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
        gradient.setColorAt(0.0, QColor(14, 24, 42))
        gradient.setColorAt(0.55, QColor(24, 31, 48))
        gradient.setColorAt(1.0, QColor(9, 13, 24))
        painter.fillRect(QRectF(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT), gradient)

        painter.setPen(QPen(QColor(80, 106, 142, 42), 2))
        for x in range(80, CANVAS_WIDTH, 120):
            painter.drawLine(x, 0, x - 240, CANVAS_HEIGHT)
        painter.setBrush(QColor(49, 74, 103, 55))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(1080, 80, 360, 360))
        painter.drawEllipse(QRectF(80, 210, 260, 260))

    def _font(self, size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
        key = (size, int(weight))
        font = self._font_cache.get(key)
        if font is None:
            font = QFont(self._font_family)
            font.setPixelSize(size)
            font.setWeight(weight)
            font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
            self._font_cache[key] = font
        return QFont(font)

    def _draw_text(
        self,
        painter: QPainter,
        x: float,
        baseline_y: float,
        text: str,
        *,
        size: int,
        color: QColor = QColor(244, 246, 250),
        weight: QFont.Weight = QFont.Weight.Medium,
        outline: bool = True,
    ) -> None:
        if not text:
            return
        font = self._font(size, weight)
        path = QPainterPath()
        path.addText(QPointF(x, baseline_y), font, text)
        if outline:
            painter.setPen(
                QPen(
                    QColor(3, 5, 9, 225),
                    max(2.0, size * 0.085),
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPath(path)
        painter.fillPath(path, color)

    def _draw_dialogue_panel(
        self,
        painter: QPainter,
        *,
        fill: QColor = QColor(7, 10, 17, 218),
    ) -> None:
        panel = QRectF(105, 555, 1390, 290)
        painter.setPen(QPen(QColor(132, 158, 190, 145), 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(panel, 24, 24)

    def _paint_typewriter(self, painter: QPainter, elapsed_s: float) -> None:
        self._draw_dialogue_panel(painter)
        self._draw_text(
            painter,
            170,
            620,
            "旅人",
            size=30,
            color=QColor(142, 204, 255),
            outline=False,
        )
        for text, baseline_y in zip(
            _typewriter_lines(elapsed_s),
            (690, 756, 822),
            strict=True,
        ):
            self._draw_text(painter, 170, baseline_y, text, size=43)

    def _paint_fade(self, painter: QPainter, elapsed_s: float) -> None:
        self._draw_dialogue_panel(painter)
        self._draw_text(
            painter,
            170,
            640,
            "システム",
            size=30,
            color=QColor(142, 204, 255),
            outline=False,
        )
        painter.save()
        painter.setOpacity(_fade_opacity(elapsed_s))
        self._draw_text(
            painter,
            170,
            750,
            "新しい任務が追加されました。",
            size=48,
        )
        painter.restore()

    def _paint_vertical_menu(self, painter: QPainter, elapsed_s: float) -> None:
        panel = QRectF(350, 90, 900, 720)
        painter.setPen(QPen(QColor(128, 157, 194, 145), 2))
        painter.setBrush(QColor(10, 14, 23, 232))
        painter.drawRoundedRect(panel, 24, 24)
        self._draw_text(
            painter,
            430,
            165,
            "メニュー",
            size=40,
            color=QColor(142, 204, 255),
        )

        items = (
            "ゲームを続ける",
            "ニューゲーム",
            "ロード",
            "装備を変更する",
            "設定",
            "操作方法",
            "クレジット",
            "タイトルへ戻る",
        )
        offset_y = -235.0 * _motion_progress(elapsed_s)
        content = QRectF(390, 190, 820, 560)
        painter.save()
        painter.setClipRect(content)
        for index, text in enumerate(items):
            top = 218 + index * 86 + offset_y
            item_rect = QRectF(415, top - 51, 770, 69)
            if index == 3:
                painter.setPen(QPen(QColor(238, 208, 128, 190), 2))
                painter.setBrush(QColor(91, 72, 35, 145))
                painter.drawRoundedRect(item_rect, 10, 10)
            self._draw_text(
                painter,
                455,
                top,
                text,
                size=35,
                color=(
                    QColor(252, 226, 156)
                    if index == 3
                    else QColor(226, 233, 243)
                ),
            )
        painter.restore()

    def _paint_horizontal_menu(self, painter: QPainter, elapsed_s: float) -> None:
        panel = QRectF(65, 105, 1470, 675)
        painter.setPen(QPen(QColor(128, 157, 194, 145), 2))
        painter.setBrush(QColor(10, 14, 23, 226))
        painter.drawRoundedRect(panel, 24, 24)
        self._draw_text(
            painter,
            130,
            180,
            "装備を選択",
            size=40,
            color=QColor(142, 204, 255),
        )

        cards = (
            ("鉄の剣", "扱いやすい標準装備"),
            ("狩人の弓", "遠距離から攻撃できる"),
            ("旅人の杖", "魔力を少し高める"),
            ("守護者の盾", "受ける衝撃を軽減する"),
            ("古代の短剣", "素早い連続攻撃が可能"),
        )
        offset_x = -665.0 * _motion_progress(elapsed_s, hold_s=1.1, travel_s=2.4)
        painter.save()
        painter.setClipRect(QRectF(95, 210, 1410, 510))
        for index, (name, detail) in enumerate(cards):
            left = 130 + index * 365 + offset_x
            card = QRectF(left, 245, 325, 410)
            painter.setPen(
                QPen(
                    QColor(241, 207, 121, 210)
                    if index == 2
                    else QColor(91, 119, 153, 180),
                    3 if index == 2 else 2,
                )
            )
            painter.setBrush(
                QColor(58, 50, 35, 225)
                if index == 2
                else QColor(25, 33, 47, 225)
            )
            painter.drawRoundedRect(card, 18, 18)

            hue = (index * 47 + 195) % 360
            glow = QRadialGradient(left + 162, 390, 125)
            glow.setColorAt(0.0, QColor.fromHsv(hue, 105, 210, 190))
            glow.setColorAt(1.0, QColor.fromHsv(hue, 135, 90, 20))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QRectF(left + 47, 275, 230, 230))
            self._draw_text(
                painter,
                left + 28,
                555,
                name,
                size=31,
                color=QColor(248, 232, 184) if index == 2 else QColor(238, 242, 248),
            )
            self._draw_text(
                painter,
                left + 28,
                608,
                detail,
                size=22,
                color=QColor(190, 204, 222),
                weight=QFont.Weight.Normal,
                outline=False,
            )
        painter.restore()

    def _paint_changing_background(self, painter: QPainter, elapsed_s: float) -> None:
        gradient = QLinearGradient(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
        pulse = (math.sin(elapsed_s * 0.9) + 1.0) * 0.5
        gradient.setColorAt(0.0, QColor(10, round(30 + 25 * pulse), 61))
        gradient.setColorAt(0.55, QColor(round(25 + 28 * pulse), 30, 72))
        gradient.setColorAt(1.0, QColor(8, 13, round(30 + 25 * (1.0 - pulse))))
        painter.fillRect(QRectF(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT), gradient)

        painter.setPen(Qt.PenStyle.NoPen)
        for index, (radius, speed, color) in enumerate(
            (
                (250, 0.46, QColor(70, 168, 255, 125)),
                (330, 0.31, QColor(187, 83, 220, 105)),
                (190, 0.62, QColor(73, 224, 185, 95)),
            )
        ):
            center_x = 800 + math.sin(elapsed_s * speed + index * 2.1) * 620
            center_y = 390 + math.cos(elapsed_s * speed * 0.83 + index) * 260
            glow = QRadialGradient(center_x, center_y, radius)
            glow.setColorAt(0.0, color)
            edge = QColor(color)
            edge.setAlpha(0)
            glow.setColorAt(1.0, edge)
            painter.setBrush(glow)
            painter.drawEllipse(
                QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)
            )

        for band in range(5):
            center_y = 185 + band * 120 + math.sin(elapsed_s * 1.1 + band) * 34
            path = QPainterPath(QPointF(-100, center_y))
            for x in range(-100, CANVAS_WIDTH + 201, 200):
                y = center_y + math.sin(x / 210 + elapsed_s * 1.35 + band) * 28
                path.lineTo(x, y)
            painter.setPen(QPen(QColor(145, 191, 244, 35 + band * 5), 13))
            painter.drawPath(path)

        panel_color = QColor(
            round(10 + 32 * pulse),
            round(14 + 12 * (1.0 - pulse)),
            round(27 + 30 * pulse),
            round(155 + 65 * (1.0 - pulse)),
        )
        self._draw_dialogue_panel(painter, fill=panel_color)
        self._draw_text(
            painter,
            170,
            645,
            "案内人",
            size=30,
            color=QColor(142, 204, 255),
            outline=False,
        )
        self._draw_text(
            painter,
            170,
            755,
            "この扉は固く閉ざされている。",
            size=48,
        )

    def _paint_help(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor(158, 183, 215, 190), 2))
        painter.setBrush(QColor(5, 8, 14, 242))
        painter.drawRoundedRect(QRectF(245, 165, 1110, 570), 24, 24)
        self._draw_text(
            painter,
            315,
            245,
            "动态字幕靶场",
            size=42,
            color=QColor(142, 204, 255),
            outline=False,
        )
        help_lines = (
            "数字一至五：切换测试场景",
            "空格：暂停或继续    R：从头播放",
            "A：自动轮换场景    F11：全屏",
            "F1 或 H：隐藏帮助    Esc：退出全屏或关闭",
            "帮助层默认隐藏，测试时请保持隐藏。",
        )
        for index, line in enumerate(help_lines):
            self._draw_text(
                painter,
                315,
                335 + index * 72,
                line,
                size=31,
                color=QColor(225, 232, 242),
                outline=False,
            )


def _scene_index(value: str) -> int:
    normalized = value.strip().lower()
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(SCENES):
            return index
    for index, scene in enumerate(SCENES):
        if normalized == scene.key:
            return index
    choices = ", ".join(
        f"{index + 1}/{scene.key}" for index, scene in enumerate(SCENES)
    )
    raise argparse.ArgumentTypeError(f"unknown scene {value!r}; choose {choices}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch standalone looping scenes for OCR/translation testing."
    )
    parser.add_argument(
        "--scene",
        type=_scene_index,
        default=0,
        metavar="NAME",
        help="initial scene number or key (default: 1/typewriter)",
    )
    parser.add_argument("--fullscreen", action="store_true", help="start fullscreen")
    parser.add_argument(
        "--auto-cycle",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="switch to the next scene after this many seconds; 0 disables it",
    )
    parser.add_argument(
        "--fps",
        type=int,
        choices=range(10, 121),
        default=60,
        metavar="10-120",
        help="drawing refresh rate (default: 60)",
    )
    parser.add_argument(
        "--list-scenes",
        action="store_true",
        help="print the fixed scene list and exit",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="close automatically after this many seconds; 0 keeps looping",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.auto_cycle < 0.0:
        raise SystemExit("--auto-cycle must be zero or greater")
    if args.duration < 0.0:
        raise SystemExit("--duration must be zero or greater")
    if args.list_scenes:
        for index, scene in enumerate(SCENES, start=1):
            print(f"{index}. {scene.key}: {scene.title} - {scene.purpose}")
        return 0

    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = AnimatedOcrSceneWindow(
        scene_index=args.scene,
        fps=args.fps,
        auto_cycle_seconds=args.auto_cycle,
    )
    if args.fullscreen:
        window.showFullScreen()
    else:
        window.show()
    if args.duration > 0.0:
        QTimer.singleShot(round(args.duration * 1000), window.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

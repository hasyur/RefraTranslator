import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from game_screen_translator.branding import PRODUCT_NAME
from game_screen_translator.live import runtime as live_runtime
from game_screen_translator.live.runtime import LiveControlWindow


def test_live_control_is_a_prism_top_hud_and_is_mouse_transparent(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    stopped: list[bool] = []
    exclusion_calls: list[tuple[int, bool]] = []

    monkeypatch.setattr(
        live_runtime,
        "exclude_window_from_capture",
        lambda hwnd, *, click_through=False: (
            exclusion_calls.append((hwnd, click_through)) or True
        ),
    )
    window = LiveControlWindow(
        lambda: stopped.append(True),
        profile_name="测试游戏",
        theme="dark",
    )

    assert window.windowTitle() == PRODUCT_NAME
    assert (window.width(), window.height()) == (1080, 20)
    assert window._hud_font_pixels == 16
    assert window.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert window.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert not window.findChildren(QPushButton)
    assert not hasattr(window, "_pause_button")
    captions = {"LIVE", "PROFILE", "COVERED", "LATENCY / RECENT · PEAK"}
    assert captions.isdisjoint(label.text() for label in window.findChildren(QLabel))

    window.set_coverage_count(42)
    window.set_latency(
        "最近  OCR 118ms · LLM 2.50s · 总延迟 640ms    "
        "峰值  OCR 230ms · LLM 3.10s · 总延迟 1.20s"
    )
    window.set_status("实时翻译运行中")
    assert window._profile.text() == "测试游戏"
    assert window._coverage.text() == "42 条"
    assert window._recent_ocr_title.text() == "OCR"
    assert window._recent_llm_title.text() == "LLM"
    assert window._recent_total_title.text() == "总延迟"
    assert window._recent_ocr.text() == "118ms"
    assert window._recent_llm.text() == "2.50s"
    assert window._recent_total.text() == "640ms"
    assert window._peak_ocr_title.text() == "OCR"
    assert window._peak_llm_title.text() == "LLM"
    assert window._peak_total_title.text() == "总延迟"
    assert window._peak_ocr.text() == "230ms"
    assert window._peak_llm.text() == "3.10s"
    assert window._peak_total.text() == "1.20s"
    assert window._status_indicator.text() == "●"
    assert window._status.text() == ""

    window.set_status("实时翻译已停止")
    assert window._status.text() == "停止"

    window.show()
    app.processEvents()
    assert exclusion_calls and exclusion_calls[-1][1] is True

    window.close()
    app.processEvents()
    assert stopped == [True]


def test_live_control_uses_black_surface_and_supplied_four_color_palette() -> None:
    app = QApplication.instance() or QApplication([])
    dark = LiveControlWindow(lambda: None, theme="dark")
    light = LiveControlWindow(lambda: None, theme="light")

    for window in (dark, light):
        style = window.styleSheet()
        assert "background-color: #000000" in style
        assert "#4c8dff" in style
        assert "#3b82f6" in style
        assert "#22d3ee" in style
        assert "#f472b6" in style
        assert "border: none" in style
        assert "border-radius" not in style
        assert "font-size: 16px" in style
        assert "QFrame#hudLatencyMetricLast { border-right: none; }" in style

    dark.close()
    light.close()
    app.processEvents()


class _ScreenGeometryStub:
    def __init__(self, geometry: QRect) -> None:
        self._geometry = geometry
        self.geometryChanged = _SignalStub()
        self.logicalDotsPerInchChanged = _SignalStub()

    def availableGeometry(self) -> QRect:  # noqa: N802
        return self._geometry

    def geometry(self) -> QRect:
        return self._geometry


class _SignalStub:
    def __init__(self) -> None:
        self.slots = []

    def connect(self, slot) -> None:
        self.slots.append(slot)

    def disconnect(self, slot) -> None:
        self.slots.remove(slot)

    def emit(self, *args) -> None:
        for slot in tuple(self.slots):
            slot(*args)


@pytest.mark.parametrize(
    ("screen_width", "expected_width", "expected_height", "expected_font"),
    (
        (800, 800, 15, 12),
        (1366, 896, 17, 13),
        (1920, 1080, 20, 16),
        (2560, 1242, 23, 18),
    ),
)
def test_live_control_scales_fixed_hud_columns_to_screen_width(
    screen_width: int,
    expected_width: int,
    expected_height: int,
    expected_font: int,
) -> None:
    app = QApplication.instance() or QApplication([])
    window = LiveControlWindow(lambda: None)

    screen_left = -screen_width
    screen_top = -200
    screen = _ScreenGeometryStub(QRect(screen_left, screen_top, screen_width, 600))
    live_runtime._position_live_control(window, screen)
    expected_left = screen_left + (screen_width - expected_width) // 2
    assert (window.x(), window.y(), window.width(), window.height()) == (
        expected_left,
        screen_top,
        expected_width,
        expected_height,
    )
    assert window._hud_font_pixels == expected_font
    assert window._hud_column_widths[-1] >= 1

    window.close()
    app.processEvents()


def test_live_control_text_updates_keep_fixed_columns_and_elide_profile() -> None:
    app = QApplication.instance() or QApplication([])
    window = LiveControlWindow(lambda: None, profile_name="短名")
    screen = _ScreenGeometryStub(QRect(-1920, -100, 1920, 600))
    live_runtime._position_live_control(window, screen)
    window.show()
    app.processEvents()
    assert window.layout() is not None
    window.layout().activate()
    assert window._surface.layout() is not None
    window._surface.layout().activate()

    column_geometry = tuple(
        (column.x(), column.width(), column.geometry().right())
        for column in window._hud_columns
    )
    profile_geometry = window._profile.geometry()

    def metric_geometry():
        return tuple(
            (
                field,
                cell.x() + window._latency_titles[field].x(),
                window._latency_titles[field].width(),
                cell.x() + window._latency_fields[field].x(),
                cell.x() + window._latency_fields[field].geometry().right(),
            )
            for field, cell in window._latency_cells.items()
        )

    initial_metric_geometry = metric_geometry()
    column_xs = tuple(geometry[0] for geometry in column_geometry)
    assert column_xs[0] == 0
    assert column_xs == tuple(sorted(column_xs))
    assert column_xs[-1] > column_xs[0]
    assert all(width > 0 and right >= left for left, width, right in column_geometry)
    assert any(title_x > 0 for _, title_x, _, _, _ in initial_metric_geometry)
    assert all(value_right > value_x for _, _, _, value_x, value_right in initial_metric_geometry)

    long_profile = "这是一个非常长的 Profile 名称用于验证固定列省略行为"
    window.set_status("OCR 暂时失败，稍后重试")
    window.set_profile_name(long_profile)
    window.set_coverage_count(1234)
    window.set_latency(
        "最近  OCR 118ms · LLM 2.50s · 总延迟 640ms    "
        "峰值  OCR 230ms · LLM 3.10s · 总延迟 1.20s"
    )

    app.processEvents()
    assert window.layout() is not None
    window.layout().activate()
    assert window._surface.layout() is not None
    window._surface.layout().activate()
    assert tuple(
        (column.x(), column.width(), column.geometry().right())
        for column in window._hud_columns
    ) == column_geometry
    assert window._profile.geometry() == profile_geometry
    assert metric_geometry() == initial_metric_geometry
    assert window._profile.text() != long_profile
    assert window._profile.text().endswith("…")
    assert window._profile.toolTip() == long_profile
    assert window._status.text() == "异常"
    assert window._coverage.alignment() & Qt.AlignmentFlag.AlignRight
    window.set_latency(
        "最近  OCR 118ms · LLM 缓存 · 总延迟 1.20s    "
        "峰值  OCR 3.10s · LLM — · 总延迟 4.20s"
    )
    app.processEvents()
    assert window.layout() is not None
    window.layout().activate()
    assert window._surface.layout() is not None
    window._surface.layout().activate()
    assert metric_geometry() == initial_metric_geometry
    initial_right_edges = {
        field: value_right
        for field, _, _, _, value_right in initial_metric_geometry
    }
    for field, value in (
        ("recent_ocr", "118ms"),
        ("recent_llm", "缓存"),
        ("recent_total", "1.20s"),
        ("peak_ocr", "3.10s"),
        ("peak_llm", "—"),
        ("peak_total", "4.20s"),
    ):
        assert window._latency_fields[field].text() == value
        field_geometry = next(
            geometry for geometry in metric_geometry() if geometry[0] == field
        )
        assert field_geometry[4] == initial_right_edges[field]

    window.set_profile_name("短名")
    assert window._profile.text() == "短名"
    assert window._profile.toolTip() == "短名"
    window.close()
    app.processEvents()


def test_live_control_repositions_on_selected_screen_geometry_and_dpi_signals() -> None:
    app = QApplication.instance() or QApplication([])
    window = LiveControlWindow(lambda: None)
    screen = _ScreenGeometryStub(QRect(-1920, -100, 1920, 600))
    live_runtime._position_live_control(window, screen)
    window.show()
    app.processEvents()
    assert window.layout() is not None
    window.layout().activate()
    assert window._surface.layout() is not None
    window._surface.layout().activate()
    assert len(screen.geometryChanged.slots) == 1
    assert len(screen.logicalDotsPerInchChanged.slots) == 1
    initial = (window.x(), window.y(), window.width(), window.height())

    screen._geometry = QRect(-1920, -100, 800, 600)
    window.set_profile_name("文本更新不应触发布局")
    app.processEvents()
    assert (window.x(), window.y(), window.width(), window.height()) == initial
    screen.geometryChanged.emit(screen._geometry)
    app.processEvents()
    assert (window.x(), window.y(), window.width(), window.height()) == (
        -1920,
        -100,
        800,
        15,
    )

    screen._geometry = QRect(-1366, -80, 1366, 600)
    screen.logicalDotsPerInchChanged.emit(144.0)
    app.processEvents()
    assert (window.x(), window.y(), window.width(), window.height()) == (
        -1366 + (1366 - 896) // 2,
        -80,
        896,
        17,
    )
    window.close()
    app.processEvents()


def test_live_theme_is_read_from_project_gui_preferences_each_session(
    monkeypatch,
    tmp_path,
) -> None:
    app = QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    config_path.write_text("[translation]\n", encoding="utf-8")
    (tmp_path / ".gui-settings.toml").write_text(
        "[appearance]\ntheme = \"light\"\n",
        encoding="utf-8",
    )
    calls: list[tuple[str, str]] = []

    def resolve_theme(preference, _app):
        calls.append((preference, "called"))
        return "light"

    monkeypatch.setattr(live_runtime, "effective_theme", resolve_theme)
    assert live_runtime._read_live_theme(config_path, app) == "light"
    assert calls == [("light", "called")]

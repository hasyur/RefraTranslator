import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
    assert window.size().width() == 1800
    assert window.size().height() == 25
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
    assert "最近" in window._latency.text()
    assert "峰值" in window._latency.text()
    assert window._status_indicator.text() == "●"
    assert window._status.text() == ""

    window.set_status("实时翻译已停止")
    assert window._status.text() == "实时翻译已停止"

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
        assert "font-size: 20px" in style

    dark.close()
    light.close()
    app.processEvents()


class _ScreenGeometryStub:
    def __init__(self, geometry: QRect) -> None:
        self._geometry = geometry

    def availableGeometry(self) -> QRect:  # noqa: N802
        return self._geometry

    def geometry(self) -> QRect:
        return self._geometry


def test_live_control_centers_on_negative_screen_geometry_and_touches_top_edge() -> None:
    app = QApplication.instance() or QApplication([])
    window = LiveControlWindow(lambda: None)

    wide_screen = _ScreenGeometryStub(QRect(-1920, -120, 1920, 1080))
    live_runtime._position_live_control(window, wide_screen)
    assert (window.x(), window.y(), window.width(), window.height()) == (
        -1860,
        -120,
        1800,
        25,
    )

    narrow_screen = _ScreenGeometryStub(QRect(-2560, -200, 800, 600))
    live_runtime._position_live_control(window, narrow_screen)
    assert (window.x(), window.y(), window.width(), window.height()) == (
        -2560,
        -200,
        800,
        25,
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

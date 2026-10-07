from __future__ import annotations

import ctypes
import math
import os
import re
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QMetaObject,
    QObject,
    QPoint,
    QPointF,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QFontMetricsF
from PySide6.QtQml import QQmlApplicationEngine, QQmlProperty
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QSystemTrayIcon

from game_screen_translator.config import load_config
from game_screen_translator.gui import qml_workbench as host_module
from game_screen_translator.gui import workbench_controller as controller_module
from game_screen_translator.gui.qml_workbench import QmlWorkbenchHost
from game_screen_translator.gui.theme import SKIN_DOHNA, SKIN_PRISM
from game_screen_translator.gui.workbench_controller import WorkbenchController
from game_screen_translator.live.snapshot import CacheHit, SnapshotEntry, new_snapshot, save_snapshot
from game_screen_translator.profiles import (
    ProfileCaptureSettings,
    apply_profile_runtime_settings,
    create_game_profile,
    load_game_profile,
    save_profile_capture_settings,
    save_profile_runtime_settings,
)


@pytest.fixture(autouse=True)
def _drain_deferred_qt_deletes() -> None:
    app = QApplication.instance()
    if app is not None:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


class _SignalRecorder:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self.callbacks):
            callback(*args)


class _TrayRecorder:
    def __init__(self) -> None:
        self.activated = _SignalRecorder()
        self.visible = False
        self.icon = None
        self.tooltip = ""

    def setIcon(self, icon) -> None:  # noqa: N802
        self.icon = icon

    def setToolTip(self, tooltip: str) -> None:  # noqa: N802
        self.tooltip = tooltip

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False


class _ContextRecorder:
    def __init__(self) -> None:
        self.properties: list[tuple[str, QObject]] = []

    def setContextProperty(self, name: str, value: QObject) -> None:  # noqa: N802
        self.properties.append((name, value))


class _RecordingWindow(QQuickWindow):
    def __init__(self) -> None:
        super().__init__()
        self.release_count = 0

    def releaseResources(self) -> None:  # noqa: N802
        self.release_count += 1
        super().releaseResources()


class _EngineRecorder:
    def __init__(self, _parent: QObject) -> None:
        self.context = _ContextRecorder()
        self.quit = _SignalRecorder()
        self.loaded_urls = []
        self.root = _RecordingWindow()
        self.delete_count = 0

    def rootContext(self):  # noqa: N802
        return self.context

    def load(self, url) -> None:
        self.loaded_urls.append(url)

    def rootObjects(self):  # noqa: N802
        return [self.root]

    def deleteLater(self) -> None:  # noqa: N802
        self.delete_count += 1


class _ControllerStub(QObject):
    stateChanged = Signal()
    regionSelectionRequested = Signal(int)
    liveReady = Signal()
    liveFinished = Signal()
    liveFailed = Signal()
    workbenchHideRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.accepted_regions: list[tuple[int, int, int, int]] = []
        self.cancel_count = 0
        self.shutdown_count = 0
        self.stop_count = 0
        self.host_errors: list[tuple[str, str]] = []
        self.themePreference = "dark"
        self.effectiveTheme = "dark"
        self.skinPreference = SKIN_PRISM

    def acceptRegionSelection(self, *region: int) -> None:  # noqa: N802
        self.accepted_regions.append(region)

    def cancelRegionSelection(self) -> None:  # noqa: N802
        self.cancel_count += 1

    def stopLive(self) -> None:  # noqa: N802
        self.stop_count += 1

    def hideWorkbench(self) -> None:  # noqa: N802
        self.workbenchHideRequested.emit()

    def shutdown(self) -> None:
        self.shutdown_count += 1

    def reportHostError(self, title: str, message: str) -> None:  # noqa: N802
        self.host_errors.append((title, message))


class _SelectorStub(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.selected_region: tuple[int, int, int, int] | None = None
        self.opened = False

    def open(self) -> None:
        self.opened = True


class _ApplicationRecorder:
    def __init__(self) -> None:
        self.aboutToQuit = _SignalRecorder()
        self.quit_count = 0

    def quit(self) -> None:
        self.quit_count += 1

    def screens(self):
        return _application().screens()


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_refra_icon_matches_the_old_prototype_mark() -> None:
    _application()
    image = host_module._build_refra_icon().pixmap(64, 64).toImage()

    assert image.pixelColor(0, 0) == QColor("#080a0e")
    assert image.pixelColor(4, 31) == QColor("#55d9ff")
    assert image.pixelColor(55, 36) == QColor("#e96ecf")
    assert image.pixelColor(16, 13) == QColor("#39434c")
    assert image.pixelColor(24, 55).blue() > image.pixelColor(24, 55).red()


def test_workbench_uses_curve_glyphs_as_the_global_text_default() -> None:
    original = QQuickWindow.textRenderType()
    try:
        QQuickWindow.setTextRenderType(
            QQuickWindow.TextRenderType.QtTextRendering,
        )
        host_module._use_smooth_quick_rendering()
        assert (
            QQuickWindow.textRenderType()
            == QQuickWindow.TextRenderType.CurveTextRendering
        )
    finally:
        QQuickWindow.setTextRenderType(original)


def _find_quick_item(
    root: QQuickWindow | QQuickItem,
    object_name: str,
) -> QQuickItem | None:
    pending = [root.contentItem() if isinstance(root, QQuickWindow) else root]
    while pending:
        item = pending.pop()
        if item.objectName() == object_name:
            return item
        pending.extend(item.childItems())
    return None


def _find_quick_items(
    root: QQuickWindow | QQuickItem,
    object_name: str,
) -> list[QQuickItem]:
    pending = [root.contentItem() if isinstance(root, QQuickWindow) else root]
    matches: list[QQuickItem] = []
    while pending:
        item = pending.pop()
        if item.objectName() == object_name:
            matches.append(item)
        pending.extend(item.childItems())
    return matches


def _wait_for_page_layout(
    window: QQuickWindow,
    item: QQuickItem,
    app: QApplication,
    *,
    timeout_ms: int = 2500,
) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    previous_geometry: tuple[float, float] | None = None
    stable_frames = 0
    while time.monotonic() < deadline:
        app.processEvents()
        settled = (
            not window.property("pageTransitioning")
            and window.property("pageContentReady")
            and item.isVisible()
        )
        geometry = (
            float(item.property("width")),
            float(item.property("height")),
        )
        if settled and min(geometry) > 0:
            if geometry == previous_geometry:
                stable_frames += 1
                if stable_frames >= 2:
                    return
            else:
                stable_frames = 0
        else:
            stable_frames = 0
        previous_geometry = geometry
        QTest.qWait(1)

    raise AssertionError(
        "QML page/layout did not settle within "
        f"{timeout_ms} ms: transitioning={window.property('pageTransitioning')}, "
        f"content_ready={window.property('pageContentReady')}, "
        f"visible={item.isVisible()}, geometry={geometry}"
    )


def _key_clicks(window: QQuickWindow, text: str) -> None:
    for character in text:
        QTest.keyClick(window, ord(character))


def _click_quick_item(window: QQuickWindow, object_name: str) -> QQuickItem:
    item = _find_quick_item(window, object_name)
    assert item is not None, object_name
    assert item.property("visible") is True, object_name
    assert QMetaObject.invokeMethod(item, "click") is True, object_name
    QCoreApplication.processEvents()
    return item


def _slider_scene_point(slider: QQuickItem, visual_position: float) -> QPoint:
    handle = slider.property("handle")
    assert isinstance(handle, QQuickItem)
    handle_width = float(handle.property("width"))
    effective_track_width = float(slider.property("availableWidth")) - handle_width
    local_x = (
        float(slider.property("leftPadding"))
        + handle_width / 2
        + visual_position * effective_track_width
    )
    local_y = (
        float(slider.property("topPadding"))
        + float(slider.property("availableHeight")) / 2
    )
    return slider.mapToScene(QPointF(local_x, local_y)).toPoint()


def _open_dialog(dialog: QObject) -> None:
    assert QMetaObject.invokeMethod(dialog, "open") is True
    QCoreApplication.processEvents()
    assert dialog.property("visible") is True


def _assert_prism_dialog_palette(
    window: QQuickWindow,
    theme: QObject,
    surface_name: str,
    *,
    dark: bool,
) -> None:
    expected_tokens = {
        "Background": "inkRaised",
        "Header": "glassRaised",
        "Content": "inkRaised",
        "Actions": "panel",
    }
    for suffix, token in expected_tokens.items():
        surface = window.findChild(QObject, surface_name + suffix)
        assert surface is not None, surface_name + suffix
        actual = QColor(surface.property("color"))
        expected = QColor(theme.property(token))
        assert actual == expected
        assert actual.lightness() < 128 if dark else actual.lightness() >= 128

    assert window.findChild(QObject, surface_name + "AcceptButton") is not None
    assert window.findChild(QObject, surface_name + "RejectButton") is not None


def _write_config(path: Path) -> None:
    path.write_text(
        """
[translation]
provider = "openai_compatible"
base_url = "http://127.0.0.1:1234/v1"
model = "hy-mt1.5-7b"
""",
        encoding="utf-8",
    )


def _host(
    controller: _ControllerStub,
    *,
    application=None,
    selector_factory=None,
    theme_applier=None,
    tray_factory=None,
) -> tuple[QmlWorkbenchHost, _EngineRecorder]:
    engine = None

    def create_engine(parent: QObject) -> _EngineRecorder:
        nonlocal engine
        engine = _EngineRecorder(parent)
        return engine

    kwargs = {}
    if selector_factory is not None:
        kwargs["selector_factory"] = selector_factory
    if theme_applier is not None:
        kwargs["theme_applier"] = theme_applier
    if tray_factory is not None:
        kwargs["tray_factory"] = tray_factory
    host = QmlWorkbenchHost(
        controller,
        application=application or _application(),
        qml_path=Path(__file__),
        engine_factory=create_engine,
        **kwargs,
    )
    assert engine is not None
    return host, engine


def test_host_exposes_only_workbench_and_rebuilds_engine_around_live() -> None:
    controller = _ControllerStub()
    host, engine = _host(controller)

    assert engine.context.properties == [("workbench", controller)]
    assert len(engine.loaded_urls) == 1
    host.show()
    first_window = host.window
    assert first_window is not None
    assert first_window.isVisible()

    controller.liveReady.emit()
    assert host.window is None
    assert host.engine is None
    assert engine.root.release_count == 1
    assert engine.delete_count == 1

    controller.liveFinished.emit()
    second_window = host.window
    assert second_window is not None
    assert second_window is not first_window
    assert second_window.isVisible()
    controller.liveReady.emit()
    assert host.window is None
    controller.liveFailed.emit()
    restored_window = host.window
    assert restored_window is not None
    assert restored_window.isVisible()

    restored_window.close()


def test_host_configures_smooth_rendering_before_loading_qml(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        host_module,
        "_use_smooth_quick_rendering",
        lambda: calls.append("smooth"),
    )

    host, _ = _host(_ControllerStub())

    assert calls == ["smooth"]
    host.shutdown()


def test_host_tray_recalls_workbench_and_running_close_returns_to_tray() -> None:
    controller = _ControllerStub()
    tray = _TrayRecorder()
    app = _application()
    host, _engine = _host(controller, tray_factory=lambda _app: tray)

    assert tray.icon is not None
    assert tray.icon.cacheKey() == app.windowIcon().cacheKey()
    assert host.window is not None
    assert host.window.icon().cacheKey() == app.windowIcon().cacheKey()
    assert app.quitOnLastWindowClosed() is True
    host.show()
    controller.liveReady.emit()
    assert host.window is None
    assert tray.visible is True
    assert app.quitOnLastWindowClosed() is False

    tray.activated.emit(QSystemTrayIcon.ActivationReason.DoubleClick)
    recalled_window = host.window
    assert recalled_window is not None
    assert recalled_window.isVisible()

    controller.workbenchHideRequested.emit()
    assert host.window is None
    assert tray.visible is True

    controller.liveFinished.emit()
    restored_window = host.window
    assert restored_window is not None
    assert restored_window.isVisible()
    assert tray.visible is False
    assert app.quitOnLastWindowClosed() is True
    host.shutdown()


def test_real_workbench_close_while_running_hides_to_tray(tmp_path: Path) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller._live_process = SimpleNamespace(poll=lambda: None)
    tray = _TrayRecorder()
    host = QmlWorkbenchHost(
        controller,
        application=app,
        tray_factory=lambda _app: tray,
    )
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    assert window.isVisible()

    window.close()
    app.processEvents()

    assert host.window is None
    assert controller.running is True
    assert tray.visible is True
    host.shutdown()


def test_real_workbench_close_while_stopped_keeps_normal_exit_path(
    tmp_path: Path,
) -> None:
    app = _application()
    app.setQuitOnLastWindowClosed(False)
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    tray = _TrayRecorder()
    host = QmlWorkbenchHost(
        controller,
        application=app,
        tray_factory=lambda _app: tray,
    )
    assert app.quitOnLastWindowClosed() is True
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    assert window.isVisible()
    assert controller.running is False

    window.close()
    app.processEvents()

    # The QML onClosing handler accepts a non-running close, so Qt hides the
    # real window and follows its normal last-window quit path.  No tray
    # fallback or host disposal is involved in this branch.
    assert window.isVisible() is False
    assert host.window is window
    assert tray.visible is False
    host.shutdown()


def test_host_applies_theme_once_per_change_and_again_for_rebuilt_window() -> None:
    controller = _ControllerStub()
    applications_and_windows: list[tuple[object, QQuickWindow, str, str]] = []

    def apply_theme(application, window, preference, effective_theme) -> None:
        applications_and_windows.append(
            (application, window, preference, effective_theme)
        )

    host, first_engine = _host(controller, theme_applier=apply_theme)

    assert applications_and_windows == [
        (_application(), first_engine.root, "dark", "dark")
    ]
    host.show()
    QCoreApplication.processEvents()
    assert applications_and_windows[-1] == (
        _application(),
        first_engine.root,
        "dark",
        "dark",
    )
    assert len(applications_and_windows) == 2
    controller.stateChanged.emit()
    assert len(applications_and_windows) == 2

    controller.themePreference = "light"
    controller.effectiveTheme = "light"
    controller.stateChanged.emit()
    assert applications_and_windows[-1][1:] == (
        first_engine.root,
        "light",
        "light",
    )
    controller.stateChanged.emit()
    assert len(applications_and_windows) == 3

    controller.liveReady.emit()
    controller.liveFinished.emit()
    QCoreApplication.processEvents()
    rebuilt_window = host.window
    assert rebuilt_window is not None
    assert rebuilt_window is not first_engine.root
    assert applications_and_windows[-1][1:] == (
        rebuilt_window,
        "light",
        "light",
    )
    # The rebuilt window is themed once on creation and once after Qt shows it.
    assert len(applications_and_windows) == 5

    controller.themePreference = "system"
    controller.effectiveTheme = "dark"
    controller.stateChanged.emit()
    assert applications_and_windows[-1][1:] == (
        rebuilt_window,
        "system",
        "dark",
    )
    assert len(applications_and_windows) == 6
    controller.effectiveTheme = "light"
    controller.stateChanged.emit()
    assert applications_and_windows[-1][1:] == (
        rebuilt_window,
        "system",
        "light",
    )
    assert len(applications_and_windows) == 7
    host.shutdown()


def test_window_theme_helper_sets_qt_scheme_and_optional_windows_dwm() -> None:
    class StyleHintsRecorder:
        def __init__(self) -> None:
            self.schemes: list[Qt.ColorScheme] = []

        def setColorScheme(self, scheme: Qt.ColorScheme) -> None:  # noqa: N802
            self.schemes.append(scheme)

    class ApplicationRecorder:
        def __init__(self) -> None:
            self.hints = StyleHintsRecorder()

        def styleHints(self):  # noqa: N802
            return self.hints

    class WindowRecorder:
        def winId(self) -> int:  # noqa: N802
            return 731

    application = ApplicationRecorder()
    window = WindowRecorder()
    dwm_calls: list[tuple[int, bool]] = []

    host_module._apply_workbench_window_theme(
        application,
        window,
        "dark",
        "dark",
        platform_name="win32",
        dwm_setter=lambda window_id, dark: dwm_calls.append((window_id, dark)),
    )
    host_module._apply_workbench_window_theme(
        application,
        window,
        "light",
        "light",
        platform_name="win32",
        dwm_setter=lambda window_id, dark: dwm_calls.append((window_id, dark)),
    )
    host_module._apply_workbench_window_theme(
        application,
        window,
        "system",
        "dark",
        platform_name="win32",
        dwm_setter=lambda window_id, dark: dwm_calls.append((window_id, dark)),
    )
    host_module._apply_workbench_window_theme(
        application,
        window,
        "dark",
        "dark",
        platform_name="linux",
        dwm_setter=lambda window_id, dark: dwm_calls.append((window_id, dark)),
    )

    assert application.hints.schemes == [
        Qt.ColorScheme.Dark,
        Qt.ColorScheme.Light,
        Qt.ColorScheme.Unknown,
        Qt.ColorScheme.Dark,
    ]
    assert dwm_calls == [(731, True), (731, False), (731, True)]


def test_windows_dwm_adapter_uses_documented_attribute_and_bool_size(
    monkeypatch,
) -> None:
    calls: list[tuple[object, int, object, int]] = []

    class SetterRecorder:
        argtypes = None
        restype = None

        def __call__(self, *args) -> int:
            calls.append(args)
            return 0

    setter = SetterRecorder()
    fake_windll = type(
        "WindllRecorder",
        (),
        {"dwmapi": type("DwmApiRecorder", (), {"DwmSetWindowAttribute": setter})()},
    )()
    monkeypatch.setattr(ctypes, "windll", fake_windll, raising=False)

    host_module._set_windows_immersive_dark_mode(731, True)

    assert len(calls) == 1
    hwnd, attribute, value_pointer, value_size = calls[0]
    assert hwnd.value == 731
    assert attribute == 20
    assert ctypes.cast(value_pointer, ctypes.POINTER(ctypes.c_int)).contents.value == 1
    assert value_size == ctypes.sizeof(ctypes.c_int)


def test_window_theme_helper_safely_ignores_platform_failures() -> None:
    class FailingStyleHints:
        def setColorScheme(self, _scheme) -> None:  # noqa: N802
            raise RuntimeError("unsupported color scheme")

    class ApplicationRecorder:
        def styleHints(self):  # noqa: N802
            return FailingStyleHints()

    class WindowRecorder:
        def winId(self) -> int:  # noqa: N802
            return 731

    def fail_dwm(_window_id: int, _dark: bool) -> None:
        raise OSError("DWM unavailable")

    host_module._apply_workbench_window_theme(
        ApplicationRecorder(),
        WindowRecorder(),
        "dark",
        "dark",
        platform_name="win32",
        dwm_setter=fail_dwm,
    )


def test_host_loads_a_real_quick_window(tmp_path: Path) -> None:
    qml_path = tmp_path / "Main.qml"
    qml_path.write_text(
        "import QtQuick\nWindow { visible: false; width: 320; height: 200 }\n",
        encoding="utf-8",
    )
    controller = _ControllerStub()
    host = QmlWorkbenchHost(
        controller,
        application=_application(),
        qml_path=qml_path,
    )

    assert isinstance(host.window, QQuickWindow)
    assert host.engine is not None
    assert host.engine.rootContext().contextProperty("workbench") is controller
    host.window.close()


def test_real_workbench_loads_exactly_seven_pages_without_qml_warnings(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    qml_warnings: list[str] = []

    def create_engine(parent: QObject) -> QQmlApplicationEngine:
        engine = QQmlApplicationEngine(parent)
        engine.warnings.connect(
            lambda errors: qml_warnings.extend(error.toString() for error in errors)
        )
        return engine

    host = QmlWorkbenchHost(
        controller,
        application=app,
        engine_factory=create_engine,
    )
    page_names = (
        "homePage",
        "capturePage",
        "ocrPage",
        "translationPage",
        "overlayPage",
        "cachePage",
        "settingsPage",
    )

    window = host.window
    initial_engine = host.engine
    assert window is not None
    assert initial_engine is not None
    engine_destroyed: list[bool] = []
    initial_engine.destroyed.connect(lambda: engine_destroyed.append(True))
    assert window.objectName() == "prismWorkbenchWindow"
    assert window.minimumWidth() == 980
    assert window.minimumHeight() == 700
    assert window.property("animationsRunning") is False
    assert (
        QQuickWindow.textRenderType()
        == QQuickWindow.TextRenderType.CurveTextRendering
    )
    assert all(window.findChild(QObject, name) is not None for name in page_names)

    page_stack = window.findChild(QObject, "pageStack")
    assert page_stack is not None
    for index, page in enumerate(
        ("HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS")
    ):
        controller.setPage(page)
        app.processEvents()
        assert page_stack.property("currentIndex") == index

    external_settings = window.findChild(QObject, "externalSettings")
    builtin_settings = window.findChild(QObject, "builtinSettings")
    dynamic_schedule = window.findChild(QObject, "dynamicRoiSchedule")
    full_frame_schedule = window.findChild(QObject, "fullFrameSchedule")
    merge_toggle = window.findChild(QObject, "textMergeToggle")
    prompt_editor = window.findChild(QObject, "profilePromptEditor")
    assert all(
        item is not None
        for item in (
            external_settings,
            builtin_settings,
            dynamic_schedule,
            full_frame_schedule,
            merge_toggle,
            prompt_editor,
        )
    )
    controller.setPage("TRANSLATION")
    app.processEvents()
    assert external_settings.property("visible") is True
    assert builtin_settings.property("visible") is False
    controller.setBackend("builtin")
    app.processEvents()
    assert external_settings.property("visible") is False
    assert builtin_settings.property("visible") is True
    controller.setPage("SETTINGS")
    controller.setDynamicRoiEnabled(True)
    app.processEvents()
    assert dynamic_schedule.property("visible") is True
    assert full_frame_schedule.property("visible") is False
    controller.setDynamicRoiEnabled(False)
    app.processEvents()
    assert dynamic_schedule.property("visible") is False
    assert full_frame_schedule.property("visible") is True
    controller.setPage("OCR")
    controller.setDetectionQualityIndex(0)
    app.processEvents()
    assert merge_toggle.property("enabled") is False
    controller.setPage("TRANSLATION")
    app.processEvents()
    assert prompt_editor.property("enabled") is True

    host.show()
    app.processEvents()
    assert window.property("animationsRunning") is True
    controller.setReducedMotion(True)
    app.processEvents()
    assert window.property("animationsRunning") is False
    controller.liveReady.emit()
    app.processEvents()
    assert host.window is None
    assert host.engine is None
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert engine_destroyed == [True]
    controller.liveFinished.emit()
    app.processEvents()
    rebuilt_window = host.window
    assert rebuilt_window is not None
    assert rebuilt_window is not window
    rebuilt_stack = rebuilt_window.findChild(QObject, "pageStack")
    assert rebuilt_stack is not None
    assert rebuilt_stack.property("currentIndex") == 3
    assert qml_warnings == []
    host.shutdown()


def test_host_uses_light_native_hint_for_dohna_without_changing_saved_theme() -> None:
    controller = _ControllerStub()
    applications_and_windows: list[tuple[object, QQuickWindow, str, str]] = []

    def apply_theme(application, window, preference, effective_theme) -> None:
        applications_and_windows.append(
            (application, window, preference, effective_theme)
        )

    host, _engine = _host(controller, theme_applier=apply_theme)
    controller.skinPreference = SKIN_DOHNA
    controller.themePreference = "dark"
    controller.effectiveTheme = "light"
    controller.stateChanged.emit()
    assert applications_and_windows[-1][2:] == ("light", "light")
    assert controller.themePreference == "dark"

    controller.skinPreference = SKIN_PRISM
    controller.stateChanged.emit()
    assert applications_and_windows[-1][2:] == ("dark", "light")
    host.shutdown()


def test_real_profile_dropdown_switches_and_restores_runtime_state(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    machine_config = load_config(config_path)
    profile_a = create_game_profile(
        config_path,
        machine_config,
        "galgame-a",
        display_name="Galgame A",
    )
    profile_b = create_game_profile(
        config_path,
        machine_config,
        "galgame-b",
        display_name="Galgame B",
    )
    save_profile_capture_settings(
        profile_a,
        ProfileCaptureSettings(monitor_index=0, region=(10, 20, 320, 140)),
    )
    save_profile_runtime_settings(
        profile_a,
        replace(
            machine_config,
            translation=replace(machine_config.translation, model="profile-a-model"),
            ocr=replace(
                machine_config.ocr,
                device="gpu:1",
                text_filter_enabled=False,
                detection_max_side=640,
            ),
            preview=replace(machine_config.preview, overlay_opacity=0.1),
            live=replace(
                machine_config.live,
                dynamic_roi_enabled=True,
                change_poll_fps=9,
                debug_border=True,
            ),
        ),
    )
    save_profile_capture_settings(
        profile_b,
        ProfileCaptureSettings(monitor_index=0, region=(40, 50, 520, 220)),
    )
    save_profile_runtime_settings(
        profile_b,
        replace(
            machine_config,
            translation=replace(machine_config.translation, model="profile-b-model"),
            ocr=replace(
                machine_config.ocr,
                device="gpu:0",
                text_filter_enabled=True,
                detection_max_side=2048,
            ),
            preview=replace(machine_config.preview, overlay_opacity=0.8),
            live=replace(
                machine_config.live,
                dynamic_roi_enabled=False,
                change_poll_fps=13,
                debug_border=False,
            ),
        ),
    )

    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    selector = window.findChild(QObject, "homeProfileSelector")
    assert isinstance(selector, QQuickItem)
    profile_card = window.findChild(QObject, "activeProfileCard")
    profile_name = window.findChild(QObject, "activeProfileName")
    assert isinstance(profile_card, QQuickItem)
    assert isinstance(profile_name, QQuickItem)
    assert controller.profileNames == ["Galgame A", "Galgame B"]
    assert controller.currentProfileIndex == 0
    assert selector.property("currentIndex") == 0
    activated_indices: list[int] = []
    selector.activated.connect(activated_indices.append)

    def assert_active_profile(name: str) -> None:
        visible_text = [
            item.property("text")
            for item in profile_card.findChildren(QQuickItem)
            if item.isVisible() and item.property("text") is not None
        ]
        assert sorted(visible_text) == sorted(["ACTIVE PROFILE", name])
        assert profile_name.property("text") == name
        assert profile_name.property("font").pixelSize() == (
            selector.property("font").pixelSize()
        )

    def assert_profile_a() -> None:
        assert_active_profile("Galgame A")
        assert controller.currentProfileId == "galgame-a"
        assert controller.captureLeft == 10
        assert controller.captureTop == 20
        assert controller.captureWidth == 320
        assert controller.captureHeight == 140
        assert controller.ocrDevice == "gpu:1"
        assert controller.ocrFilterEnabled is False
        assert controller.model == "profile-a-model"
        assert controller.overlayOpacity == 0.1
        assert controller.dynamicRoiEnabled is True
        assert controller.changePollFps == 9
        assert controller.debugEnabled is True
        assert selector.property("currentIndex") == 0

    def assert_profile_b() -> None:
        assert_active_profile("Galgame B")
        assert controller.currentProfileId == "galgame-b"
        assert controller.captureLeft == 40
        assert controller.captureTop == 50
        assert controller.captureWidth == 520
        assert controller.captureHeight == 220
        assert controller.ocrDevice == "gpu:0"
        assert controller.ocrFilterEnabled is True
        assert controller.model == "profile-b-model"
        assert controller.overlayOpacity == 0.8
        assert controller.dynamicRoiEnabled is False
        assert controller.changePollFps == 13
        assert controller.debugEnabled is False
        assert selector.property("currentIndex") == 1

    def choose_with_dropdown(index: int, key: Qt.Key) -> None:
        center = selector.mapToScene(
            QPointF(selector.width() / 2, selector.height() / 2)
        ).toPoint()
        QTest.mouseClick(
            window,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            center,
        )
        app.processEvents()
        QTest.keyClick(window, key)
        QTest.keyClick(window, Qt.Key.Key_Return)
        app.processEvents()
        assert controller.currentProfileIndex == index
        assert selector.property("currentIndex") == index

    assert_profile_a()
    choose_with_dropdown(1, Qt.Key.Key_Down)
    assert_profile_b()
    choose_with_dropdown(0, Qt.Key.Key_Up)
    assert_profile_a()
    assert activated_indices == [1, 0]
    host.shutdown()


@pytest.mark.parametrize("skin", [SKIN_PRISM, SKIN_DOHNA])
def test_real_skin_dropdown_highlight_uses_skin_specific_surface(
    tmp_path: Path,
    skin: str,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(skin)
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    selector = window.findChild(QObject, "homeSkinSelector")
    theme = window.findChild(QObject, "prismTheme")
    assert isinstance(selector, QQuickItem)
    assert theme is not None
    center = selector.mapToScene(
        QPointF(selector.width() / 2, selector.height() / 2)
    ).toPoint()
    QTest.mouseClick(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        center,
    )
    app.processEvents()

    def wait_for_delegates(object_name: str, minimum: int = 1) -> list[QQuickItem]:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            app.processEvents()
            delegates = _find_quick_items(window, object_name)
            if len(delegates) >= minimum:
                return delegates
            QTest.qWait(10)
        return _find_quick_items(window, object_name)

    def assert_prism_highlight(delegates: list[QQuickItem]) -> None:
        assert delegates
        input_surface = QColor(theme.property("inputSurface"))
        accent = QColor(theme.property("accent"))
        colors = [QColor(delegate.property("color")) for delegate in delegates]
        highlighted = [color for color in colors if color != input_surface]
        assert highlighted
        for color in highlighted:
            assert (color.red(), color.green(), color.blue()) == (
                accent.red(),
                accent.green(),
                accent.blue(),
            )
            assert 0 < color.alpha() < 255
        if len(colors) >= 2:
            assert input_surface in colors
            assert len({color.name(QColor.HexArgb) for color in colors}) >= 2

    if skin == SKIN_PRISM:
        rows = wait_for_delegates(
            "prismComboBoxDelegatePrismBackground",
            minimum=2,
        )
        assert_prism_highlight(rows)

        assert selector.property("highlightedIndex") == 0
        QTest.keyClick(window, Qt.Key.Key_Down)
        rows = wait_for_delegates(
            "prismComboBoxDelegatePrismBackground",
            minimum=2,
        )
        assert selector.property("highlightedIndex") == 1
        assert_prism_highlight(rows)
    else:
        cuts = wait_for_delegates("prismComboBoxDohnaDelegateCut")
        assert cuts

        def assert_borderless_selection() -> None:
            for item in wait_for_delegates("prismComboBoxDohnaDelegateCut"):
                path = item.findChild(QObject, "prismComboBoxDohnaDelegatePath")
                assert path.property("strokeWidth") == 0
                assert QColor(path.property("strokeColor")).alpha() == 0
            for name in ("prismComboBoxDohnaBodyPath", "prismComboBoxDohnaPopupPath"):
                paths = window.findChildren(QObject, name)
                assert paths
                assert all(path.property("strokeWidth") == 0 for path in paths)
            assert selector.findChild(QObject, "prismComboBoxDohnaArrowFace") is None
            assert not window.findChildren(QObject, "prismComboBoxDohnaPopupShadow")

        assert_borderless_selection()
        assert any(
            item.property("visible") is True
            and item.property("x") >= 4
            and item.property("x") + item.property("width") <= selector.width() - 13
            and item.property("height") > 0
            for item in cuts
        )
        colors = [
            QColor(item.findChild(QObject, "prismComboBoxDohnaDelegatePath").property("fillColor"))
            for item in cuts
            if item.property("visible") is True
        ]
        assert QColor(theme.property("accent")) in colors
        QTest.keyClick(window, Qt.Key.Key_Up)
        cuts = wait_for_delegates("prismComboBoxDohnaDelegateCut")
        assert selector.property("highlightedIndex") == 0
        assert any(
            item.property("visible") is True
            and item.property("x") >= 4
            and item.property("x") + item.property("width") <= selector.width() - 13
            and item.property("height") > 0
            for item in cuts
        )
        colors = [
            QColor(item.findChild(QObject, "prismComboBoxDohnaDelegatePath").property("fillColor"))
            for item in cuts
            if item.property("visible") is True
        ]
        assert QColor(theme.property("violet")) in colors
        assert QColor(theme.property("accent")) in colors
        assert_borderless_selection()

        # Border removal must keep the real keyboard selection path working.
        QTest.keyClick(window, Qt.Key.Key_Return)
        app.processEvents()
        assert controller.skinPreference == SKIN_PRISM

    QTest.keyClick(window, Qt.Key.Key_Escape)
    app.processEvents()
    host.shutdown()


def test_profile_and_external_model_names_use_one_control(tmp_path: Path) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(config_path, load_config(config_path), "game", display_name="测试游戏")
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    try:
        host.show()
        app.processEvents()
        window = host.window
        assert window is not None
        window.resize(1280, 1000)
        profile_hint = window.findChild(QObject, "settingHint-home-profile-label")
        assert profile_hint is not None
        profile_label = profile_hint.property("target")
        assert profile_label.property("meta") == ""
        profile_selector = window.findChild(QObject, "homeProfileSelector")
        assert profile_selector is not None
        assert profile_selector.property("currentText") == "测试游戏"
        assert controller.maxConcurrency == 4
        assert controller.builtinParallel == 4
        assert controller.dynamicRoiEnabled is True
        assert controller.clearAfterMs == 150
        assert controller.roiResponseTargetMs == 350

        controller.setPage("TRANSLATION")
        page = window.findChild(QObject, "translationPage")
        assert isinstance(page, QQuickItem)
        _wait_for_page_layout(window, page, app)
        model_hints = window.findChildren(QObject, "settingHint-translation-external-model-control")
        assert len(model_hints) == 1
        selector = window.findChild(QObject, "externalModelSelector")
        editor = _find_quick_item(window, "externalModelEditor")
        assert isinstance(selector, QQuickItem)
        assert isinstance(editor, QQuickItem)
        assert selector.property("editable") is True
        assert editor.property("text") == controller.model

        editor.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        _key_clicks(window, "custom-model")
        app.processEvents()
        assert controller.model == "custom-model"
        assert editor.property("text") == "custom-model"

        reply = SimpleNamespace(
            error=lambda: controller_module.QNetworkReply.NetworkError.NoError,
            readAll=lambda: b'{"data":[{"id":"server-a"},{"id":"server-b"}]}',
            deleteLater=lambda: None,
        )
        controller._model_reply = reply
        controller._models_loaded(reply, "http://127.0.0.1:1234/v1/models")
        app.processEvents()
        assert editor.property("text") == "custom-model"
        assert selector.property("count") == 3

        selector.forceActiveFocus()
        QTest.mouseClick(
            window,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            selector.mapToScene(QPointF(selector.width() - 10, selector.height() / 2)).toPoint(),
        )
        app.processEvents()
        QTest.keyClick(window, Qt.Key.Key_Down)
        QTest.keyClick(window, Qt.Key.Key_Return)
        app.processEvents()
        assert controller.model == "server-a"
        assert editor.property("text") == "server-a"
        editor.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(window, Qt.Key.Key_Backspace)
        app.processEvents()
        assert controller.model == ""
        assert editor.property("text") == ""
        _key_clicks(window, "custom-after-fetch")
        app.processEvents()
        assert controller.model == "custom-after-fetch"
        controller.setModel("server-a")
        app.processEvents()
        assert editor.property("text") == "server-a"
        assert controller.saveRuntimeSettings() is True
        restored = apply_profile_runtime_settings(
            load_config(config_path),
            load_game_profile(config_path, load_config(config_path), "game"),
        )
        assert restored.translation.model == "server-a"
    finally:
        host.shutdown()


def test_real_setting_hints_cover_editable_options_and_exclude_read_only_actions(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    window.resize(980, 700)
    window.update()
    QTest.qWait(20)

    expected_parts = {
        "home-profile": {"label", "control"},
        "home-skin": {"label", "control"},
        "home-theme": {"label", "control"},
        "home-motion": {"control"},
        "capture-monitor": {"label", "control"},
        "capture-fullscreen": {"control"},
        "capture-custom": {"control"},
        "capture-left": {"label", "control"},
        "capture-top": {"label", "control"},
        "capture-width": {"label", "control"},
        "capture-height": {"label", "control"},
        "ocr-device": {"label", "control"},
        "ocr-quality": {"label", "control"},
        "ocr-filter": {"control"},
        "ocr-merge": {"control"},
        "ocr-dynamic": {"label", "control"},
        "translation-backend": {"control"},
        "translation-builtin-model": {"label", "control"},
        "translation-builtin-device": {"label", "control"},
        "translation-builtin-parallel": {"label", "control"},
        "translation-builtin-cache": {"label", "control"},
        "translation-external-url": {"label", "control"},
        "translation-external-key": {"label", "control"},
        "translation-external-model": {"label", "control"},
        "translation-external-concurrency": {"label", "control"},
        "translation-prompt": {"label", "control"},
        "overlay-opacity": {"label", "control"},
        "settings-poll-fps": {"label", "control"},
        "settings-clear-after": {"label", "control"},
        "settings-roi-response": {"label", "control"},
        "settings-stable-rescan": {"label", "control"},
        "settings-idle-rescan": {"label", "control"},
        "settings-ocr-cooldown": {"label", "control"},
        "settings-browser-overlay": {"label", "control"},
        "settings-debug-border": {"control"},
    }

    hint_items: dict[tuple[str, str], list[QObject]] = {}
    for item in window.findChildren(QObject):
        object_name = item.objectName()
        if object_name.startswith("settingHint-"):
            hint_name = object_name.removeprefix("settingHint-")
            part = next(
                part_name
                for part_name in ("label", "control", "editor")
                if hint_name.endswith("-" + part_name)
            )
            key = hint_name[: -(len(part) + 1)]
            hint_items.setdefault((key, part), []).append(item)

    actual_parts = {
        key: {part for (item_key, part) in hint_items if item_key == key}
        for key in expected_parts
    }
    assert actual_parts == expected_parts
    assert set(hint_items) == {
        (key, part) for key, parts in expected_parts.items() for part in parts
    }
    expected_counts = {key_and_part: 1 for key_and_part in hint_items}
    expected_counts[("translation-backend", "control")] = 2
    assert {
        key_and_part: len(items) for key_and_part, items in hint_items.items()
    } == expected_counts
    assert all(
        hint.property("description")
        and any(
            "\u4e00" <= character <= "\u9fff"
            for character in str(hint.property("description"))
        )
        for hints in hint_items.values()
        for hint in hints
    )

    named_hints = [hint for hints in hint_items.values() for hint in hints]
    hint_targets = [hint.property("target") for hint in named_hints]
    for item in window.findChildren(QObject):
        if (
            item.metaObject().indexOfProperty("readOnly") >= 0
            and item.property("readOnly") is True
        ):
            assert item not in hint_targets
    for object_name in (
        "openCreateProfileDialogButton",
        "createProfileNameField",
        "ocrProbeAction",
        "openDeleteModelDialogButton",
    ):
        excluded = window.findChild(QObject, object_name)
        assert excluded is not None
        assert excluded not in hint_targets

    for editor_name, setting_key in (
        ("glossaryEditor", "translation-glossary"),
        ("correctionsEditor", "cache-corrections"),
    ):
        editor = window.findChild(QObject, editor_name)
        assert editor is not None
        assert editor.property("entryCount") == 0
        assert not any(
            item.objectName().startswith("settingHint-" + setting_key)
            for item in editor.findChildren(QObject)
        )
        action_texts = {
            "添加一行",
            "删除选中行",
            str(editor.property("saveText")),
        }
        actions = [
            item
            for item in editor.findChildren(QObject)
            if item.metaObject().indexOfProperty("settingDescription") >= 0
            and str(item.property("text")) in action_texts
        ]
        assert {str(action.property("text")) for action in actions} == action_texts
        for action in actions:
            assert action.property("settingDescription") == ""
            assert action.property("settingKey") == ""
            action_hints = [
                item
                for item in action.findChildren(QObject)
                if item.metaObject().indexOfProperty("hintVisible") >= 0
            ]
            assert len(action_hints) == 1
            assert action_hints[0].property("description") == ""
            assert action_hints[0].property("enabled") is False

    def setting_hint(object_name: str) -> tuple[QObject, QQuickItem]:
        hint = window.findChild(QObject, object_name)
        assert hint is not None
        target = hint.property("target")
        assert isinstance(target, QQuickItem)
        return hint, target

    def move_out(hint: QObject) -> None:
        QTest.mouseMove(window, QPoint(2, 2))
        app.processEvents()
        assert hint.property("hintVisible") is False

    def hover_target(
        hint: QObject,
        target: QQuickItem,
        local_point: QPointF | None = None,
    ) -> None:
        point_in_target = local_point or QPointF(
            target.width() / 2,
            target.height() / 2,
        )
        point = target.mapToScene(point_in_target).toPoint()
        QTest.mouseMove(window, point)
        QTest.qWait(300)
        assert hint.property("hintVisible") is False
        QTest.qWait(150)
        assert hint.property("hintVisible") is True

    label_hint, label_target = setting_hint("settingHint-home-theme-label")
    control_hint, control_target = setting_hint("settingHint-home-theme-control")
    assert label_target.height() > 20
    hover_target(
        label_hint,
        label_target,
        QPointF(label_target.width() / 2, label_target.height() - 2),
    )
    move_out(label_hint)
    hover_target(control_hint, control_target)
    assert label_hint.property("description") == control_hint.property("description")
    move_out(control_hint)

    controller.setPage("SETTINGS")
    controller.setDynamicRoiEnabled(False)
    app.processEvents()
    window.update()
    QTest.qWait(20)

    stepper_hint, stepper = setting_hint(
        "settingHint-settings-poll-fps-control"
    )
    assert stepper.objectName() == "settingsCalibrationStepper"
    assert float(stepper.property("width")) == float(
        stepper.property("compactWidth")
    )
    direct_controls = {
        child.objectName(): child
        for child in stepper.childItems()
        if child.objectName()
    }
    assert set(direct_controls) == {
        "numberStepperDecrease",
        "numberStepperEditor",
        "numberStepperIncrease",
    }
    for child in direct_controls.values():
        child_center = child.mapToItem(
            stepper,
            QPointF(child.width() / 2, child.height() / 2),
        )
        hover_target(stepper_hint, stepper, child_center)
        move_out(stepper_hint)

    increase = direct_controls["numberStepperIncrease"]
    before_click = controller.changePollFps
    increase_point = increase.mapToScene(
        QPointF(increase.width() / 2, increase.height() / 2)
    ).toPoint()
    hover_target(
        stepper_hint,
        stepper,
        increase.mapToItem(
            stepper,
            QPointF(increase.width() / 2, increase.height() / 2),
        ),
    )
    QTest.mouseClick(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        increase_point,
    )
    app.processEvents()
    assert controller.changePollFps == before_click + 1
    move_out(stepper_hint)

    controller.setPage("OCR")
    controller.setDetectionQualityIndex(0)
    app.processEvents()
    window.update()
    QTest.qWait(20)
    merge_toggle = window.findChild(QObject, "textMergeToggle")
    assert merge_toggle is not None
    assert merge_toggle.property("enabled") is False
    disabled_hint, disabled_target = setting_hint("settingHint-ocr-merge-control")
    hover_target(disabled_hint, disabled_target)
    move_out(disabled_hint)

    controller.setPage("SETTINGS")
    app.processEvents()
    window.update()
    QTest.qWait(20)
    edge_hint, edge_target = setting_hint(
        "settingHint-settings-ocr-cooldown-control"
    )
    ancestor = edge_target.parentItem()
    flickable = None
    while ancestor is not None:
        if (
            ancestor.metaObject().indexOfProperty("contentY") >= 0
            and ancestor.metaObject().indexOfProperty("contentHeight") >= 0
        ):
            flickable = ancestor
            break
        ancestor = ancestor.parentItem()
    assert flickable is not None
    target_in_view = edge_target.mapToItem(flickable, QPointF(0, 0))
    desired_y = float(flickable.property("height")) - edge_target.height() - 12
    requested_content_y = (
        float(flickable.property("contentY")) + target_in_view.y() - desired_y
    )
    maximum_content_y = max(
        0.0,
        float(flickable.property("contentHeight"))
        - float(flickable.property("height")),
    )
    flickable.setProperty(
        "contentY",
        max(0.0, min(maximum_content_y, requested_content_y)),
    )
    window.update()
    QTest.qWait(20)
    app.processEvents()

    hover_target(edge_hint, edge_target)

    def scene_rect(item: QQuickItem) -> tuple[float, float, float, float]:
        origin = item.mapToScene(QPointF(0, 0))
        opposite = item.mapToScene(QPointF(item.width(), item.height()))
        return (
            min(origin.x(), opposite.x()),
            min(origin.y(), opposite.y()),
            abs(opposite.x() - origin.x()),
            abs(opposite.y() - origin.y()),
        )

    def assert_hint_geometry() -> tuple[float, float]:
        target_x, target_y, target_width, target_height = scene_rect(edge_target)
        view_x, view_y, view_width, view_height = scene_rect(flickable)
        popup_x = float(edge_hint.property("hintX"))
        popup_y = float(edge_hint.property("hintY"))
        popup_width = float(edge_hint.property("hintWidth"))
        popup_height = float(edge_hint.property("hintHeight"))
        visible_left = max(0.0, view_x) + 8
        visible_top = max(0.0, view_y) + 8
        visible_right = min(float(window.width()), view_x + view_width) - 8
        visible_bottom = min(float(window.height()), view_y + view_height) - 8

        assert popup_x >= visible_left - 0.5
        assert popup_y >= visible_top - 0.5
        assert popup_x + popup_width <= visible_right + 0.5
        assert popup_y + popup_height <= visible_bottom + 0.5
        vertical_gap = min(
            abs(popup_y - (target_y + target_height)),
            abs(target_y - (popup_y + popup_height)),
        )
        assert 7.0 <= vertical_gap <= 9.0
        assert popup_x <= target_x + target_width
        assert popup_x + popup_width >= target_x
        return target_y, popup_y

    first_target_y, first_popup_y = assert_hint_geometry()
    current_content_y = float(flickable.property("contentY"))
    moved_content_y = min(maximum_content_y, current_content_y + 16)
    if math.isclose(moved_content_y, current_content_y):
        moved_content_y = max(0.0, current_content_y - 16)
    assert not math.isclose(moved_content_y, current_content_y)
    flickable.setProperty("contentY", moved_content_y)
    window.update()
    QTest.qWait(20)
    QTest.mouseMove(
        window,
        edge_target.mapToScene(
            QPointF(edge_target.width() / 2, edge_target.height() / 2)
        ).toPoint(),
    )
    QTest.qWait(40)
    assert edge_hint.property("hintVisible") is True
    second_target_y, second_popup_y = assert_hint_geometry()
    assert math.isclose(
        second_popup_y - first_popup_y,
        second_target_y - first_target_y,
        abs_tol=1.0,
    )
    move_out(edge_hint)
    host.shutdown()


def test_pair_editor_existing_rows_show_one_adjacent_hint_and_remain_editable(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.saveGlossary([{"source": "仕事", "target": "委托"}])
    controller.saveCorrections([{"source": "待て。", "target": "等等。"}])
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    window.resize(980, 700)

    def visible_hints() -> list[QObject]:
        pending = [window.contentItem()]
        result: list[QObject] = []
        while pending:
            item = pending.pop()
            result.extend(
                child
                for child in item.children()
                if child.metaObject().indexOfProperty("hintVisible") >= 0
                and child.property("hintVisible") is True
            )
            pending.extend(item.childItems())
        return result

    def scene_rect(item: QQuickItem) -> tuple[float, float, float, float]:
        origin = item.mapToScene(QPointF(0, 0))
        opposite = item.mapToScene(QPointF(item.width(), item.height()))
        return (
            min(origin.x(), opposite.x()),
            min(origin.y(), opposite.y()),
            abs(opposite.x() - origin.x()),
            abs(opposite.y() - origin.y()),
        )

    cases = (
        (
            "TRANSLATION",
            "translationPage",
            "sideMode",
            "glossary",
            "glossaryEditor",
            "translation-glossary",
        ),
        (
            "CACHE",
            "cachePage",
            "mode",
            "corrections",
            "correctionsEditor",
            "cache-corrections",
        ),
    )
    for page_name, page_object, mode_property, mode, editor_name, setting_key in cases:
        controller.setPage(page_name)
        page = window.findChild(QObject, page_object)
        assert page is not None
        page.setProperty(mode_property, mode)
        app.processEvents()
        window.update()
        QTest.qWait(20)
        app.processEvents()

        editor = window.findChild(QObject, editor_name)
        assert isinstance(editor, QQuickItem)
        assert editor.property("entryCount") == 1
        assert editor.findChild(
            QObject,
            "settingHint-" + setting_key + "-editor",
        ) is None

        for part, field_name in (
            ("source", "pairSourceField-0"),
            ("target", "pairTargetField-0"),
        ):
            field = _find_quick_item(editor, field_name)
            assert isinstance(field, QQuickItem)
            hint = field.findChild(
                QObject,
                "settingHint-" + setting_key + "-" + part + "-0-control",
            )
            assert hint is not None
            assert hint.property("target") == field
            assert hint.property("enabled") is True
            assert hint.property("description")
            assert field.property("visible") is True
            assert field.width() > 0
            assert field.height() > 0
            ancestor = field
            while ancestor is not None:
                assert ancestor.property("visible") is True, (
                    page_name,
                    ancestor.objectName(),
                )
                assert float(ancestor.property("opacity")) > 0, (
                    page_name,
                    ancestor.objectName(),
                )
                ancestor = ancestor.parentItem()

            field_center = field.mapToScene(
                QPointF(field.width() / 2, field.height() / 2)
            ).toPoint()
            assert 0 <= field_center.x() < window.width(), (
                page_name,
                field_center,
            )
            assert 0 <= field_center.y() < window.height(), (
                page_name,
                field_center,
            )
            QTest.mouseMove(window, field_center)
            app.processEvents()
            assert hint.property("hovered") is True
            QTest.qWait(300)
            assert visible_hints() == []
            QTest.qWait(150)
            actual_hints = visible_hints()
            assert actual_hints == [hint], (
                hint.property("hintVisible"),
                hint.property("hovered"),
                hint.property("hintX"),
                hint.property("hintY"),
                hint.property("hintWidth"),
                hint.property("hintHeight"),
            )

            target_x, target_y, target_width, target_height = scene_rect(field)
            popup_x = float(hint.property("hintX"))
            popup_y = float(hint.property("hintY"))
            popup_width = float(hint.property("hintWidth"))
            popup_height = float(hint.property("hintHeight"))
            vertical_gap = min(
                abs(popup_y - (target_y + target_height)),
                abs(target_y - (popup_y + popup_height)),
            )
            assert 7.0 <= vertical_gap <= 9.0
            assert popup_x <= target_x + target_width
            assert popup_x + popup_width >= target_x

            before_text = str(field.property("text"))
            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                field_center,
            )
            app.processEvents()
            assert field.property("activeFocus") is True
            assert visible_hints() == [hint]
            QTest.keyClick(window, Qt.Key.Key_End)
            _key_clicks(window, "x")
            app.processEvents()
            assert field.property("text") == before_text + "x"

            QTest.mouseMove(window, QPoint(2, 2))
            app.processEvents()
            assert hint.property("hintVisible") is False
            assert visible_hints() == []

    host.shutdown()


def test_real_dohna_skin_switches_from_home_and_keeps_prism_theme_preference(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setTheme("dark")
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    window.resize(980, 700)
    app.processEvents()

    skin_selector = window.findChild(QObject, "homeSkinSelector")
    theme_selector = window.findChild(QObject, "homeThemeSelector")
    theme = window.findChild(QObject, "prismTheme")
    stage = window.findChild(QObject, "opticalStage")
    backdrop = window.findChild(QObject, "dohnaBackdrop")
    assert skin_selector is not None
    assert theme is not None
    assert stage is not None
    assert backdrop is not None
    assert skin_selector.property("currentIndex") == 0
    assert theme.property("dohna") is False
    assert stage.property("visible") is True

    for index in range(7):
        navigation_button = _find_quick_item(window, f"navigationButton{index}")
        assert navigation_button is not None
        assert navigation_button.property("visible") is True

    center = skin_selector.mapToScene(
        QPointF(skin_selector.width() / 2, skin_selector.height() / 2)
    ).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=center)
    app.processEvents()
    QTest.keyClick(window, Qt.Key.Key_Down)
    QTest.keyClick(window, Qt.Key.Key_Return)
    app.processEvents()

    assert controller.skinPreference == SKIN_DOHNA
    assert controller.themePreference == "dark"
    assert controller.effectiveTheme == "light"
    assert skin_selector.property("currentIndex") == 1
    assert theme.property("dohna") is True
    assert theme.property("dark") is False
    for index in range(7):
        navigation_button = _find_quick_item(window, f"navigationButton{index}")
        assert navigation_button is not None
        assert navigation_button.property("visible") is True
    assert theme_selector is not None
    assert theme_selector.property("enabled") is False
    assert stage.property("visible") is False
    assert backdrop.property("visible") is True
    assert window.findChild(QObject, "homeDohnaThemeHint").property("visible") is True
    assert window.findChild(QObject, "pageDisplayTitleLight").property("text") == "翻译控制台"
    skin_body = skin_selector.findChild(QObject, "prismComboBoxDohnaBody")
    assert skin_body is not None
    assert skin_body.property("visible") is True
    assert skin_body.findChild(QObject, "prismComboBoxDohnaBodyPath").property("strokeWidth") == 0
    assert skin_selector.findChild(QObject, "prismComboBoxDohnaArrowFace") is None
    assert skin_selector.findChild(QObject, "prismComboBoxDohnaShadow") is None
    assert skin_selector.findChild(QObject, "prismComboBoxDohnaCorner") is None

    secondary_scroll = window.findChild(QObject, "homeSecondaryScroll")
    assert secondary_scroll is not None
    motion_toggle = next(
        item
        for item in window.findChildren(QQuickItem)
        if item.property("settingKey") == "home-motion"
    )
    secondary_scroll.setProperty(
        "contentY",
        max(
            0.0,
            float(secondary_scroll.property("contentHeight"))
            - float(secondary_scroll.property("height")),
        ),
    )
    app.processEvents()
    motion_origin = motion_toggle.mapToItem(secondary_scroll, QPointF(0, 0))
    assert 0 <= motion_origin.y() <= secondary_scroll.height()

    page_titles = {
        "HOME": "翻译控制台",
        "CAPTURE": "画面捕获",
        "OCR": "文字识别",
        "TRANSLATION": "译文设置",
        "OVERLAY": "字幕叠加",
        "CACHE": "翻译缓存",
        "SETTINGS": "高级设置",
    }
    for page, title in page_titles.items():
        controller.setPage(page)
        app.processEvents()
        assert window.findChild(QObject, "pageDisplayTitleLight").property("text") == title

    controller.setPage("HOME")
    app.processEvents()
    create_dialog = window.findChild(QObject, "createProfileDialog")
    assert create_dialog is not None
    _open_dialog(create_dialog)
    _assert_prism_dialog_palette(window, theme, "createProfileDialog", dark=False)
    _click_quick_item(window, "createProfileDialogRejectButton")

    controller.setPage("CAPTURE")
    app.processEvents()
    assert window.findChild(QObject, "pageDisplayTitleLight").property("text") == "画面捕获"
    controller.setPage("HOME")
    controller.setSkin(SKIN_PRISM)
    app.processEvents()
    assert controller.themePreference == "dark"
    assert theme.property("dohna") is False
    assert theme.property("dark") is True
    assert stage.property("visible") is True
    host.shutdown()


def test_real_dohna_uses_short_pop_feedback_and_settles_on_switch_or_hide(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setTheme("dark")
    controller.setSkin(SKIN_DOHNA)
    controller.setReducedMotion(False)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    theme = window.findChild(QObject, "prismTheme")
    stage = window.findChild(QObject, "opticalStage")
    feedback = window.findChild(QObject, "dohnaFeedbackLayer")
    sweep = window.findChild(QObject, "pageTransitionSweep")
    page_content = window.findChild(QObject, "pageContentMotion")
    content_translate = window.findChild(QObject, "pageContentTranslate")
    page_header = window.findChild(QObject, "pageHeaderSlice")
    page_title = window.findChild(QObject, "pageDisplayTitle")
    panel_body = window.findChild(QObject, "prismPanelDohnaBody")
    toggle_cut = window.findChild(QObject, "prismToggleDohnaCut")
    save_button = window.findChild(QObject, "saveAllButton")
    nav_button = _find_quick_item(window, "navigationButton1")
    required_items = {
        "theme": theme,
        "stage": stage,
        "feedback": feedback,
        "sweep": sweep,
        "page_content": page_content,
        "content_translate": content_translate,
        "page_header": page_header,
        "page_title": page_title,
        "panel_body": panel_body,
        "toggle_cut": toggle_cut,
        "save_button": save_button,
        "nav_button": nav_button,
    }
    assert all(item is not None for item in required_items.values()), [
        name for name, item in required_items.items() if item is None
    ]
    assert theme.property("dohna") is True
    for decoration in (
        "dohnaPageImpact",
        "dohnaPageImpactShadow",
        "prismPanelDohnaStamp",
        "prismPanelDohnaStampShadow",
        "prismButtonDohnaFocusSlash",
    ):
        assert not window.findChildren(QObject, decoration)
    backdrop = window.findChild(QObject, "dohnaBackdrop")
    assert backdrop is not None
    assert backdrop.findChild(QObject, "dohnaPrintFacet").property("visible") is True
    assert stage.property("motionEnabled") is False
    assert sweep.property("visible") is False
    assert panel_body.property("visible") is True
    assert panel_body.property("width") > 0
    assert panel_body.property("height") > 0
    assert float(page_content.property("opacity")) == 1
    assert float(page_header.property("opacity")) == 1
    assert float(panel_body.property("opacity")) == 1
    assert float(page_title.property("opacity")) == 1
    assert toggle_cut.property("width") == 34
    assert toggle_cut.property("height") == 18
    for path_name in (
        "prismToggleDohnaPathTopRight",
        "prismToggleDohnaPathBottomRight",
        "prismToggleDohnaPathBottomLeft",
    ):
        path = toggle_cut.findChild(QObject, path_name)
        assert path is not None
        assert 0 <= float(path.property("x")) <= float(toggle_cut.property("width"))
        assert 0 <= float(path.property("y")) <= float(toggle_cut.property("height"))
    dohna_shape = save_button.findChild(QObject, "prismButtonDohnaCut")
    assert dohna_shape is not None
    assert dohna_shape.property("visible") is True

    skin_selector = window.findChild(QObject, "homeSkinSelector")
    assert skin_selector is not None
    selector_center = skin_selector.mapToScene(
        QPointF(skin_selector.width() / 2, skin_selector.height() / 2)
    ).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=selector_center)
    QTest.qWait(30)
    app.processEvents()
    popup_bodies = window.findChildren(QObject, "prismComboBoxDohnaPopupBody")
    assert popup_bodies
    assert any(item.property("visible") is True for item in popup_bodies)
    delegate_cuts = _find_quick_items(
        window, "prismComboBoxDohnaDelegateCut"
    )
    assert delegate_cuts
    assert any(
        item.property("visible") is True
        and item.property("x") >= 4
        and item.property("x") + item.property("width") <= skin_selector.width() - 13
        and item.property("height") > 0
        for item in delegate_cuts
    )
    QTest.keyClick(window, Qt.Key.Key_Escape)
    app.processEvents()

    controller.setPage("CAPTURE")
    app.processEvents()
    assert window.property("pageContentReady") is True
    assert window.property("pageTransitioning") is True
    capture_panels = [
        window.findChild(QObject, "capturePrimaryPanel"),
        window.findChild(QObject, "captureSecondaryPanel"),
    ]
    assert all(panel is not None for panel in capture_panels)
    visible_capture_panels = [panel for panel in capture_panels if panel.isVisible()]
    assert visible_capture_panels

    def find_visible_text(item: QQuickItem) -> QQuickItem | None:
        pending = list(item.childItems())
        while pending:
            candidate = pending.pop()
            if candidate.isVisible() and candidate.metaObject().indexOfProperty("text") >= 0:
                value = candidate.property("text")
                if isinstance(value, str) and value:
                    return candidate
            pending.extend(candidate.childItems())
        return None

    capture_text = find_visible_text(visible_capture_panels[0])
    assert capture_text is not None

    def opacity_chain(item: QQuickItem) -> list[QQuickItem]:
        chain = []
        current = item
        while current is not None:
            chain.append(current)
            if current is page_content:
                break
            current = current.parentItem()
        assert chain[-1] is page_content
        return chain

    capture_chains = [
        opacity_chain(panel) for panel in visible_capture_panels
    ] + [opacity_chain(capture_text)]

    def assert_opaque_capture_tree() -> None:
        for chain in capture_chains:
            for item in chain:
                assert float(item.property("opacity")) == pytest.approx(1.0), (
                    item.objectName(),
                    float(item.property("opacity")),
                )

    assert_opaque_capture_tree()
    assert float(page_content.property("opacity")) == 1
    assert float(page_header.property("opacity")) == 1
    assert float(page_title.property("opacity")) == 1
    assert float(content_translate.property("x")) > 40
    sampled_content_x = []
    sample_deadline = time.monotonic() + 1.2
    while window.property("pageTransitioning"):
        app.processEvents()
        assert_opaque_capture_tree()
        sampled_content_x.append(float(content_translate.property("x")))
        if time.monotonic() >= sample_deadline:
            raise AssertionError("Dohna page transition did not settle")
        QTest.qWait(40)
    assert len(sampled_content_x) >= 3
    assert sampled_content_x[0] > 0
    assert sampled_content_x[-1] == pytest.approx(0.0)
    assert_opaque_capture_tree()
    assert float(content_translate.property("x")) == pytest.approx(0.0)
    QTest.qWait(
        int(theme.property("dohnaTitleDelay"))
        + int(theme.property("dohnaTitleMotion"))
        + 80
    )
    app.processEvents()
    assert window.property("pageTransitioning") is False
    assert float(page_content.property("opacity")) == 1
    assert float(page_header.property("opacity")) == 1
    assert float(page_title.property("opacity")) == 1

    # The selected navigation face and ordinary action face are both slanted;
    # pressing an ordinary real button gives a local offset without rotating
    # its text hit target.
    nav_cut = nav_button.findChild(QObject, "prismNavigationCut")
    assert nav_cut is not None
    assert nav_cut.property("visible") is True
    nav_path = nav_cut.findChild(QObject, "prismNavigationDohnaPath")
    assert nav_path.property("strokeWidth") == 0
    assert QColor(nav_path.property("fillColor")) == QColor(theme.property("violet"))
    assert nav_button.findChild(QObject, "prismButtonDohnaShadow").property("visible") is False

    # Keyboard focus uses the same flat highlight as hovering, without a frame.
    other_nav = _find_quick_item(window, "navigationButton2")
    other_nav.forceActiveFocus()
    app.processEvents()
    other_path = other_nav.findChild(QObject, "prismNavigationDohnaPath")
    assert other_path.property("strokeWidth") == 0
    assert QColor(other_path.property("fillColor")) == QColor(theme.property("violet"))
    button_center = save_button.mapToScene(
        QPointF(save_button.width() / 2, save_button.height() / 2)
    ).toPoint()
    QTest.mouseMove(window, button_center)
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=button_center)
    app.processEvents()
    assert save_button.property("down") is True
    assert save_button.findChild(QObject, "prismButtonDohnaFocusSlash") is None
    assert float(save_button.property("dohnaImpact")) >= 0
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=button_center)
    QTest.qWait(int(theme.property("popPressMotion")) + 50)
    app.processEvents()
    assert float(save_button.property("dohnaImpact")) == 0

    # Save and error signals use the real controller boundary and each create
    # one short visual pulse.
    controller.setPage("SETTINGS")
    QTest.qWait(int(theme.property("popPageMotion")) + 40)
    app.processEvents()
    _click_quick_item(window, "saveAllButton")
    assert feedback.property("actionPulseRunning") is True
    action_sequence = int(feedback.property("actionSequence"))
    QTest.qWait(int(theme.property("popActionMotion")) + 60)
    app.processEvents()
    assert feedback.property("actionPulseRunning") is False
    assert int(feedback.property("actionSequence")) == action_sequence

    controller.reportHostError("测试错误", "反馈动画")
    app.processEvents()
    assert feedback.property("warningPulseRunning") is True
    error_dialog = window.findChild(QObject, "errorDialog")
    assert error_dialog is not None
    _click_quick_item(window, "errorDialogAcceptButton")
    QTest.qWait(int(theme.property("popWarningMotion")) + 60)
    app.processEvents()
    assert feedback.property("warningPulseRunning") is False

    # Reduced motion and hiding the window immediately stop every Dohna pulse.
    assert QMetaObject.invokeMethod(feedback, "pulseStart") is True
    app.processEvents()
    assert feedback.property("startPulseRunning") is True
    controller.setReducedMotion(True)
    app.processEvents()
    assert feedback.property("reducedMotion") is True
    assert feedback.property("startPulseRunning") is False
    controller.setReducedMotion(False)
    controller.setPage("HOME")
    app.processEvents()
    assert QMetaObject.invokeMethod(feedback, "pulseStart") is True
    window.hide()
    app.processEvents()
    assert feedback.property("motionEnabled") is False
    assert feedback.property("startPulseRunning") is False
    window.show()
    app.processEvents()

    controller.setPage("OCR")
    app.processEvents()
    assert window.property("pageTransitioning") is True
    controller.setPage("OVERLAY")
    app.processEvents()
    assert window.property("pageTransitioning") is True
    assert float(content_translate.property("x")) > 0
    assert float(page_content.property("opacity")) == 1
    assert float(page_header.property("opacity")) == 1
    QTest.qWait(
        int(theme.property("dohnaTitleDelay"))
        + int(theme.property("dohnaTitleMotion"))
        + 80
    )
    app.processEvents()
    assert window.property("pageTransitioning") is False
    assert float(content_translate.property("x")) == 0
    assert float(page_content.property("opacity")) == 1
    assert float(page_header.property("opacity")) == 1
    controller.setSkin(SKIN_PRISM)
    app.processEvents()
    assert stage.property("motionEnabled") is True
    assert sweep.property("visible") is True
    assert feedback.property("visible") is False
    assert window.property("pageTransitioning") is False
    assert window.property("pageContentReady") is True
    host.shutdown()


def test_real_prism_dialogs_follow_dark_and_light_themes_and_keep_actions(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setTheme("dark")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    theme = window.findChild(QObject, "prismTheme")
    create_dialog = window.findChild(QObject, "createProfileDialog")
    delete_dialog = window.findChild(QObject, "deleteModelDialog")
    error_dialog = window.findChild(QObject, "errorDialog")
    profile_name = window.findChild(QObject, "createProfileNameField")
    assert theme is not None
    assert create_dialog is not None
    assert delete_dialog is not None
    assert error_dialog is not None
    assert profile_name is not None

    rejected_events: list[bool] = []
    create_dialog.rejected.connect(lambda: rejected_events.append(True))
    _open_dialog(create_dialog)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    app.processEvents()
    assert create_dialog.property("visible") is False
    assert rejected_events == [True]
    assert controller.hasProfile is False

    _open_dialog(create_dialog)
    _assert_prism_dialog_palette(
        window,
        theme,
        "createProfileDialog",
        dark=True,
    )
    _click_quick_item(window, "createProfileDialogRejectButton")
    assert create_dialog.property("visible") is False
    assert controller.hasProfile is False

    _open_dialog(create_dialog)
    profile_name.setProperty("text", "弹窗动作测试")
    app.processEvents()
    _click_quick_item(window, "createProfileDialogAcceptButton")
    assert create_dialog.property("visible") is False
    assert controller.hasProfile is True
    assert controller.currentProfileName == "弹窗动作测试"

    _open_dialog(delete_dialog)
    _assert_prism_dialog_palette(
        window,
        theme,
        "deleteModelDialog",
        dark=True,
    )
    _click_quick_item(window, "deleteModelDialogRejectButton")
    assert delete_dialog.property("visible") is False
    assert error_dialog.property("visible") is False

    _open_dialog(delete_dialog)
    _click_quick_item(window, "deleteModelDialogAcceptButton")
    assert delete_dialog.property("visible") is False
    assert error_dialog.property("visible") is True
    assert "当前模型没有可删除的本地文件" in error_dialog.property(
        "errorMessage"
    )
    _assert_prism_dialog_palette(
        window,
        theme,
        "errorDialog",
        dark=True,
    )
    _click_quick_item(window, "errorDialogAcceptButton")
    assert error_dialog.property("visible") is False

    controller.setTheme("light")
    app.processEvents()
    assert theme.property("dark") is False
    for dialog, surface_name, close_button in (
        (create_dialog, "createProfileDialog", "createProfileDialogRejectButton"),
        (delete_dialog, "deleteModelDialog", "deleteModelDialogRejectButton"),
    ):
        _open_dialog(dialog)
        _assert_prism_dialog_palette(
            window,
            theme,
            surface_name,
            dark=False,
        )
        _click_quick_item(window, close_button)

    controller.reportHostError("浅色错误", "浅色主题仍使用 Prism 弹窗")
    app.processEvents()
    assert error_dialog.property("visible") is True
    _assert_prism_dialog_palette(
        window,
        theme,
        "errorDialog",
        dark=False,
    )
    _click_quick_item(window, "errorDialogAcceptButton")
    host.shutdown()


def test_real_number_steppers_stay_compact_in_wide_panels(tmp_path: Path) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    window = host.window
    assert window is not None
    window.resize(1600, 900)
    app.processEvents()
    settings_panel = _find_quick_item(window, "settingsPrimaryPanel")
    assert settings_panel is not None
    assert window.width() == 1600

    for page in ("CAPTURE", "TRANSLATION", "SETTINGS"):
        controller.setPage(page)
        app.processEvents()
    _wait_for_page_layout(window, settings_panel, app)

    steppers = [
        item
        for item in window.findChildren(QObject)
        if item.metaObject().indexOfProperty("compactWidth") >= 0
    ]
    assert len(steppers) == 12
    assert float(settings_panel.property("width")) > 600
    assert float(settings_panel.property("width")) > 3 * max(
        float(stepper.property("compactWidth")) for stepper in steppers
    )
    for stepper in steppers:
        width = float(stepper.property("width"))
        compact_width = float(stepper.property("compactWidth"))
        if str(stepper.property("settingKey")).startswith("capture-"):
            assert stepper.property("compact") is True
            assert compact_width == 144
        else:
            assert stepper.property("compact") is False
            assert compact_width in {176.0, 200.0}
        assert width == compact_width

    window.resize(980, 700)
    controller.setReducedMotion(True)
    window.update()
    QTest.qWait(20)
    app.processEvents()
    page_expectations = (
        ("CAPTURE", "captureSecondaryPanel", 4),
        ("TRANSLATION", "translationSecondaryPanel", 2),
        ("SETTINGS", "settingsPrimaryPanel", 6),
    )

    def scroll_stepper_into_view(panel: QQuickItem, stepper: QQuickItem) -> None:
        ancestor = stepper.parentItem()
        flickable = None
        while ancestor is not None and ancestor is not panel:
            if (
                ancestor.metaObject().indexOfProperty("contentY") >= 0
                and ancestor.metaObject().indexOfProperty("contentHeight") >= 0
            ):
                flickable = ancestor
                break
            ancestor = ancestor.parentItem()
        if flickable is None:
            return
        stepper_in_view = stepper.mapToItem(flickable, QPointF(0, 0))
        target_content_y = float(flickable.property("contentY"))
        if stepper_in_view.y() < 0:
            target_content_y += stepper_in_view.y()
        elif (
            stepper_in_view.y() + float(stepper.property("height"))
            > flickable.property("height")
        ):
            target_content_y += (
                stepper_in_view.y()
                + float(stepper.property("height"))
                - float(flickable.property("height"))
            )
        maximum_content_y = max(
            0.0,
            float(flickable.property("contentHeight"))
            - float(flickable.property("height")),
        )
        flickable.setProperty(
            "contentY",
            max(0.0, min(maximum_content_y, target_content_y)),
        )
        app.processEvents()

    def assert_stepper_geometry(panel: QQuickItem, stepper: QQuickItem) -> None:
        scroll_stepper_into_view(panel, stepper)
        panel_origin = panel.mapToScene(QPointF(0, 0))
        panel_right = panel_origin.x() + float(panel.property("width"))
        panel_bottom = panel_origin.y() + float(panel.property("height"))
        stepper_origin = stepper.mapToScene(QPointF(0, 0))
        stepper_right = stepper_origin.x() + float(stepper.property("width"))
        stepper_bottom = stepper_origin.y() + float(stepper.property("height"))
        assert stepper_origin.x() >= panel_origin.x() - 0.5
        assert stepper_origin.y() >= panel_origin.y() - 0.5
        assert stepper_right <= panel_right + 0.5
        assert stepper_bottom <= panel_bottom + 0.5

        decrease = stepper.findChild(QObject, "numberStepperDecrease")
        editor = stepper.findChild(QObject, "numberStepperEditor")
        suffix = stepper.findChild(QObject, "numberStepperSuffix")
        increase = stepper.findChild(QObject, "numberStepperIncrease")
        assert decrease is not None
        assert editor is not None
        assert suffix is not None
        assert increase is not None
        ordered_children = [decrease, editor, increase]
        child_rects = []
        for child in ordered_children:
            child_origin = child.mapToItem(stepper, QPointF(0, 0))
            child_rect = (
                child_origin.x(),
                child_origin.y(),
                float(child.property("width")),
                float(child.property("height")),
            )
            child_rects.append(child_rect)
            assert child_rect[0] >= -0.5
            assert child_rect[1] >= -0.5
            assert child_rect[0] + child_rect[2] <= stepper.property("width") + 0.5
            assert child_rect[1] + child_rect[3] <= stepper.property("height") + 0.5
        for left_rect, right_rect in zip(child_rects, child_rects[1:]):
            assert left_rect[0] + left_rect[2] <= right_rect[0] + 0.5

        decrease_rect, editor_rect, increase_rect = child_rects
        assert abs(decrease_rect[2] - increase_rect[2]) <= 0.5
        left_gap = editor_rect[0] - (decrease_rect[0] + decrease_rect[2])
        right_gap = increase_rect[0] - (editor_rect[0] + editor_rect[2])
        assert abs(left_gap - right_gap) <= 0.5
        assert abs(
            decrease_rect[0]
            - (stepper.property("width") - increase_rect[0] - increase_rect[2])
        ) <= 0.5

        if stepper.property("suffix") and not stepper.property("compact"):
            assert suffix.property("visible") is True
            assert suffix.parentItem() == editor
            suffix_origin = suffix.mapToItem(editor, QPointF(0, 0))
            assert suffix_origin.x() >= -0.5
            assert suffix_origin.y() >= -0.5
            assert (
                suffix_origin.x() + float(suffix.property("width"))
                <= editor.property("width") + 0.5
            )
            assert (
                suffix_origin.y() + float(suffix.property("height"))
                <= editor.property("height") + 0.5
            )

    for page, panel_name, expected_count in page_expectations:
        controller.setPage(page)
        window.update()
        QTest.qWait(20)
        app.processEvents()
        panel = _find_quick_item(window, panel_name)
        assert panel is not None
        page_steppers = [
            item
            for item in panel.findChildren(QObject)
            if item.metaObject().indexOfProperty("compactWidth") >= 0
        ]
        assert len(page_steppers) == expected_count
        expected_names = {
            str(stepper.property("accessibleName")) for stepper in page_steppers
        }
        assert len(expected_names) == expected_count
        checked_names = set()
        visibility_states = (
            ("external", "builtin")
            if page == "TRANSLATION"
            else (True, False) if page == "SETTINGS" else (None,)
        )
        for state in visibility_states:
            if page == "TRANSLATION":
                controller.setBackend(state)
            elif page == "SETTINGS":
                controller.setDynamicRoiEnabled(state)
            window.update()
            QTest.qWait(20)
            app.processEvents()
            for stepper in page_steppers:
                if stepper.property("visible") is not True:
                    continue
                assert_stepper_geometry(panel, stepper)
                checked_names.add(str(stepper.property("accessibleName")))
        assert checked_names == expected_names
    host.shutdown()


@pytest.mark.parametrize("window_size", [(980, 700), (1280, 820)])
def test_real_dohna_slanted_menu_and_parallel_buttons_keep_hit_targets(
    tmp_path: Path, window_size: tuple[int, int],
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(config_path, load_config(config_path), "game", display_name="测试游戏")
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_DOHNA)
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    try:
        window = host.window
        assert window is not None
        window.resize(*window_size)
        host.show()
        QTest.qWait(80)
        theme = window.findChild(QObject, "prismTheme")
        pages = ("HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS")
        menu_edges = []
        for index, page in enumerate(pages):
            button = _find_quick_item(window, f"navigationButton{index}")
            assert button is not None
            label = button.findChild(QQuickItem, "prismButtonLabel")
            text = label.property("text")
            assert page in text and re.search(r"[\u4e00-\u9fff]", text)
            assert "\n" not in text
            assert label.property("lineCount") == 1
            assert label.property("truncated") is False, text
            available_text_width = label.width() - label.property("leftPadding") - label.property("rightPadding")
            assert label.property("contentWidth") <= available_text_width + 1
            fitted_font = label.property("font")
            fitted_font.setPixelSize(label.property("fontInfo").property("pixelSize").toInt())
            glyph_bounds = QFontMetricsF(fitted_font).tightBoundingRect(text)
            # Measure visible glyphs, not the font's extra line spacing.  The
            # thin strips must not vertically shrink their existing lettering.
            assert 0.79 <= glyph_bounds.height() / button.height() <= 0.86
            assert fitted_font.pixelSize() >= 10
            assert button.height() < 20
            baseline = label.y() + label.property("baselineOffset")
            assert baseline + glyph_bounds.top() >= -1
            assert baseline + glyph_bounds.bottom() <= button.height() + 1
            label_left = label.mapToScene(QPointF(0, 0))
            label_right = label.mapToScene(QPointF(label.width(), 0))
            assert label_right.y() > label_left.y() + 10
            rail = button.parentItem().parentItem()
            assert rail.property("clip") is True
            rail_left = rail.mapToScene(QPointF(0, 0)).x()
            rail_right = rail_left + rail.width()
            middle_x = (rail_left + rail_right) / 2
            slope = math.tan(math.radians(button.property("rotation")))
            top = button.mapToScene(QPointF(0, 0))
            bottom = button.mapToScene(QPointF(0, button.height()))
            menu_edges.append((top.y() + (middle_x - top.x()) * slope,
                               bottom.y() + (middle_x - bottom.x()) * slope))
            # Both sloping edges span past the sidebar, so clipping leaves
            # straight, flush ends rather than exposed corners or side gaps.
            for y in (0, button.height()):
                left = button.mapToScene(QPointF(0, y))
                right = button.mapToScene(QPointF(button.width(), y))
                assert left.x() < rail_left
                assert right.x() > rail_right
                assert 0 <= left.y() <= window.height()
                assert 0 <= right.y() <= window.height()
            # The extended strips respond even at the visible sidebar edges.
            start = button.mapToScene(QPointF(0, button.height() / 2))
            end = button.mapToScene(QPointF(button.width(), button.height() / 2))
            for x in (rail_left + 1, rail_right - 1):
                y = start.y() + (x - start.x()) * (end.y() - start.y()) / (end.x() - start.x())
                point = QPointF(x, y)
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point.toPoint())
                app.processEvents()
                assert controller.currentPage == page
            path = button.findChild(QObject, "prismNavigationDohnaPath")
            assert path.property("strokeWidth") == 0
            assert QColor(path.property("fillColor")) == QColor(theme.property("violet"))
            assert QColor(label.property("color")) == QColor(theme.property("ink"))

        # Preserve the actual space between slanted edges, including layout
        # rounding, rather than retaining only the unrotated layout spacing.
        gaps = [current[0] - previous[1] for previous, current in zip(menu_edges, menu_edges[1:])]
        original_gap = 60 - 50 / math.cos(math.radians(12))
        assert all(abs(gap - original_gap) <= 0.5 for gap in gaps)

        capture_button = _find_quick_item(window, "navigationButton1")
        capture_button.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_Space)
        app.processEvents()
        assert controller.currentPage == "CAPTURE"

        def assert_parallel_sides(path: QObject) -> list[tuple[float, float]]:
            assert path is not None
            top_left = (float(path.property("startX")), float(path.property("startY")))
            points = [
                (float(line.property("x")), float(line.property("y")))
                for line in path.children()
                if line.metaObject().className().startswith("QQuickPathLine")
            ]
            assert len(points) == 4
            top_right, bottom_right, bottom_left, close = points
            assert close == pytest.approx(top_left)
            assert bottom_left[0] > top_left[0]
            assert bottom_right[0] - top_right[0] == pytest.approx(bottom_left[0] - top_left[0])
            assert bottom_right[1] - top_right[1] == pytest.approx(bottom_left[1] - top_left[1])
            assert top_right[0] - top_left[0] == pytest.approx(bottom_right[0] - bottom_left[0])
            return points

        for name in ("saveAllButton", "startLiveButton", "captureScanAction", "captureCustomAction"):
            button = window.findChild(QQuickItem, name)
            assert button is not None
            assert button.property("rotation") == 0
            face = assert_parallel_sides(button.findChild(QObject, "prismButtonDohnaPath"))
            shadow = assert_parallel_sides(button.findChild(QObject, "prismButtonDohnaShadowPath"))
            assert face == shadow

        panel = window.findChild(QObject, "captureSecondaryPanel")
        for path in panel.findChildren(QObject, "prismButtonDohnaGroupPath"):
            assert_parallel_sides(path)
        for path in panel.findChildren(QObject, "prismButtonDohnaGroupShadowPath"):
            assert_parallel_sides(path)

        controller.setSkin(SKIN_PRISM)
        app.processEvents()
        assert rail.property("clip") is False
        assert all(_find_quick_item(window, f"navigationButton{i}").property("rotation") == 0
                   for i in range(len(pages)))
        assert all(_find_quick_item(window, f"navigationButton{i}").height() == 42
                   for i in range(len(pages)))
    finally:
        host.shutdown()


def test_real_dohna_number_stepper_uses_one_frame_at_bounds_and_input(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(SKIN_DOHNA)
    controller.setReducedMotion(True)
    controller.setCaptureRegion(10, 20, 640, 180)
    controller.setPage("CAPTURE")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    theme = window.findChild(QObject, "prismTheme")
    capture_panel = _find_quick_item(window, "captureSecondaryPanel")
    assert capture_panel is not None
    assert theme is not None
    _wait_for_page_layout(window, capture_panel, app)
    stepper = next(
        item
        for item in capture_panel.findChildren(QObject)
        if item.metaObject().indexOfProperty("compactWidth") >= 0
        and item.property("settingKey") == "capture-left"
    )
    assert stepper is not None
    decrease = stepper.findChild(QObject, "numberStepperDecrease")
    increase = stepper.findChild(QObject, "numberStepperIncrease")
    editor = stepper.findChild(QObject, "numberStepperEditor")
    suffix = stepper.findChild(QObject, "numberStepperSuffix")
    group_surface = stepper.findChild(QObject, "prismButtonDohnaGroupSurface")
    group_shadow = stepper.findChild(QObject, "prismButtonDohnaGroupShadow")
    group_cut = stepper.findChild(QObject, "prismButtonDohnaCut")
    assert decrease is not None
    assert increase is not None
    assert editor is not None
    assert suffix is not None
    assert group_surface is not None
    assert group_shadow is not None
    assert group_cut is not None
    assert stepper.property("compact") is True
    assert stepper.property("width") == 144
    assert suffix.property("visible") is False
    assert group_surface.property("visible") is True
    assert group_shadow.property("visible") is True
    assert group_surface.property("width") == stepper.property("width")
    assert group_surface.property("height") == stepper.property("height")
    assert group_cut.property("visible") is False
    group_path = group_surface.findChild(QObject, "prismButtonDohnaGroupPath")
    assert group_path is not None
    increase.forceActiveFocus()
    app.processEvents()
    assert increase.property("activeFocus") is True
    assert QColor(group_path.property("fillColor")) == QColor(theme.property("violet"))

    controller.setCaptureRegion(0, 20, 640, 180)
    app.processEvents()
    assert stepper.property("value") == 0
    assert decrease.property("enabled") is False
    assert group_surface.property("visible") is True

    editor.forceActiveFocus()
    editor.setProperty("text", "32768")
    QTest.keyClick(window, Qt.Key.Key_Return)
    app.processEvents()
    assert controller.captureLeft == 32768
    assert stepper.property("value") == 32768
    assert increase.property("enabled") is False
    assert group_surface.property("visible") is True

    maximum_point = increase.mapToScene(
        QPointF(increase.width() / 2, increase.height() / 2)
    ).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=maximum_point)
    app.processEvents()
    assert controller.captureLeft == 32768

    controller.setPage("SETTINGS")
    app.processEvents()
    normal_stepper = window.findChild(QObject, "settingsCalibrationStepper")
    assert normal_stepper is not None
    assert normal_stepper.property("compact") is False
    assert normal_stepper.property("width") == 200
    normal_suffix = normal_stepper.findChild(QObject, "numberStepperSuffix")
    normal_surface = normal_stepper.findChild(
        QObject,
        "prismButtonDohnaGroupSurface",
    )
    assert normal_suffix is not None
    assert normal_suffix.property("visible") is True
    assert normal_surface is not None
    assert normal_surface.property("visible") is True

    controller.useFullScreen()
    controller.setPage("CAPTURE")
    app.processEvents()
    assert stepper.property("enabled") is False
    assert group_surface.property("visible") is True
    assert float(group_surface.property("opacity")) < 1
    host.shutdown()


@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize("window_size", [(980, 700), (1280, 820), (1600, 900)])
def test_capture_fields_use_two_rows_and_keep_geometry_clear(
    tmp_path: Path,
    theme_name: str,
    window_size: tuple[int, int],
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setTheme(theme_name)
    controller.setReducedMotion(True)
    controller.setCaptureRegion(30, 40, 640, 180)
    controller.setPage("CAPTURE")
    host = QmlWorkbenchHost(controller, application=app)
    try:
        host.show()
        window = host.window
        assert window is not None
        window.resize(*window_size)
        panel = _find_quick_item(window, "captureSecondaryPanel")
        assert panel is not None
        _wait_for_page_layout(window, panel, app)
        steppers = {
            str(item.property("settingKey")): item
            for item in panel.findChildren(QQuickItem)
            if item.metaObject().indexOfProperty("compactWidth") >= 0
        }
        assert set(steppers) == {
            "capture-left", "capture-top", "capture-width", "capture-height",
        }
        origins = {
            key: stepper.mapToScene(QPointF(0, 0))
            for key, stepper in steppers.items()
        }
        left = origins["capture-left"]
        top = origins["capture-top"]
        width = origins["capture-width"]
        height = origins["capture-height"]
        assert math.isclose(left.y(), top.y(), abs_tol=0.5)
        assert math.isclose(width.y(), height.y(), abs_tol=0.5)
        assert math.isclose(left.x(), width.x(), abs_tol=0.5)
        assert math.isclose(top.x(), height.x(), abs_tol=0.5)
        assert left.x() + steppers["capture-left"].width() < top.x()
        assert left.y() + steppers["capture-left"].height() < width.y()

        panel_origin = panel.mapToScene(QPointF(0, 0))
        for key, stepper in steppers.items():
            origin = origins[key]
            assert stepper.width() == 144
            assert origin.x() >= panel_origin.x()
            assert origin.y() >= panel_origin.y()
            assert origin.x() + stepper.width() <= panel_origin.x() + panel.width()
            assert origin.y() + stepper.height() <= panel_origin.y() + panel.height()
            editor = stepper.findChild(QQuickItem, "numberStepperEditor")
            suffix = stepper.findChild(QQuickItem, "numberStepperSuffix")
            assert editor is not None
            assert suffix is not None
            editor.forceActiveFocus()
            editor.setProperty("text", "32768")
            app.processEvents()
            assert (
                float(editor.property("contentWidth"))
                + float(editor.property("leftPadding"))
                + float(editor.property("rightPadding"))
                <= editor.width()
            )
            assert suffix.property("visible") is False
            editor.setProperty("text", str(stepper.property("value")))

        # Click each narrow button and verify it still edits the correct field.
        controller.setCaptureRegion(30, 40, 640, 180)
        app.processEvents()
        for stepper in steppers.values():
            original = int(stepper.property("value"))
            for button_name, expected in (
                ("numberStepperIncrease", original + 10),
                ("numberStepperDecrease", original),
            ):
                button = stepper.findChild(QQuickItem, button_name)
                assert button is not None
                point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point.toPoint())
                app.processEvents()
                assert stepper.property("value") == expected

        theme = window.findChild(QObject, "prismTheme")
        surface = _find_quick_item(window, "captureGeometrySurface")
        outline = _find_quick_item(window, "captureDisplayOutline")
        preview = _find_quick_item(window, "captureRegionPreview")
        stage = _find_quick_item(window, "opticalStage")
        assert all(item is not None for item in (theme, surface, outline, preview, stage))
        assert surface.property("color") == theme.property("panel")
        assert surface.property("color").alphaF() == 1
        assert QQmlProperty(outline, "border.color").read() == theme.property("line")
        assert QQmlProperty(preview, "border.color").read() == theme.property("accent")
        assert QQmlProperty(preview, "border.width").read() == 2
        assert preview.property("visible") is True
        assert 0 < float(stage.property("opacity")) < 0.2

        controller.useFullScreen()
        app.processEvents()
        assert preview.property("visible") is False
        assert all(stepper.property("enabled") is False for stepper in steppers.values())
        controller.setPage("HOME")
        app.processEvents()
        assert stage.property("opacity") == theme.property("opticalStageOpacity")
    finally:
        host.shutdown()


def test_capture_geometry_projects_bottom_right_region_against_full_display(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    display_width = controller.captureDisplayWidth
    display_height = controller.captureDisplayHeight
    assert display_width > 0
    assert display_height > 0
    region_width = max(1, display_width // 5)
    region_height = max(1, display_height // 5)
    controller.setCaptureRegion(
        display_width - region_width,
        display_height - region_height,
        region_width,
        region_height,
    )
    controller.setPage("CAPTURE")

    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    window = host.window
    assert window is not None
    window.update()
    QTest.qWait(20)
    app.processEvents()

    stage = _find_quick_item(window, "captureGeometryStage")
    preview = _find_quick_item(window, "captureRegionPreview")
    assert stage is not None
    assert preview is not None
    assert preview.property("visible") is True
    stage_width = float(stage.property("width"))
    stage_height = float(stage.property("height"))
    preview_x = float(preview.property("x"))
    preview_y = float(preview.property("y"))
    preview_width = float(preview.property("width"))
    preview_height = float(preview.property("height"))

    assert math.isclose(preview_width, stage_width / 5, abs_tol=0.5)
    assert math.isclose(preview_height, stage_height / 5, abs_tol=0.5)
    assert math.isclose(preview_x + preview_width, stage_width, abs_tol=0.5)
    assert math.isclose(preview_y + preview_height, stage_height, abs_tol=0.5)
    assert preview_x > stage_width * 0.75
    assert preview_y > stage_height * 0.75
    host.shutdown()


def test_real_overlay_slider_updates_draft_and_profile_apply_persists_it(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\n[preview]\noverlay_opacity = 0.375\n",
        encoding="utf-8",
    )
    profile = create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    save_snapshot(
        profile.directory,
        new_snapshot(
            (
                SnapshotEntry(
                    "overlay-preview",
                    0,
                    "原文",
                    "示例译文",
                    0.9,
                    (100, 120, 500, 220),
                ),
            ),
            (),
            ocr_peak_seconds=None,
            llm_peak_seconds=None,
            canvas_size=(800, 600),
        ),
    )
    configured = load_config(config_path).preview.overlay_opacity
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setPage("OVERLAY")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    window.update()
    QTest.qWait(20)
    app.processEvents()
    slider = _find_quick_item(window, "overlayProjectionAction")
    percentage = window.findChild(QObject, "overlayOpacityValue")
    preview_entry = _find_quick_item(window, "overlayLastRunEntry")
    assert slider is not None
    assert percentage is not None
    assert preview_entry is not None
    assert _find_quick_item(window, "overlayCanvasMask") is None
    assert float(slider.property("from")) == 0.0
    assert float(slider.property("to")) == 1.0
    assert float(slider.property("stepSize")) == 0.01
    assert float(slider.property("value")) == configured
    assert percentage.property("text") == f"{round(configured * 100)}%"
    assert float(preview_entry.property("maskOpacity")) == configured
    assert controller.settingsDirty is False

    stage = window.findChild(QObject, "opticalStage")
    overlay_motif = window.findChild(QObject, "overlayStageMotif")
    overlay_near_plane = window.findChild(QObject, "overlayStageNearPlane")
    assert stage is not None
    assert overlay_motif is not None
    assert overlay_near_plane is not None
    resting_plane_x = float(overlay_near_plane.property("x"))
    action_sequence = int(stage.property("actionSequence"))
    start_ratio = float(slider.property("visualPosition"))
    start = _slider_scene_point(slider, start_ratio)
    end_ratio = 0.73
    end = _slider_scene_point(slider, end_ratio)
    QTest.mousePress(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        start,
    )
    assert int(stage.property("actionSequence")) == action_sequence

    draft_samples = []
    for progress in (0.25, 0.5, 0.75, 1.0):
        position = _slider_scene_point(
            slider,
            start_ratio + (end_ratio - start_ratio) * progress,
        )
        QTest.mouseMove(window, position, delay=10)
        app.processEvents()
        draft_samples.append(controller.overlayOpacity)
        assert float(preview_entry.property("maskOpacity")) == controller.overlayOpacity
        assert int(stage.property("actionSequence")) == action_sequence

    assert draft_samples == sorted(draft_samples)
    assert len(set(draft_samples)) == len(draft_samples)
    QTest.mouseRelease(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        end,
    )
    app.processEvents()
    assert int(stage.property("actionSequence")) == action_sequence + 1
    QTest.qWait(160)
    app.processEvents()
    assert overlay_motif.property("actionLinked") is True
    assert float(overlay_near_plane.property("x")) > resting_plane_x + 1

    draft = controller.overlayOpacity
    assert draft > configured
    assert float(slider.property("from")) <= draft <= float(slider.property("to"))
    assert float(slider.property("value")) == draft
    assert percentage.property("text") == f"{round(draft * 100)}%"
    assert controller.settingsDirty is True
    assert load_config(config_path).preview.overlay_opacity == configured
    assert stage.property("actionKind") == "projection"

    controller.setOverlayOpacity(0.23)
    app.processEvents()
    draft = controller.overlayOpacity
    assert draft == 0.23
    assert float(slider.property("value")) == 0.23
    assert percentage.property("text") == "23%"
    assert float(preview_entry.property("maskOpacity")) == 0.23
    assert int(stage.property("actionSequence")) == action_sequence + 1

    _click_quick_item(window, "saveAllButton")
    assert controller.settingsDirty is False
    machine = load_config(config_path)
    saved_profile = load_game_profile(config_path, machine, "game")
    assert machine.preview.overlay_opacity == configured
    assert apply_profile_runtime_settings(
        machine,
        saved_profile,
    ).preview.overlay_opacity == draft
    QTest.qWait(600)
    app.processEvents()
    assert overlay_motif.property("actionLinked") is False
    assert math.isclose(
        float(overlay_near_plane.property("x")),
        resting_plane_x,
        abs_tol=0.01,
    )
    host.shutdown()


def test_real_ocr_quality_slider_snaps_three_presets_and_keeps_merge_guard(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setPage("OCR")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    slider = _find_quick_item(window, "ocrQualitySlider")
    assert slider is not None
    assert float(slider.property("from")) == 0.0
    assert float(slider.property("to")) == 2.0
    assert float(slider.property("stepSize")) == 1.0
    initial_index = controller.detectionQualityIndex
    assert initial_index in (0, 1, 2)

    start = _slider_scene_point(slider, initial_index / 2)
    quality_position = _slider_scene_point(slider, 0.76)
    QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(window, quality_position, delay=10)
    app.processEvents()
    QTest.mouseRelease(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        quality_position,
    )
    app.processEvents()

    assert controller.detectionQualityIndex == 2
    assert float(slider.property("value")) == 2.0
    assert controller.detectionQualitySummary.startswith("质量 · ")
    assert controller.settingsDirty is True

    low_position = _slider_scene_point(slider, 0.1)
    QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, quality_position)
    QTest.mouseMove(window, low_position, delay=10)
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, low_position)
    app.processEvents()
    assert controller.detectionQualityIndex == 0
    assert controller.textMergeAllowed is False
    host.shutdown()


@pytest.mark.parametrize("skin", [SKIN_PRISM, SKIN_DOHNA])
def test_real_slider_press_feedback_uses_skin_specific_accent(
    tmp_path: Path,
    skin: str,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setSkin(skin)
    controller.setPage("OCR")
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    slider = _find_quick_item(window, "ocrQualitySlider")
    theme = window.findChild(QObject, "prismTheme")
    assert isinstance(slider, QQuickItem)
    assert theme is not None
    handle = slider.property("handle")
    assert isinstance(handle, QQuickItem)
    point = _slider_scene_point(slider, float(slider.property("visualPosition")))

    QTest.mouseMove(window, point)
    QTest.mousePress(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        point,
    )
    app.processEvents()
    assert slider.property("pressed") is True
    expected_pressed = QColor(
        theme.property("violet") if skin == SKIN_DOHNA else theme.property("accent")
    )
    assert QColor(handle.property("color")) == expected_pressed

    QTest.mouseRelease(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        point,
    )
    app.processEvents()
    assert slider.property("pressed") is False
    assert QColor(handle.property("color")) == QColor(
        theme.property("inkRaised")
    )
    host.shutdown()


def test_real_last_run_snapshot_renders_all_output_pages_in_minimum_window(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    profile = create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    save_snapshot(
        profile.directory,
        new_snapshot(
            tuple(
                SnapshotEntry(
                    f"track-{index}",
                    index,
                    f"原文 {index}",
                    "这是一段较长的上次运行译文，用于验证页面不会因为长文本而溢出。" * 2,
                    0.8,
                    (20, index * 45, 420, index * 45 + 35),
                )
                for index in range(3)
            ),
            tuple(CacheHit(f"缓存原文 {index}", 5 - index) for index in range(5)),
            ocr_peak_seconds=0.4,
            llm_peak_seconds=2.5,
            canvas_size=(800, 600),
        ),
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    qml_warnings: list[str] = []

    def create_engine(parent: QObject) -> QQmlApplicationEngine:
        engine = QQmlApplicationEngine(parent)
        engine.warnings.connect(
            lambda errors: qml_warnings.extend(error.toString() for error in errors)
        )
        return engine

    host = QmlWorkbenchHost(
        controller,
        application=app,
        engine_factory=create_engine,
    )
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    window.resize(980, 700)
    app.processEvents()
    assert window.width() >= 980
    assert window.height() >= 700

    home_scroll = _find_quick_item(window, "homePrimaryScroll")
    home_metrics_content = _find_quick_item(window, "homeLastRunMetricsContent")
    home_metrics = window.findChild(QObject, "homeLastRunMetrics")
    home_status = window.findChild(QObject, "homeLastRunStatus")
    home_peak_cards = window.findChild(QObject, "homePeakCards")
    home_footnote = window.findChild(QObject, "homeLastRunFootnote")
    home_ocr_peak_group = window.findChild(QObject, "homeOcrPeakGroup")
    home_llm_peak_group = window.findChild(QObject, "homeLlmPeakGroup")
    home_ocr_peak = window.findChild(QObject, "homeOcrPeakValue")
    home_llm_peak = window.findChild(QObject, "homeLlmPeakValue")
    assert home_scroll is not None
    assert home_metrics_content is not None
    assert home_metrics is not None
    assert home_status is not None
    assert home_peak_cards is not None
    assert home_footnote is not None
    assert home_ocr_peak_group is not None
    assert home_llm_peak_group is not None
    assert home_ocr_peak is not None
    assert home_llm_peak is not None
    assert home_metrics.property("visible") is True
    assert home_peak_cards.property("visible") is True
    assert home_ocr_peak.property("text") == "400 ms"
    assert home_llm_peak.property("text") == "2.50 s"
    assert home_ocr_peak.property("font").pixelSize() == 44
    assert home_llm_peak.property("font").pixelSize() == 44
    assert home_ocr_peak_group.property("color") is None
    assert home_llm_peak_group.property("color") is None
    assert home_ocr_peak_group.property("height") >= 142
    assert home_llm_peak_group.property("height") >= 142
    assert float(home_metrics.property("height")) >= float(
        home_metrics_content.property("implicitHeight")
    ) + 32
    for child in (home_status, home_peak_cards, home_footnote):
        child_y = child.mapToItem(home_metrics, QPointF(0, 0)).y()
        assert child_y >= -1e-3
        assert child_y + float(child.property("height")) <= float(
            home_metrics.property("height")
        ) + 1e-3
    assert float(home_scroll.property("contentHeight")) <= float(
        home_scroll.property("height")
    )
    assert float(home_scroll.property("contentY")) == 0
    footnote_y = home_footnote.mapToItem(home_scroll, QPointF(0, 0)).y()
    assert footnote_y >= -1e-3
    assert footnote_y + float(home_footnote.property("height")) <= float(
        home_scroll.property("height")
    ) + 1e-3

    controller.setPage("OCR")
    app.processEvents()
    ocr_list = window.findChild(QObject, "ocrLastRunList")
    assert ocr_list is not None
    assert ocr_list.property("visible") is True
    controller.setPage("TRANSLATION")
    app.processEvents()
    translation_list = window.findChild(QObject, "translationLastRunList")
    assert translation_list is not None
    assert translation_list.property("visible") is True
    controller.setPage("OVERLAY")
    app.processEvents()
    controller.setOverlayOpacity(0.1)
    app.processEvents()
    canvas = window.findChild(QObject, "overlayLastRunCanvas")
    canvas_item = _find_quick_item(window, "overlayLastRunCanvas")
    drawn_canvas = _find_quick_item(window, "overlayCanvas")
    assert canvas is not None
    assert canvas_item is not None
    assert drawn_canvas is not None
    assert _find_quick_item(window, "overlayCanvasMask") is None
    _wait_for_page_layout(window, canvas_item, app)
    assert float(drawn_canvas.property("width")) <= float(canvas_item.property("width"))
    assert float(drawn_canvas.property("height")) <= float(canvas_item.property("height"))
    entries = _find_quick_items(window, "overlayLastRunEntry")
    assert len(entries) == 3
    canvas_width = float(drawn_canvas.property("width"))
    canvas_height = float(drawn_canvas.property("height"))
    for entry in entries:
        for name in ("x", "y", "width", "height"):
            value = float(entry.property(name))
            assert math.isfinite(value)
        assert float(entry.property("width")) > 0
        assert float(entry.property("height")) > 0
        assert 0 <= float(entry.property("x")) <= canvas_width
        assert 0 <= float(entry.property("y")) <= canvas_height
        assert float(entry.property("x")) + float(entry.property("width")) <= canvas_width + 1e-6
        assert float(entry.property("y")) + float(entry.property("height")) <= canvas_height + 1e-6
        assert math.isclose(
            float(entry.property("maskOpacity")),
            controller.overlayOpacity,
            abs_tol=1e-6,
        )
        background = entry.property("color")
        assert background.red() == 0
        assert background.green() == 0
        assert background.blue() == 0
        assert math.isclose(
            background.alphaF(),
            controller.overlayOpacity,
            abs_tol=1 / 255,
        )
        frame_color = QQmlProperty(entry, "border.color").read()
        assert 0 < frame_color.alphaF() <= 0.25
    controller.setOverlayOpacity(0.8)
    app.processEvents()
    assert all(
        math.isclose(
            float(entry.property("maskOpacity")),
            0.8,
            abs_tol=1e-6,
        )
        for entry in entries
    )
    assert qml_warnings == []
    controller.setPage("CACHE")
    app.processEvents()
    cache_hits = window.findChild(QObject, "cacheLastRunHits")
    cache_summary = _find_quick_item(window, "cacheSummaryMetrics")
    cache_hint = _find_quick_item(window, "cacheSummarySourceHint")
    assert cache_hits is not None
    assert cache_summary is not None
    assert cache_hint is not None
    assert cache_hits.property("visible") is True
    assert cache_hint.property("text") == (
        "上方为 Profile SQLite 累计统计；上次运行命中列表仅代表最近一次运行。"
    )
    assert cache_summary.mapToItem(cache_hits, QPointF(0, 0)).y() < 0
    unavailable_titles = _find_quick_items(window, "unavailableStateTitle")
    assert any(
        title.property("text") == "暂不支持浏览自动缓存明细"
        for title in unavailable_titles
    )

    window.resize(1280, 820)
    controller.setPage("HOME")
    app.processEvents()
    assert float(home_scroll.property("contentHeight")) <= float(
        home_scroll.property("height")
    )
    host.shutdown()


@pytest.mark.parametrize("theme_name", ("dark", "light"))
def test_nearly_fitting_pages_compact_spacing_before_requiring_scroll(
    tmp_path: Path,
    theme_name: str,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    profile = create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    save_snapshot(
        profile.directory,
        new_snapshot(
            (SnapshotEntry("track", 0, "原文", "译文", 0.9, (20, 40, 420, 75)),),
            (),
            ocr_peak_seconds=0.4,
            llm_peak_seconds=2.5,
        ),
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setTheme(theme_name)
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    try:
        host.show()
        window = host.window
        assert window is not None
        home_panel = _find_quick_item(window, "homePrimaryPanel")
        home_scroll = _find_quick_item(window, "homePrimaryScroll")
        hero = _find_quick_item(window, "homeRunHero")
        footnote = _find_quick_item(window, "homeLastRunFootnote")
        assert all(item is not None for item in (home_panel, home_scroll, hero, footnote))
        for size in ((980, 700), (1100, 760), (1280, 820)):
            window.resize(*size)
            _wait_for_page_layout(window, home_panel, app)
            assert home_scroll.property("contentHeight") <= home_scroll.height()
            assert home_scroll.property("contentY") == 0
            footnote_origin = footnote.mapToItem(home_scroll, QPointF(0, 0))
            assert footnote_origin.y() + footnote.height() <= home_scroll.height()
            assert hero.property("font").pixelSize() >= 40
            for group_name in ("homeOcrSignalGroup", "homeTranslationSignalGroup"):
                group = _find_quick_item(window, group_name)
                assert group is not None
                for text in group.findChildren(QQuickItem):
                    if text.metaObject().indexOfProperty("font") < 0 or not text.isVisible():
                        continue
                    origin = text.mapToItem(group, QPointF(0, 0))
                    assert origin.y() >= 0
                    assert origin.y() + text.height() <= group.height()

        controller.setPage("OCR")
        ocr_panel = _find_quick_item(window, "ocrSecondaryPanel")
        ocr_scroll = _find_quick_item(window, "ocrSettingsScroll")
        assert ocr_panel is not None
        assert ocr_scroll is not None
        _wait_for_page_layout(window, ocr_panel, app)
        assert ocr_scroll.property("contentHeight") <= ocr_scroll.height()
        assert ocr_scroll.property("contentY") == 0
        for quality_index in range(len(controller.detectionQualityNames)):
            controller.setDetectionQualityIndex(quality_index)
            app.processEvents()
            assert ocr_scroll.property("contentHeight") <= ocr_scroll.height()
    finally:
        host.shutdown()


def test_real_overlay_snapshot_keeps_portrait_canvas_contain_fit(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    profile = create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    save_snapshot(
        profile.directory,
        new_snapshot(
            (SnapshotEntry("portrait", 0, "竖屏原文", "竖屏译文", 0.9, (20, 80, 260, 420)),),
            (),
            ocr_peak_seconds=None,
            llm_peak_seconds=None,
            canvas_size=(600, 1200),
        ),
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    controller.setPage("OVERLAY")
    app.processEvents()
    canvas_item = _find_quick_item(window, "overlayLastRunCanvas")
    drawn_canvas = _find_quick_item(window, "overlayCanvas")
    assert canvas_item is not None
    assert drawn_canvas is not None
    _wait_for_page_layout(window, canvas_item, app)
    assert float(drawn_canvas.property("width")) <= float(canvas_item.property("width"))
    assert float(drawn_canvas.property("height")) <= float(canvas_item.property("height"))
    assert float(drawn_canvas.property("height")) > float(drawn_canvas.property("width"))
    host.shutdown()


def test_page_subtitle_stays_clear_of_dividers_across_pages_themes_and_sizes(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    header = _find_quick_item(window, "pageHeaderBar")
    underline = _find_quick_item(window, "pageHeaderUnderline")
    subtitle = _find_quick_item(window, "pageSubtitle")
    assert header is not None
    assert underline is not None
    assert subtitle is not None

    pages = ("HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS")
    underline_points = (
        QPointF(0, 0),
        QPointF(float(underline.property("width")), 0),
        QPointF(0, float(underline.property("height"))),
        QPointF(
            float(underline.property("width")),
            float(underline.property("height")),
        ),
    )
    for width, height in ((980, 700), (1280, 820)):
        window.resize(width, height)
        app.processEvents()
        for theme_name in ("dark", "light"):
            controller.setTheme(theme_name)
            app.processEvents()
            for page in pages:
                controller.setPage(page)
                app.processEvents()
                subtitle_top = subtitle.mapToItem(header, QPointF(0, 0)).y()
                subtitle_bottom = subtitle_top + float(subtitle.property("height"))
                underline_bottom = max(
                    underline.mapToItem(header, point).y()
                    for point in underline_points
                )
                assert subtitle_top >= underline_bottom + 3
                assert subtitle_bottom <= float(header.property("height")) - 4

    host.shutdown()


def test_real_workbench_uses_responsive_title_stack_and_layered_page_motion(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    title = window.findChild(QObject, "pageDisplayTitle")
    title_light = window.findChild(QObject, "pageDisplayTitleLight")
    title_heavy = window.findChild(QObject, "pageDisplayTitleHeavy")
    cyan_slice = window.findChild(QObject, "pageTitleCyanSlice")
    spectrum_slice = window.findChild(QObject, "pageTitleSpectrumSlice")
    cyan_edge = window.findChild(QObject, "pageTitleCyanEdge")
    spectrum_edge = window.findChild(QObject, "pageTitleSpectrumEdge")
    header_underline = window.findChild(QObject, "pageHeaderUnderline")
    page_subtitle = window.findChild(QObject, "pageSubtitle")
    cyan_counter_rotation = window.findChild(
        QObject,
        "pageTitleCyanCounterRotation",
    )
    spectrum_counter_rotation = window.findChild(
        QObject,
        "pageTitleSpectrumCounterRotation",
    )
    header_bar = window.findChild(QObject, "pageHeaderBar")
    save_button = window.findChild(QObject, "saveAllButton")
    theme = window.findChild(QObject, "prismTheme")
    stage = window.findChild(QObject, "opticalStage")
    assert title is not None
    assert title_light is not None
    assert title_heavy is not None
    assert cyan_slice is not None
    assert spectrum_slice is not None
    assert cyan_edge is not None
    assert spectrum_edge is not None
    assert header_underline is not None
    assert page_subtitle is not None
    assert cyan_counter_rotation is not None
    assert spectrum_counter_rotation is not None
    assert header_bar is not None
    assert save_button is not None
    assert theme is not None
    assert stage is not None

    display_fonts = theme.property("displayFonts")
    if hasattr(display_fonts, "toVariant"):
        display_fonts = display_fonts.toVariant()
    assert list(display_fonts)[:2] == ["Bahnschrift", "Microsoft YaHei UI"]
    assert title_light.property("font").family() == "Microsoft YaHei UI"
    assert title_light.property("font").pixelSize() == 80
    assert title_light.property("font").weight() == 300
    assert title_heavy.property("font").pixelSize() == 75
    assert title_heavy.property("font").weight() == 700
    assert title_light.property("font").letterSpacing() < 0
    assert 0.07 <= float(title.property("facetWidthRatio")) <= 0.08
    assert 5 <= float(title.property("facetAngle")) <= 7
    assert cyan_slice.property("clip") is True
    assert spectrum_slice.property("clip") is True
    assert spectrum_slice.property("chromaticOffset") > cyan_slice.property(
        "chromaticOffset"
    ) > 0
    assert cyan_slice.property("rotation") == title.property("facetAngle")
    assert spectrum_slice.property("rotation") == title.property("facetAngle")
    facet_ratio = cyan_slice.property("width") / title_heavy.property("width")
    assert 0.07 <= facet_ratio <= 0.08
    assert cyan_slice.property("height") > title_heavy.property("height")
    assert spectrum_slice.property("height") == cyan_slice.property("height")
    assert cyan_edge.property("rotation") == title.property("facetAngle")
    assert spectrum_edge.property("rotation") == title.property("facetAngle")
    assert cyan_edge.property("width") >= 1.5
    assert spectrum_edge.property("width") >= 1.5
    assert cyan_edge.property("antialiasing") is True
    assert spectrum_edge.property("antialiasing") is True
    assert header_underline.property("antialiasing") is True
    assert cyan_counter_rotation.property("angle") == -title.property("facetAngle")
    assert spectrum_counter_rotation.property("angle") == -title.property(
        "facetAngle"
    )
    cyan_origin = cyan_counter_rotation.property("origin")
    spectrum_origin = spectrum_counter_rotation.property("origin")
    assert abs(
        cyan_origin.x()
        - (cyan_slice.property("x") + cyan_slice.property("width") / 2)
    ) < 1e-6
    assert abs(
        cyan_origin.y()
        - (cyan_slice.property("y") + cyan_slice.property("height") / 2)
    ) < 1e-6
    assert abs(
        spectrum_origin.x()
        - (spectrum_slice.property("x") + spectrum_slice.property("width") / 2)
    ) < 1e-6
    assert abs(
        spectrum_origin.y()
        - (spectrum_slice.property("y") + spectrum_slice.property("height") / 2)
    ) < 1e-6

    title_parts = (
        ("HOME", "折射", "控制台"),
        ("CAPTURE", "捕获", "光圈"),
        ("OCR", "识别", "矩阵"),
        ("TRANSLATION", "译文", "分光器"),
        ("OVERLAY", "覆盖层", "投影"),
        ("CACHE", "缓存", "阵列"),
        ("SETTINGS", "高级", "设置"),
    )
    for page, light_text, heavy_text in title_parts:
        controller.setPage(page)
        app.processEvents()
        assert title_light.property("text") == light_text
        assert title_heavy.property("text") == heavy_text

    def assert_subtitle_clearance() -> None:
        subtitle_top = page_subtitle.mapToItem(header_bar, QPointF(0, 0)).y()
        subtitle_bottom = subtitle_top + float(page_subtitle.property("height"))
        header_height = float(header_bar.property("height"))
        assert subtitle_bottom <= header_height - 4
        underline_points = (
            QPointF(0, 0),
            QPointF(float(header_underline.property("width")), 0),
            QPointF(0, float(header_underline.property("height"))),
            QPointF(
                float(header_underline.property("width")),
                float(header_underline.property("height")),
            ),
        )
        underline_bottom = max(
            header_underline.mapToItem(header_bar, point).y()
            for point in underline_points
        )
        assert subtitle_top >= underline_bottom + 3

    def assert_title_inside_container() -> None:
        for segment in (title_light, title_heavy):
            assert segment.property("y") >= 0
            assert (
                segment.property("y") + segment.property("height")
                <= title.property("height")
            )
            segment_in_header = segment.mapToItem(header_bar, QPointF(0, 0))
            assert segment_in_header.y() >= 0
            assert segment_in_header.y() + segment.property("height") <= header_bar.property(
                "height"
            )
        assert title_heavy.property("x") + title_heavy.property("width") <= title.property(
            "width"
        )
        heavy_right = title_heavy.mapToItem(
            header_bar,
            QPointF(title_heavy.property("width"), 0),
        ).x()
        save_left = save_button.mapToItem(header_bar, QPointF(0, 0)).x()
        assert heavy_right + 8 <= save_left

    assert_title_inside_container()
    window.resize(980, 700)
    controller.setTheme("dark")
    controller.setPage("OVERLAY")
    app.processEvents()
    compact_title_size = title_light.property("font").pixelSize()
    assert 60 <= compact_title_size < 80
    assert_title_inside_container()
    assert_subtitle_clearance()

    window.resize(1280, 820)
    controller.setPage("HOME")
    app.processEvents()
    assert title_light.property("font").pixelSize() == 80
    assert_title_inside_container()
    assert_subtitle_clearance()

    QTest.qWait(820)
    refraction_states: list[bool] = []
    title.refractionRunningChanged.connect(
        lambda *_args: refraction_states.append(
            bool(title.property("refractionRunning"))
        )
    )
    controller.setPage("CAPTURE")
    app.processEvents()
    QTest.qWait(1)
    app.processEvents()
    content_translate = window.findChild(QObject, "pageContentTranslate")
    page_content = window.findChild(QObject, "pageContentMotion")
    header_translate = window.findChild(QObject, "pageHeaderTranslate")
    page_header = window.findChild(QObject, "pageHeaderSlice")
    transition_sweep = window.findChild(QObject, "pageTransitionSweep")
    primary_panel = window.findChild(QObject, "capturePrimaryPanel")
    secondary_panel = window.findChild(QObject, "captureSecondaryPanel")
    tertiary_rail = window.findChild(QObject, "pageTertiaryRail")
    assert content_translate is not None
    assert page_content is not None
    assert header_translate is not None
    assert page_header is not None
    assert transition_sweep is not None
    assert primary_panel is not None
    assert secondary_panel is not None
    assert tertiary_rail is not None
    assert window.property("pageTransitioning") is True
    assert stage.property("pageTransitionRunning") is True
    assert window.property("pageTransitionSequence") >= 2
    assert window.property("pageContentReady") is False
    assert title.property("refractionRunning") is False
    assert float(title.property("refractionShift")) == 3
    assert abs(float(content_translate.property("x"))) > 0.5
    assert abs(float(header_translate.property("x"))) > 0.5
    assert primary_panel.property("entryRunning") is False
    assert secondary_panel.property("entryRunning") is False
    assert float(primary_panel.property("opacity")) == 1
    assert stage.property("deviceVisualOpacity") < 1

    QTest.qWait(70)
    app.processEvents()
    assert window.property("pageContentReady") is False
    assert float(page_content.property("opacity")) == 0
    assert primary_panel.property("entryRunning") is False
    assert 0 < float(stage.property("deviceVisualOffsetX")) < 18
    assert float(stage.property("deviceVisualOpacity")) > 0.04
    assert float(transition_sweep.property("x")) > -float(
        transition_sweep.property("width")
    )

    QTest.qWait(int(theme.property("backgroundMotion")) - 70 + 90)
    app.processEvents()
    assert window.property("pageContentReady") is True
    assert float(page_content.property("opacity")) == 1
    assert primary_panel.property("entryRunning") is True
    assert secondary_panel.property("entryRunning") is True
    assert True in refraction_states
    QTest.qWait(90)
    app.processEvents()
    primary_offset = float(primary_panel.property("visualOffsetX"))
    secondary_offset = float(secondary_panel.property("visualOffsetX"))
    assert 0 <= primary_offset < secondary_offset <= 18
    assert 0 < float(primary_panel.property("opacity")) < 1
    assert 0 < float(window.findChild(QObject, "pageHeaderSlice").property("opacity")) < 1
    refraction_deadline = time.monotonic() + 0.25
    while bool(title.property("refractionRunning")) and time.monotonic() < refraction_deadline:
        QTest.qWait(5)
        app.processEvents()
    assert title.property("refractionRunning") is False
    assert False in refraction_states
    assert float(title.property("refractionShift")) == 3
    assert float(title.property("refractionEnergy")) == 0
    assert 0 < float(tertiary_rail.property("opacity")) < theme.property(
        "tertiaryRailOpacity"
    )
    assert stage.property("deviceVisualOffsetX") == 0

    first_sequence = int(window.property("pageTransitionSequence"))
    controller.setPage("OCR")
    app.processEvents()
    QTest.qWait(1)
    app.processEvents()
    ocr_primary = window.findChild(QObject, "ocrPrimaryPanel")
    ocr_secondary = window.findChild(QObject, "ocrSecondaryPanel")
    assert ocr_primary is not None
    assert ocr_secondary is not None
    assert int(window.property("pageTransitionSequence")) == first_sequence + 1
    assert window.property("pageTransitioning") is True
    assert window.property("pageContentReady") is False
    assert float(page_content.property("opacity")) == 0
    assert title.property("refractionRunning") is False
    assert abs(float(content_translate.property("x"))) > 0.5
    assert ocr_primary.property("entryRunning") is False
    assert ocr_secondary.property("entryRunning") is False
    assert float(stage.property("deviceVisualOffsetX")) > 0

    QTest.qWait(int(theme.property("backgroundMotion")) + 100)
    app.processEvents()
    assert window.property("pageTransitioning") is True
    assert window.property("pageContentReady") is True
    assert ocr_primary.property("entryRunning") is True
    assert ocr_secondary.property("entryRunning") is True
    assert 0 < float(ocr_primary.property("opacity")) < 1
    assert 0 < float(window.findChild(QObject, "pageHeaderSlice").property("opacity")) < 1
    assert 0 < tertiary_rail.property("opacity") < theme.property(
        "tertiaryRailOpacity"
    )
    QTest.qWait(int(theme.property("pageMotion")) + 50)
    app.processEvents()
    assert window.property("pageTransitioning") is False
    assert stage.property("pageTransitionRunning") is False
    assert stage.property("pageTransitionSequence") >= 1
    assert content_translate.property("x") == 0
    assert header_translate.property("x") == 0
    assert ocr_primary.property("visualOffsetX") == 0
    assert ocr_secondary.property("visualOffsetX") == 0
    assert stage.property("deviceVisualOffsetX") == 0
    assert title.property("refractionRunning") is False
    assert abs(float(title.property("refractionShift")) - 3) < 0.01
    host.shutdown()


def test_real_workbench_strengthens_key_type_and_optical_layers(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setTheme("dark")
    controller.setReducedMotion(True)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    theme = window.findChild(QObject, "prismTheme")
    title = window.findChild(QObject, "pageDisplayTitle")
    section_title = window.findChild(QObject, "sectionHeaderTitle")
    unavailable_title = window.findChild(QObject, "unavailableStateTitle")
    home_hero = window.findChild(QObject, "homeRunHero")
    home_profile = window.findChild(QObject, "homeProfileName")
    home_ocr_group = window.findChild(QObject, "homeOcrSignalGroup")
    home_translation_group = window.findChild(QObject, "homeTranslationSignalGroup")
    home_ocr_accent = window.findChild(QObject, "homeOcrSignalAccent")
    home_translation_spectrum = window.findChild(QObject, "homeTranslationSignalSpectrum")
    home_ocr_value = window.findChild(QObject, "homeOcrSignalValue")
    home_translation_value = window.findChild(QObject, "homeTranslationSignalValue")
    save_button = window.findChild(QObject, "saveAllButton")
    start_button = window.findChild(QObject, "startLiveButton")
    panel_accent = window.findChild(QObject, "panelAccentEdge")
    panel_spectrum = window.findChild(QObject, "panelSpectrumEdge")
    panel_facet = window.findChild(QObject, "prismPanelCutFacet")
    button_edge = (
        start_button.findChild(QObject, "prismButtonLightEdge")
        if start_button is not None
        else None
    )
    stage = window.findChild(QObject, "opticalStage")
    stage_frame = window.findChild(QObject, "opticalStageFrame")
    ambient_aura = window.findChild(QObject, "opticalAmbientAura")
    home_refraction = window.findChild(QObject, "homeRefractionShape")
    home_housing = window.findChild(QObject, "homeRefractionHousing")
    capture_glass = window.findChild(QObject, "captureApertureGlass")
    ocr_backplane = window.findChild(QObject, "ocrMatrixBackplane")
    translation_prism = window.findChild(QObject, "translationSplitterBody")
    overlay_near_plane = window.findChild(QObject, "overlayStageNearPlane")
    cache_tray: QObject | None = None
    settings_deck = window.findChild(QObject, "settingsCalibrationDeck")
    transition_sweep = window.findChild(QObject, "pageTransitionSweep")
    transition_core = window.findChild(QObject, "pageTransitionSweepCore")
    feedback_layer = window.findChild(QObject, "transientFeedbackLayer")
    capture_scan_line = window.findChild(QObject, "captureStageScanLine")
    start_beam = window.findChild(QObject, "startFeedbackBeam")
    assert theme is not None
    assert title is not None
    assert section_title is not None
    assert unavailable_title is not None
    assert home_hero is not None
    assert home_profile is not None
    assert home_ocr_group is not None
    assert home_translation_group is not None
    assert home_ocr_accent is not None
    assert home_translation_spectrum is not None
    assert home_ocr_value is not None
    assert home_translation_value is not None
    assert home_ocr_group.property("color") is None
    assert home_translation_group.property("color") is None
    assert save_button is not None
    assert start_button is not None
    assert panel_accent is not None
    assert panel_spectrum is not None
    assert panel_facet is not None
    assert button_edge is not None
    assert stage is not None
    assert stage_frame is not None
    assert ambient_aura is not None
    assert home_refraction is not None
    assert home_housing is not None
    assert capture_glass is not None
    assert ocr_backplane is not None
    assert translation_prism is not None
    assert overlay_near_plane is not None
    assert settings_deck is not None
    assert transition_sweep is not None
    assert transition_core is not None
    assert feedback_layer is not None
    assert capture_scan_line is not None
    assert start_beam is not None
    assert window.findChild(QObject, "pageActionFeedback") is None

    button_label = save_button.findChild(QObject, "prismButtonLabel")
    assert button_label is not None
    assert section_title.property("font").pixelSize() == 16
    assert section_title.property("font").weight() == 600
    assert section_title.property("font").letterSpacing() == 2
    assert unavailable_title.property("font").pixelSize() == 22
    assert home_hero.property("font").pixelSize() == 54
    assert home_hero.property("font").weight() == 700
    assert home_profile.property("font").pixelSize() == 18
    assert home_ocr_value.property("font").pixelSize() == 20
    assert home_translation_value.property("font").pixelSize() == 20
    assert home_ocr_accent.property("color") == theme.property("accent")
    assert home_translation_spectrum.property("color") == theme.property("spectrum")
    assert button_label.property("font").pixelSize() == 11
    assert button_label.property("font").weight() == 600
    assert button_label.property("font").letterSpacing() >= 0.8

    assert panel_accent.property("width") == 2
    assert panel_accent.property("opacity") >= 0.7
    assert panel_spectrum.property("height") == 2
    assert button_edge.property("width") == 2
    assert button_edge.property("opacity") > 0.5
    assert stage.property("opacity") == theme.property("opticalStageOpacity")
    assert theme.property("opticalStageOpacity") == 0.64
    assert stage_frame.property("opacity") == 1
    assert float(stage.property("hairlineWidth")) <= 1
    assert ambient_aura.property("antialiasing") is True
    assert window.findChild(QObject, "opticalAmbientCyanBeam") is None
    assert window.findChild(QObject, "opticalAmbientSpectrumBeam") is None
    assert window.findChild(QObject, "stagePrismSweep") is None
    for optical_shape in (
        panel_facet,
        home_housing,
        capture_glass,
        ocr_backplane,
        translation_prism,
        overlay_near_plane,
        settings_deck,
    ):
        assert float(optical_shape.property("width")) > 0
        assert float(optical_shape.property("height")) > 0
    assert transition_sweep.property("accentAlpha") >= 0.48
    assert transition_sweep.property("spectrumAlpha") >= 0.42
    assert transition_sweep.property("antialiasing") is True
    assert transition_core.property("width") == 2
    assert feedback_layer.property("lineWidth") == 3
    assert capture_scan_line.property("height") == 3
    assert start_beam.property("height") == 4
    assert theme.property("backgroundMotion") == 230
    assert theme.property("pageMotion") == 390
    assert theme.property("pageSecondaryMotion") == 320
    assert theme.property("actionMotion") == 520
    assert theme.property("startPreludeMotion") == 350
    assert theme.property("warningMotion") == 780

    page_motifs = {
        "HOME": window.findChild(QObject, "homeStageMotif"),
        "CAPTURE": window.findChild(QObject, "captureStageMotif"),
        "OCR": window.findChild(QObject, "ocrStageMotif"),
        "TRANSLATION": window.findChild(QObject, "translationStageMotif"),
        "OVERLAY": window.findChild(QObject, "overlayStageMotif"),
        "CACHE": window.findChild(QObject, "cacheStageMotif"),
        "SETTINGS": window.findChild(QObject, "settingsStageMotif"),
    }
    assert all(motif is not None for motif in page_motifs.values())
    for page, active_motif in page_motifs.items():
        controller.setPage(page)
        app.processEvents()
        assert active_motif is not None
        assert active_motif.isVisible() is True
        assert sum(motif.isVisible() for motif in page_motifs.values()) == 1
        if page == "CACHE":
            cache_tray = _find_quick_item(window, "cacheStageTray0")
            assert cache_tray is not None
            assert cache_tray.property("width") == 822
            assert cache_tray.property("height") == 52

    dark_cyan_facet_alpha = float(title.property("cyanFacetOpacity"))
    dark_spectrum_facet_alpha = float(title.property("spectrumFacetOpacity"))
    dark_stage_opacity = float(stage.property("opacity"))
    dark_sweep_accent_alpha = float(transition_sweep.property("accentAlpha"))
    dark_sweep_spectrum_alpha = float(transition_sweep.property("spectrumAlpha"))
    controller.setTheme("light")
    app.processEvents()
    assert 0 < float(title.property("cyanFacetOpacity")) < dark_cyan_facet_alpha
    assert (
        0
        < float(title.property("spectrumFacetOpacity"))
        < dark_spectrum_facet_alpha
    )
    assert 0 < float(stage.property("opacity")) < dark_stage_opacity
    assert (
        0
        < float(transition_sweep.property("accentAlpha"))
        < dark_sweep_accent_alpha
    )
    assert (
        0
        < float(transition_sweep.property("spectrumAlpha"))
        < dark_sweep_spectrum_alpha
    )
    assert float(stage.property("opacity")) == 0.56
    host.shutdown()


def test_real_prism_button_feedback_tracks_pointer_and_reduced_motion(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setReducedMotion(False)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    button = _find_quick_item(window, "navigationButton0")
    theme = window.findChild(QObject, "prismTheme")
    assert button is not None
    assert theme is not None
    QTest.qWait(int(theme.property("pageMotion")) + 60)
    app.processEvents()

    button_point = button.mapToScene(
        QPointF(button.width() / 2, button.height() / 2)
    ).toPoint()
    outside_point = QPoint(window.width() - 4, window.height() - 4)
    fast = int(theme.property("fast"))
    QTest.mouseMove(window, outside_point)
    QTest.qWait(fast + 20)
    app.processEvents()
    assert button.property("hovered") is False
    assert abs(float(button.property("scale")) - 1.0) < 0.001

    QTest.mouseMove(window, button_point)
    app.processEvents()
    assert button.property("hovered") is True
    QTest.qWait(max(5, fast // 2))
    hover_midpoint = float(button.property("scale"))
    assert 1.0 < hover_midpoint < 1.004
    QTest.qWait(fast + 20)
    assert abs(float(button.property("scale")) - 1.004) < 0.001

    QTest.mousePress(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        button_point,
    )
    app.processEvents()
    assert button.property("down") is True
    QTest.qWait(max(5, fast // 2))
    press_midpoint = float(button.property("scale"))
    assert 0.994 < press_midpoint < 1.004
    QTest.qWait(fast + 20)
    assert abs(float(button.property("scale")) - 0.994) < 0.001

    controller.setReducedMotion(True)
    app.processEvents()
    assert theme.property("fast") == 0
    assert abs(float(button.property("scale")) - 0.994) < 0.001
    QTest.mouseRelease(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        button_point,
    )
    app.processEvents()
    assert button.property("down") is False
    assert abs(float(button.property("scale")) - 1.004) < 0.001
    QTest.mouseMove(window, outside_point)
    app.processEvents()
    assert button.property("hovered") is False
    assert abs(float(button.property("scale")) - 1.0) < 0.001

    button.setProperty("enabled", False)
    app.processEvents()
    edge = button.findChild(QObject, "prismButtonLightEdge")
    assert edge is not None
    QTest.mouseMove(window, button_point)
    QTest.mousePress(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        button_point,
    )
    app.processEvents()
    assert button.property("down") is False
    QTest.mouseRelease(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        button_point,
    )
    app.processEvents()
    assert controller.currentPage == "HOME"
    assert abs(float(button.property("scale")) - 1.0) < 0.001
    assert abs(float(edge.property("opacity")) - 0.15) < 0.001
    host.shutdown()


def test_real_page_operations_animate_their_background_motifs(tmp_path: Path) -> None:
    class ActionController(WorkbenchController):
        def __init__(self, config_path: Path) -> None:
            super().__init__(config_path, probe_ocr_devices=False)
            self.probe_calls = 0

        @Slot()
        def probeOcrDevices(self) -> None:  # noqa: N802
            self.probe_calls += 1

    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = ActionController(config_path)
    selectors: list[_SelectorStub] = []
    selector_failure: list[Exception] = []

    def make_selector(_screen) -> _SelectorStub:
        if selector_failure:
            raise selector_failure.pop()
        selector = _SelectorStub()
        selectors.append(selector)
        return selector

    host = QmlWorkbenchHost(
        controller,
        application=app,
        selector_factory=make_selector,
    )
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    stage = window.findChild(QObject, "opticalStage")
    feedback_layer = window.findChild(QObject, "transientFeedbackLayer")
    capture_motif = window.findChild(QObject, "captureStageMotif")
    capture_scan_line = window.findChild(QObject, "captureStageScanLine")
    title = window.findChild(QObject, "pageDisplayTitle")
    theme = window.findChild(QObject, "prismTheme")
    assert stage is not None
    assert feedback_layer is not None
    assert capture_motif is not None
    assert capture_scan_line is not None
    assert title is not None
    assert theme is not None
    assert window.findChild(QObject, "pageActionFeedback") is None
    assert feedback_layer.parent() == stage.parent()
    assert feedback_layer.property("enabled") is False
    assert feedback_layer.property("opacity") == 1
    assert feedback_layer.property("z") > stage.property("z")

    operations = (
        (
            "OCR",
            "ocrProbeAction",
            "focus",
            "ocrStageMotif",
            "ocrStageFocusBox0",
            "scale",
            lambda current, resting: current < resting - 0.005,
        ),
        (
            "TRANSLATION",
            "translationTraceAction",
            "trace",
            "translationStageMotif",
            "translationStageTracePrimary",
            "width",
            lambda current, resting: current < resting - 20,
        ),
        (
            "CACHE",
            "cacheRippleAction",
            "ripple",
            "cacheStageMotif",
            "cacheStageRail0",
            "height",
            lambda current, resting: current > resting + 0.1,
        ),
        (
            "SETTINGS",
            "saveAllButton",
            "calibrate",
            "settingsStageMotif",
            "settingsStageCalibrationTarget",
            "rotation",
            lambda current, resting: current > resting + 1,
        ),
    )
    previous_sequence = int(stage.property("actionSequence"))

    controller.setPage("CAPTURE")
    app.processEvents()
    custom_action = _click_quick_item(window, "captureCustomAction")
    assert int(stage.property("actionSequence")) == previous_sequence
    assert stage.property("actionPulseRunning") is False
    assert selectors[-1].opened is True
    assert window.isVisible() is False
    selectors[-1].selected_region = (10, 20, 640, 180)
    selectors[-1].finished.emit(int(QDialog.DialogCode.Accepted))
    app.processEvents()
    QTest.qWait(1)
    app.processEvents()
    assert window.isVisible() is True
    assert controller.captureLeft == 10
    assert controller.captureTop == 20
    assert controller.captureWidth == 640
    assert controller.captureHeight == 180
    assert stage.property("actionKind") == "scan"
    assert int(stage.property("actionSequence")) == previous_sequence + 1
    assert stage.property("actionPulseRunning") is True
    assert capture_motif.property("actionLinked") is True
    assert feedback_layer.property("visible") is False
    resting_scan_y = 294.0
    QTest.qWait(180)
    app.processEvents()
    assert abs(float(capture_scan_line.property("y")) - resting_scan_y) > 10
    previous_sequence += 1

    _click_quick_item(window, "captureCustomAction")
    assert window.isVisible() is False
    selectors[-1].finished.emit(int(QDialog.DialogCode.Rejected))
    app.processEvents()
    QTest.qWait(1)
    app.processEvents()
    assert window.isVisible() is True
    assert int(stage.property("actionSequence")) == previous_sequence
    assert stage.property("actionPulseRunning") is False
    assert capture_motif.property("actionLinked") is False
    assert feedback_layer.property("visible") is False

    selector_failure.append(RuntimeError("selector unavailable"))
    _click_quick_item(window, "captureCustomAction")
    app.processEvents()
    QTest.qWait(1)
    app.processEvents()
    assert window.isVisible() is True
    assert int(stage.property("actionSequence")) == previous_sequence
    assert stage.property("actionPulseRunning") is False
    assert capture_motif.property("actionLinked") is False
    assert feedback_layer.property("visible") is False

    assert custom_action.property("text") == "自定义区域"
    assert window.findChild(QObject, "captureRegionSelectAction") is None
    assert not any(
        str(item.property("text")) in {"框选区域", "保存区域"}
        for item in window.findChildren(QObject)
    )

    motif_names = ["captureStageMotif"]
    visual_states = [(capture_scan_line, "y", resting_scan_y)]
    for (
        page,
        button_name,
        feedback,
        motif_name,
        visual_name,
        visual_property,
        changed,
    ) in operations:
        controller.setPage(page)
        app.processEvents()
        motif = window.findChild(QObject, motif_name)
        visual = _find_quick_item(window, visual_name)
        assert motif is not None
        assert visual is not None, visual_name
        resting_value = float(visual.property(visual_property))
        _click_quick_item(window, button_name)
        assert stage.property("actionKind") == feedback
        assert int(stage.property("actionSequence")) == previous_sequence + 1
        assert stage.property("actionPulseRunning") is True
        assert motif.property("actionLinked") is True
        assert feedback_layer.property("visible") is False
        QTest.qWait(180)
        app.processEvents()
        assert changed(float(visual.property(visual_property)), resting_value)
        motif_names.append(motif_name)
        visual_states.append((visual, visual_property, resting_value))
        previous_sequence += 1
    assert controller.probe_calls == 1

    QTest.qWait(int(theme.property("actionMotion")) + 30)
    app.processEvents()
    assert stage.property("actionPulseRunning") is False
    assert feedback_layer.property("visible") is False
    for motif_name in motif_names:
        motif = window.findChild(QObject, motif_name)
        assert motif is not None
        assert motif.property("actionLinked") is False
    for visual, visual_property, resting_value in visual_states:
        assert math.isclose(
            float(visual.property(visual_property)),
            resting_value,
            abs_tol=0.01,
        )

    controller.setReducedMotion(True)
    controller.setPage("OCR")
    app.processEvents()
    assert controller.reducedMotion is True
    assert window.property("reduceMotion") is True
    assert stage.property("reducedMotion") is True
    assert feedback_layer.property("visible") is False
    QTest.qWait(16)
    app.processEvents()
    assert stage.property("actionPulseRunning") is False
    _click_quick_item(window, "ocrProbeAction")
    assert stage.property("actionKind") == "focus"
    assert int(stage.property("actionSequence")) == previous_sequence + 1
    assert stage.property("actionPulseRunning") is False
    ocr_motif = window.findChild(QObject, "ocrStageMotif")
    assert ocr_motif is not None
    assert ocr_motif.property("actionLinked") is False
    assert stage.property("pageTransitionRunning") is False
    assert stage.property("startPreludeRunning") is False
    assert stage.property("actionProgress") == 1
    assert window.property("pageTransitioning") is False
    assert title.property("refractionRunning") is False
    assert float(title.property("refractionShift")) == 3
    host.shutdown()


def test_capture_custom_action_preserves_cancel_and_applies_boundary_edits(
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setReducedMotion(True)
    selectors: list[_SelectorStub] = []

    def make_selector(_screen) -> _SelectorStub:
        selector = _SelectorStub()
        selectors.append(selector)
        return selector

    controller.setPage("CAPTURE")
    host = QmlWorkbenchHost(
        controller,
        application=app,
        selector_factory=make_selector,
    )
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None

    custom_action = window.findChild(QObject, "captureCustomAction")
    assert custom_action is not None
    assert custom_action.property("text") == "自定义区域"
    assert window.findChild(QObject, "captureRegionSelectAction") is None
    assert controller.customRegion is False
    original_region = (
        controller.captureLeft,
        controller.captureTop,
        controller.captureWidth,
        controller.captureHeight,
    )

    _click_quick_item(window, "captureCustomAction")
    assert window.isVisible() is False
    assert selectors[-1].opened is True
    selectors[-1].finished.emit(int(QDialog.DialogCode.Rejected))
    app.processEvents()
    assert window.isVisible() is True
    assert controller.customRegion is False
    assert (
        controller.captureLeft,
        controller.captureTop,
        controller.captureWidth,
        controller.captureHeight,
    ) == original_region

    _click_quick_item(window, "captureCustomAction")
    selectors[-1].selected_region = (10, 20, 640, 180)
    selectors[-1].finished.emit(int(QDialog.DialogCode.Accepted))
    app.processEvents()
    assert window.isVisible() is True
    assert controller.customRegion is True
    assert (
        controller.captureLeft,
        controller.captureTop,
        controller.captureWidth,
        controller.captureHeight,
    ) == (10, 20, 640, 180)
    saved_profile = load_game_profile(config_path, load_config(config_path), "game")
    assert saved_profile.capture_settings.region == (10, 20, 640, 180)

    desired_values = {
        "捕获区域左边界": 30,
        "捕获区域上边界": 40,
        "捕获区域宽度": 800,
        "捕获区域高度": 400,
    }
    steppers = {
        str(item.property("accessibleName")): item
        for item in window.findChildren(QObject)
        if str(item.property("accessibleName")) in desired_values
    }
    assert set(steppers) == set(desired_values)
    for name, value in desired_values.items():
        stepper = steppers[name]
        assert stepper.property("enabled") is True
        editor = stepper.findChild(QObject, "numberStepperEditor")
        assert editor is not None
        editor.forceActiveFocus()
        editor.setProperty("text", str(value))
        QTest.keyClick(window, Qt.Key.Key_Return)
        app.processEvents()

    assert (
        controller.captureLeft,
        controller.captureTop,
        controller.captureWidth,
        controller.captureHeight,
    ) == (30, 40, 800, 400)
    assert controller.settingsDirty is True

    _click_quick_item(window, "saveAllButton")
    app.processEvents()
    assert controller.settingsDirty is False
    saved_profile = load_game_profile(config_path, load_config(config_path), "game")
    assert saved_profile.capture_settings.region == (30, 40, 800, 400)
    host.shutdown()


@pytest.mark.parametrize("skin", [SKIN_PRISM, SKIN_DOHNA])
def test_start_button_waits_for_prelude_and_reduced_motion_runs_immediately(
    tmp_path: Path,
    skin: str,
) -> None:
    class RecordingController(WorkbenchController):
        def __init__(self, config_path: Path) -> None:
            super().__init__(config_path, probe_ocr_devices=False)
            self.toggle_calls = 0

        @Slot()
        def toggleLive(self) -> None:  # noqa: N802
            self.toggle_calls += 1

    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )
    controller = RecordingController(config_path)
    controller.setSkin(skin)
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    theme = window.findChild(QObject, "prismTheme")
    stage = window.findChild(QObject, "opticalStage")
    start_feedback = window.findChild(QObject, "startPreludeFeedback")
    dohna_feedback = window.findChild(QObject, "dohnaFeedbackLayer")
    assert stage is not None
    assert start_feedback is not None
    assert dohna_feedback is not None
    assert theme is not None

    _click_quick_item(window, "startLiveButton")
    assert window.property("startPreludePending") is True
    assert controller.toggle_calls == 0
    if skin == SKIN_DOHNA:
        assert stage.property("startPreludeRunning") is False
        assert dohna_feedback.property("startPulseRunning") is True
    else:
        assert stage.property("startPreludeRunning") is True
    assert stage.property("startPreludeSequence") == 1
    QTest.qWait(280)
    assert controller.toggle_calls == 0
    QTest.qWait(100)
    app.processEvents()
    assert controller.toggle_calls == 1
    assert window.property("startPreludePending") is False
    QTest.qWait(80)
    assert controller.toggle_calls == 1

    _click_quick_item(window, "startLiveButton")
    assert window.property("startPreludePending") is True
    assert controller.toggle_calls == 1
    controller.setReducedMotion(True)
    app.processEvents()
    assert controller.toggle_calls == 2
    assert window.property("startPreludePending") is False
    assert start_feedback.property("visible") is False
    assert dohna_feedback.property("startPulseRunning") is False
    QTest.qWait(16)
    app.processEvents()
    assert stage.property("startPreludeRunning") is False

    _click_quick_item(window, "startLiveButton")
    assert controller.toggle_calls == 3
    assert window.property("startPreludePending") is False

    # Switching skins during the pending prelude must settle only the visual
    # pulse; the one-shot timer still toggles the real controller exactly once.
    controller.setReducedMotion(False)
    controller.setSkin(SKIN_DOHNA if skin == SKIN_PRISM else SKIN_PRISM)
    app.processEvents()
    _click_quick_item(window, "startLiveButton")
    assert window.property("startPreludePending") is True
    pending_calls = controller.toggle_calls
    controller.setSkin(skin)
    app.processEvents()
    assert window.property("startPreludePending") is True
    QTest.qWait(int(theme.property("startPreludeMotion")) + 70)
    app.processEvents()
    assert controller.toggle_calls == pending_calls + 1
    assert window.property("startPreludePending") is False
    host.shutdown()


def test_qml_sources_use_explicit_unavailable_states_without_mock_timers() -> None:
    qml_root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "game_screen_translator"
        / "gui"
        / "qml"
    )
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(qml_root.rglob("*.qml"))
    )

    assert 'readonly property var pageOrder: ["HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS"]' in sources
    assert "LAST RUN OCR · UNAVAILABLE" in sources
    assert "LAST RUN TRANSLATION · UNAVAILABLE" in sources
    assert "LAST RUN CACHE · UNAVAILABLE" in sources
    assert "Math.random" not in sources
    assert 'objectName: "startPreludeTimer"' in sources
    assert 'interval: 400' in sources
    assert re.search(r"workbench\.apiKey\b", sources) is None
    assert re.search(
        r"font\.family:\s*(?:(?:root\.)?theme|prism)\."
        r"(?:uiFont|displayFont|monoFont)\b",
        sources,
    ) is None

    capture_source = (qml_root / "pages" / "CapturePage.qml").read_text(
        encoding="utf-8"
    )
    ocr_source = (qml_root / "pages" / "OcrPage.qml").read_text(encoding="utf-8")
    settings_source = (qml_root / "pages" / "SettingsPage.qml").read_text(
        encoding="utf-8"
    )
    main_source = (qml_root / "Main.qml").read_text(encoding="utf-8")
    title_source = (qml_root / "components" / "RefractedTitle.qml").read_text(
        encoding="utf-8"
    )
    stage_source = (qml_root / "components" / "OpticalStage.qml").read_text(
        encoding="utf-8"
    )
    feedback_source = (
        qml_root / "components" / "TransientFeedbackLayer.qml"
    ).read_text(encoding="utf-8")
    assert 'objectName: "captureCustomAction"' in capture_source
    assert "selectRegion()" in capture_source
    assert 'text: "框选区域"' not in capture_source
    assert 'text: "保存区域"' not in capture_source
    assert 'root.visualAction("scan")' in capture_source
    assert 'title: "捕获区域"' in capture_source
    assert 'title: "字幕区域"' not in capture_source
    assert "CAPTURE PREVIEW · UNAVAILABLE" not in capture_source
    assert "实时捕获画面未接入工作台" not in capture_source
    assert "itemEnabled: root.workbench.ocrDeviceAvailability" in ocr_source
    assert 'objectName: "ocrProbeAction"' in ocr_source
    assert 'objectName: "ocrQualitySlider"' in ocr_source
    assert "stepSize: 1" in ocr_source
    assert 'root.visualAction("focus")' in ocr_source
    assert ocr_source.count("setDynamicRoiEnabled") == 1
    assert "setDynamicRoiEnabled" not in settings_source
    assert settings_source.count('root.visualAction("calibrate")') >= 8
    assert 'objectName: "saveAllButton"' in main_source
    assert 'root.pulseVisualAction("calibrate")' in main_source
    assert "TransientFeedbackLayer" in main_source
    assert "pageActionFeedback" not in feedback_source
    assert "startPreludeFeedback" in feedback_source
    for motif_name in (
        "captureStageMotif",
        "ocrStageMotif",
        "translationStageMotif",
        "overlayStageMotif",
        "cacheStageMotif",
        "settingsStageMotif",
    ):
        assert motif_name in stage_source
    assert stage_source.count("preferredRendererType: Shape.CurveRenderer") >= 5
    assert "style: Text.Raised" not in title_source
    assert "facetWidthRatio: 0.075" in title_source
    assert title_source.count("renderType: Text.CurveRendering") == 4
    assert title_source.count(
        "renderTypeQuality: Text.VeryHighRenderTypeQuality"
    ) == 4
    assert title_source.count("layer.enabled: true") == 2
    assert title_source.count("layer.samples: 4") == 2
    assert 'objectName: "pageHeaderUnderline"' in main_source


def test_cache_page_hides_numeric_metrics_without_a_profile(tmp_path: Path) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    controller.setPage("CACHE")
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()

    window = host.window
    assert window is not None
    metrics = window.findChild(QObject, "cacheSummaryMetrics")
    assert metrics is not None
    assert metrics.property("visible") is False
    visible_text = {
        str(item.property("text"))
        for item in window.findChildren(QObject)
        if item.property("visible") is True and item.property("text") is not None
    }
    assert "尚未选择 Profile" in visible_text
    assert controller.hasProfile is False
    host.shutdown()


def test_region_selector_accepts_or_cancels_then_restores_workbench() -> None:
    controller = _ControllerStub()
    selectors: list[_SelectorStub] = []

    def make_selector(_screen) -> _SelectorStub:
        selector = _SelectorStub()
        selectors.append(selector)
        return selector

    host, engine = _host(controller, selector_factory=make_selector)
    host.show()
    first_window = host.window
    assert first_window is not None

    controller.regionSelectionRequested.emit(0)
    assert not first_window.isVisible()
    assert selectors[-1].opened is True
    selectors[-1].selected_region = (10, 20, 800, 300)
    selectors[-1].finished.emit(int(QDialog.DialogCode.Accepted))
    assert controller.accepted_regions == [(10, 20, 800, 300)]
    assert first_window.isVisible()

    controller.regionSelectionRequested.emit(0)
    selectors[-1].finished.emit(int(QDialog.DialogCode.Rejected))
    assert controller.cancel_count == 1
    assert first_window.isVisible()

    controller.regionSelectionRequested.emit(0)
    controller.liveReady.emit()
    selectors[-1].finished.emit(int(QDialog.DialogCode.Rejected))
    assert controller.cancel_count == 2
    assert host.window is None
    assert engine.root.release_count == 1
    controller.liveFailed.emit()
    restored_window = host.window
    assert restored_window is not None
    assert restored_window.isVisible()

    restored_window.close()


def test_region_selector_construction_failure_is_reported_without_escaping() -> None:
    controller = _ControllerStub()

    def fail_selector(_screen):
        raise RuntimeError("selector unavailable")

    host, _engine = _host(controller, selector_factory=fail_selector)
    host.show()

    controller.regionSelectionRequested.emit(0)

    window = host.window
    assert window is not None
    assert window.isVisible() is True
    assert controller.cancel_count == 1
    assert controller.host_errors == [
        ("无法打开区域选择器", "selector unavailable")
    ]
    host.shutdown()


def test_about_to_quit_uses_shutdown_without_stopping_live() -> None:
    controller = _ControllerStub()
    application = _ApplicationRecorder()
    host, _engine = _host(controller, application=application)

    application.aboutToQuit.emit()
    host.shutdown()

    assert controller.shutdown_count == 1
    assert controller.stop_count == 0
    assert host.window is None


def test_real_host_and_controller_rebuild_workbench_after_live_exit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    app = _application()
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    create_game_profile(
        config_path,
        load_config(config_path),
        "game",
        display_name="测试游戏",
    )

    class ProcessStub:
        pid = 4321

        def __init__(self) -> None:
            self.return_code: int | None = None
            self.poll_count = 0

        def poll(self) -> int | None:
            self.poll_count += 1
            return self.return_code

        def terminate(self) -> None:
            self.return_code = 0

    process = ProcessStub()
    monkeypatch.setattr(
        controller_module,
        "_validate_ocr_device_isolated",
        lambda _device: "gpu:0 · integration test",
    )
    monkeypatch.setattr(
        controller_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: process,
    )

    controller = WorkbenchController(config_path, probe_ocr_devices=False)
    host = QmlWorkbenchHost(controller, application=app)
    controller.setPage("TRANSLATION")
    host.show()
    first_window = host.window
    assert first_window is not None

    translation_page = first_window.findChild(QObject, "translationPage")
    glossary_editor = first_window.findChild(QObject, "glossaryEditor")
    assert translation_page is not None
    assert glossary_editor is not None
    translation_page.setProperty("sideMode", "glossary")
    app.processEvents()
    add_row_button = glossary_editor.findChild(QObject, "addPairRowButton")
    assert add_row_button is not None
    click_position = add_row_button.mapToScene(
        QPointF(
            add_row_button.property("width") / 2,
            add_row_button.property("height") / 2,
        )
    ).toPoint()
    QTest.mouseClick(
        first_window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        click_position,
    )
    app.processEvents()
    assert glossary_editor.property("entryCount") == 1
    assert glossary_editor.property("dirty") is True
    assert controller.glossaryEntries == [{"source": "", "target": ""}]
    assert controller.glossaryDirty is True
    first_window.update()
    QTest.qWait(20)
    app.processEvents()
    source_field = _find_quick_item(first_window, "pairSourceField-0")
    target_field = _find_quick_item(first_window, "pairTargetField-0")
    assert source_field is not None
    assert target_field is not None
    source_field.forceActiveFocus()
    _key_clicks(first_window, "unsaved source")
    target_field.forceActiveFocus()
    _key_clicks(first_window, "unsaved target")
    app.processEvents()
    assert controller.glossaryEntries == [
        {"source": "unsaved source", "target": "unsaved target"}
    ]
    controller.setPage("OCR")

    controller.startLive()
    app.processEvents()

    assert controller.runPhase == "running"
    assert controller._live_monitor.isActive() is True
    assert host.window is None
    assert host.engine is None
    polls_while_hidden = process.poll_count
    controller._check_live_process()
    assert process.poll_count > polls_while_hidden
    assert controller._live_monitor.isActive() is True

    process.return_code = 0
    controller._check_live_process()
    app.processEvents()

    restored_window = host.window
    assert restored_window is not None
    assert restored_window is not first_window
    assert restored_window.isVisible() is True
    restored_stack = restored_window.findChild(QObject, "pageStack")
    assert restored_stack is not None
    assert restored_stack.property("currentIndex") == 2
    restored_editor = restored_window.findChild(QObject, "glossaryEditor")
    assert restored_editor is not None
    assert restored_editor.property("entryCount") == 1
    assert restored_editor.property("dirty") is True
    restored_source = _find_quick_item(restored_window, "pairSourceField-0")
    restored_target = _find_quick_item(restored_window, "pairTargetField-0")
    assert restored_source is not None
    assert restored_target is not None
    assert restored_source.property("text") == "unsaved source"
    assert restored_target.property("text") == "unsaved target"
    assert controller.glossaryDirty is True
    assert controller._live_monitor.isActive() is False
    assert controller.runPhase == "stopped"

    process.return_code = None
    controller.startLive()
    app.processEvents()
    assert host.window is None
    process.return_code = 7
    controller._check_live_process()
    app.processEvents()

    failed_window = host.window
    assert failed_window is not None
    error_dialog = failed_window.findChild(QObject, "errorDialog")
    assert error_dialog is not None
    assert error_dialog.property("visible") is True
    assert controller.runPhase == "failed"
    failed_editor = failed_window.findChild(QObject, "glossaryEditor")
    assert failed_editor is not None
    assert failed_editor.property("entryCount") == 1
    assert failed_editor.property("dirty") is True
    host.shutdown()


def test_run_keeps_config_duration_and_probe_compatibility(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = {}

    class ApplicationStub:
        @staticmethod
        def instance():
            return None

        def __init__(self, arguments) -> None:
            calls["arguments"] = arguments

        def setApplicationName(self, value: str) -> None:  # noqa: N802
            calls["application_name"] = value

        def setApplicationDisplayName(self, value: str) -> None:  # noqa: N802
            calls["display_name"] = value

        def platformName(self) -> str:  # noqa: N802
            return "test"

        def primaryScreen(self):  # noqa: N802
            return None

        def quit(self) -> None:
            calls["quit"] = True

        def exec(self) -> int:
            return 17

    class ControllerStub:
        def __init__(self, config_path: Path, *, probe_ocr_devices: bool) -> None:
            calls["controller"] = (config_path, probe_ocr_devices)

        def shutdown(self) -> None:
            calls["controller_shutdown"] = calls.get("controller_shutdown", 0) + 1

    class HostStub:
        def __init__(self, controller, *, application) -> None:
            calls["host"] = (controller, application)
            self.window = object()

        def show(self) -> None:
            calls["shown"] = True

        def shutdown(self) -> None:
            calls["host_shutdown"] = True

    class TimerStub:
        @staticmethod
        def singleShot(milliseconds: int, callback) -> None:  # noqa: N802
            calls.setdefault("timers", []).append((milliseconds, callback))

    monkeypatch.setattr(host_module, "QApplication", ApplicationStub)
    monkeypatch.setattr(host_module, "WorkbenchController", ControllerStub)
    monkeypatch.setattr(host_module, "QmlWorkbenchHost", HostStub)
    monkeypatch.setattr(host_module, "QTimer", TimerStub)

    config_path = tmp_path / "config.toml"
    assert host_module.run(
        config_path,
        duration_seconds=0.25,
        probe_ocr_devices=False,
    ) == 17

    assert calls["controller"] == (config_path, False)
    assert [milliseconds for milliseconds, _callback in calls["timers"]] == [0, 250]
    assert calls["shown"] is True
    assert calls["host_shutdown"] is True

from __future__ import annotations

import ctypes
import math
import os
import re
from pathlib import Path

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
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from game_screen_translator.config import load_config
from game_screen_translator.gui import qml_workbench as host_module
from game_screen_translator.gui import workbench_controller as controller_module
from game_screen_translator.gui.qml_workbench import QmlWorkbenchHost
from game_screen_translator.gui.workbench_controller import WorkbenchController
from game_screen_translator.live.snapshot import CacheHit, SnapshotEntry, new_snapshot, save_snapshot
from game_screen_translator.profiles import create_game_profile


class _SignalRecorder:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self.callbacks):
            callback(*args)


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

    def __init__(self) -> None:
        super().__init__()
        self.accepted_regions: list[tuple[int, int, int, int]] = []
        self.cancel_count = 0
        self.shutdown_count = 0
        self.stop_count = 0
        self.host_errors: list[tuple[str, str]] = []
        self.themePreference = "dark"
        self.effectiveTheme = "dark"

    def acceptRegionSelection(self, *region: int) -> None:  # noqa: N802
        self.accepted_regions.append(region)

    def cancelRegionSelection(self) -> None:  # noqa: N802
        self.cancel_count += 1

    def stopLive(self) -> None:  # noqa: N802
        self.stop_count += 1

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
    settings_panel = window.findChild(QObject, "settingsPrimaryPanel")
    assert settings_panel is not None
    assert window.width() == 1600

    for page in ("CAPTURE", "TRANSLATION", "SETTINGS"):
        controller.setPage(page)
        app.processEvents()

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
        assert compact_width in {176.0, 200.0}
        assert 176 <= width <= 200
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

        if stepper.property("suffix"):
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


def test_real_overlay_slider_updates_draft_and_global_apply_persists_it(
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
    assert draft != configured
    assert math.isclose(
        draft,
        end_ratio,
        abs_tol=float(slider.property("stepSize")),
    )
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
    assert load_config(config_path).preview.overlay_opacity == draft
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
    assert window.width() >= 980
    assert window.height() >= 700

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
    canvas = window.findChild(QObject, "overlayLastRunCanvas")
    canvas_item = _find_quick_item(window, "overlayLastRunCanvas")
    drawn_canvas = _find_quick_item(window, "overlayCanvas")
    assert canvas is not None
    assert canvas_item is not None
    assert drawn_canvas is not None
    assert _find_quick_item(window, "overlayCanvasMask") is None
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
    assert qml_warnings == []
    controller.setPage("CACHE")
    app.processEvents()
    cache_hits = window.findChild(QObject, "cacheLastRunHits")
    assert cache_hits is not None
    assert cache_hits.property("visible") is True
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
    assert float(drawn_canvas.property("width")) <= float(canvas_item.property("width"))
    assert float(drawn_canvas.property("height")) <= float(canvas_item.property("height"))
    assert float(drawn_canvas.property("height")) > float(drawn_canvas.property("width"))
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
    assert 0.1 <= float(title.property("facetWidthRatio")) <= 0.12
    assert 8 <= float(title.property("facetAngle")) <= 12
    assert cyan_slice.property("clip") is True
    assert spectrum_slice.property("clip") is True
    assert spectrum_slice.property("chromaticOffset") > cyan_slice.property(
        "chromaticOffset"
    ) > 0
    assert cyan_slice.property("rotation") == title.property("facetAngle")
    assert spectrum_slice.property("rotation") == title.property("facetAngle")
    facet_ratio = cyan_slice.property("width") / title_heavy.property("width")
    assert 0.1 <= facet_ratio <= 0.12
    assert cyan_slice.property("height") > title_heavy.property("height")
    assert spectrum_slice.property("height") == cyan_slice.property("height")
    assert cyan_edge.property("rotation") == title.property("facetAngle")
    assert spectrum_edge.property("rotation") == title.property("facetAngle")
    assert cyan_edge.property("width") >= 1.5
    assert spectrum_edge.property("width") >= 1.5
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
    controller.setPage("OVERLAY")
    app.processEvents()
    compact_title_size = title_light.property("font").pixelSize()
    assert 60 <= compact_title_size < 80
    assert_title_inside_container()

    window.resize(1280, 820)
    controller.setPage("HOME")
    app.processEvents()
    assert title_light.property("font").pixelSize() == 80
    assert_title_inside_container()

    QTest.qWait(820)
    controller.setPage("CAPTURE")
    app.processEvents()
    QTest.qWait(1)
    app.processEvents()
    content_translate = window.findChild(QObject, "pageContentTranslate")
    header_translate = window.findChild(QObject, "pageHeaderTranslate")
    primary_panel = window.findChild(QObject, "capturePrimaryPanel")
    secondary_panel = window.findChild(QObject, "captureSecondaryPanel")
    tertiary_rail = window.findChild(QObject, "pageTertiaryRail")
    assert content_translate is not None
    assert header_translate is not None
    assert primary_panel is not None
    assert secondary_panel is not None
    assert tertiary_rail is not None
    assert window.property("pageTransitioning") is True
    assert stage.property("pageTransitionRunning") is True
    assert window.property("pageTransitionSequence") >= 2
    assert title.property("refractionRunning") is True
    assert float(title.property("refractionShift")) > 6
    assert abs(float(content_translate.property("x"))) > 0.5
    assert abs(float(header_translate.property("x"))) > 0.5
    assert primary_panel.property("entryRunning") is True
    assert secondary_panel.property("entryRunning") is True

    QTest.qWait(140)
    app.processEvents()
    primary_offset = float(primary_panel.property("visualOffsetX"))
    secondary_offset = float(secondary_panel.property("visualOffsetX"))
    assert 0 < primary_offset < secondary_offset <= 18
    assert tertiary_rail.property("opacity") == 0
    assert 0 < float(stage.property("deviceVisualOffsetX")) < 18

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
    assert abs(float(content_translate.property("x"))) > 0.5
    assert ocr_primary.property("entryRunning") is True
    assert ocr_secondary.property("entryRunning") is True

    QTest.qWait(200)
    app.processEvents()
    assert window.property("pageTransitioning") is True
    assert 0 < tertiary_rail.property("opacity") < theme.property(
        "tertiaryRailOpacity"
    )
    QTest.qWait(620)
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
    assert abs(float(title.property("refractionShift")) - 6) < 0.01
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
    save_button = window.findChild(QObject, "saveAllButton")
    panel_accent = window.findChild(QObject, "panelAccentEdge")
    panel_spectrum = window.findChild(QObject, "panelSpectrumEdge")
    stage = window.findChild(QObject, "opticalStage")
    stage_frame = window.findChild(QObject, "opticalStageFrame")
    transition_sweep = window.findChild(QObject, "pageTransitionSweep")
    transition_core = window.findChild(QObject, "pageTransitionSweepCore")
    stage_core = window.findChild(QObject, "stagePrismSweepCore")
    feedback_layer = window.findChild(QObject, "transientFeedbackLayer")
    capture_scan_line = window.findChild(QObject, "captureStageScanLine")
    start_beam = window.findChild(QObject, "startFeedbackBeam")
    assert theme is not None
    assert title is not None
    assert section_title is not None
    assert unavailable_title is not None
    assert home_hero is not None
    assert save_button is not None
    assert panel_accent is not None
    assert panel_spectrum is not None
    assert stage is not None
    assert stage_frame is not None
    assert transition_sweep is not None
    assert transition_core is not None
    assert stage_core is not None
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
    assert home_hero.property("font").pixelSize() == 34
    assert button_label.property("font").pixelSize() == 11
    assert button_label.property("font").weight() == 600
    assert button_label.property("font").letterSpacing() >= 0.8

    assert panel_accent.property("width") == 2
    assert panel_accent.property("opacity") >= 0.7
    assert panel_spectrum.property("height") == 2
    assert stage.property("opacity") == theme.property("opticalStageOpacity")
    assert stage_frame.property("opacity") == 1
    assert transition_sweep.property("accentAlpha") >= 0.48
    assert transition_sweep.property("spectrumAlpha") >= 0.42
    assert transition_core.property("width") == 2
    assert stage_core.property("width") == 2
    assert feedback_layer.property("lineWidth") == 3
    assert capture_scan_line.property("height") == 3
    assert start_beam.property("height") == 4
    assert theme.property("pageMotion") == 720
    assert theme.property("actionMotion") == 720
    assert theme.property("startPreludeMotion") == 350
    assert theme.property("warningMotion") == 780

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
    _click_quick_item(window, "captureRegionSelectAction")
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

    _click_quick_item(window, "captureRegionSelectAction")
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
    _click_quick_item(window, "captureRegionSelectAction")
    app.processEvents()
    QTest.qWait(1)
    app.processEvents()
    assert window.isVisible() is True
    assert int(stage.property("actionSequence")) == previous_sequence
    assert stage.property("actionPulseRunning") is False
    assert capture_motif.property("actionLinked") is False
    assert feedback_layer.property("visible") is False

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
    assert float(title.property("refractionShift")) == 6
    host.shutdown()


def test_start_button_waits_for_prelude_and_reduced_motion_runs_immediately(
    tmp_path: Path,
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
    host = QmlWorkbenchHost(controller, application=app)
    host.show()
    app.processEvents()
    window = host.window
    assert window is not None
    stage = window.findChild(QObject, "opticalStage")
    start_feedback = window.findChild(QObject, "startPreludeFeedback")
    assert stage is not None
    assert start_feedback is not None

    _click_quick_item(window, "startLiveButton")
    assert window.property("startPreludePending") is True
    assert controller.toggle_calls == 0
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
    QTest.qWait(16)
    app.processEvents()
    assert stage.property("startPreludeRunning") is False

    _click_quick_item(window, "startLiveButton")
    assert controller.toggle_calls == 3
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
    assert sources.count("Timer {") == 1
    assert 'objectName: "startPreludeTimer"' in sources
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
    assert "setCustomRegion(true)" in capture_source
    assert 'objectName: "captureRegionSelectAction"' in capture_source
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
    assert 'stage.pulseAction("calibrate")' in main_source
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
    assert "style: Text.Raised" not in title_source
    assert "facetWidthRatio: 0.11" in title_source


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

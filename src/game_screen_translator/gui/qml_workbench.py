from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QScreen, QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QDialog

from game_screen_translator.branding import GUI_PROCESS_NAME, PRODUCT_NAME

from .region_selector import RegionSelector
from .workbench_controller import WorkbenchController


_CONTEXT_PROPERTY = "workbench"
_DEFAULT_QML_PATH = Path(__file__).with_name("qml") / "Main.qml"
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20


def _startup_message(message: str) -> None:
    print(f"[{PRODUCT_NAME} GUI] {message}", flush=True)


def _use_customizable_quick_style() -> None:
    """Select a non-native Controls style before loading customized controls."""

    QQuickStyle.setStyle("Basic")


def _set_windows_immersive_dark_mode(window_id: int, dark: bool) -> None:
    """Apply the supported per-window DWM title-bar hint when available."""

    import ctypes

    enabled = ctypes.c_int(1 if dark else 0)
    setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
    setter.argtypes = (
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_uint,
    )
    setter.restype = ctypes.c_long
    setter(
        ctypes.c_void_p(window_id),
        _DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(enabled),
        ctypes.sizeof(enabled),
    )


def _apply_workbench_window_theme(
    application: QApplication,
    window: QQuickWindow,
    preference: str,
    effective_theme: str,
    *,
    platform_name: str | None = None,
    dwm_setter: Callable[[int, bool], None] | None = None,
) -> None:
    """Synchronize Qt's color hint and the native Windows title bar safely."""

    scheme = {
        "dark": Qt.ColorScheme.Dark,
        "light": Qt.ColorScheme.Light,
        "system": Qt.ColorScheme.Unknown,
    }.get(preference, Qt.ColorScheme.Unknown)
    try:
        set_color_scheme = getattr(application.styleHints(), "setColorScheme", None)
        if callable(set_color_scheme):
            set_color_scheme(scheme)
    except (AttributeError, RuntimeError, TypeError):
        pass

    if platform_name is None:
        try:
            is_windows_window = (
                sys.platform == "win32" and application.platformName() == "windows"
            )
        except (AttributeError, RuntimeError, TypeError):
            is_windows_window = False
    else:
        is_windows_window = platform_name == "win32"
    if not is_windows_window:
        return
    try:
        native_window_id = int(window.winId())
        (dwm_setter or _set_windows_immersive_dark_mode)(
            native_window_id,
            effective_theme == "dark",
        )
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        pass


class QmlWorkbenchHost(QObject):
    """Own the native QML workbench and its QWidget-only helper window."""

    def __init__(
        self,
        controller: WorkbenchController,
        *,
        application: QApplication | None = None,
        qml_path: Path | None = None,
        engine_factory: Callable[[QObject], QQmlApplicationEngine] = QQmlApplicationEngine,
        selector_factory: Callable[[QScreen], RegionSelector] = RegionSelector,
        theme_applier: (
            Callable[[QApplication, QQuickWindow, str, str], None] | None
        ) = None,
    ) -> None:
        super().__init__()
        app = application or QApplication.instance()
        if app is None:
            raise RuntimeError("QmlWorkbenchHost 需要已经创建的 QApplication")

        _use_customizable_quick_style()

        self._application = app
        self._controller = controller
        self._engine_factory = engine_factory
        self._source_path = (qml_path or _DEFAULT_QML_PATH).resolve()
        self._selector_factory = selector_factory
        self._theme_applier = theme_applier or _apply_workbench_window_theme
        self._selector: RegionSelector | None = None
        self._restore_after_selector = False
        self._hidden_for_live = False
        self._shutdown_called = False
        self._engine: QQmlApplicationEngine | None = None
        self._window: QQuickWindow | None = None
        self._last_geometry: QRect | None = None
        self._was_maximized = False
        self._last_theme_signature: tuple[int, str, str] | None = None

        controller.stateChanged.connect(self._sync_window_theme)
        controller.regionSelectionRequested.connect(self._open_region_selector)
        controller.liveReady.connect(self._hide_for_live)
        controller.liveFinished.connect(self._restore_after_live)
        controller.liveFailed.connect(self._restore_after_live)
        app.aboutToQuit.connect(self.shutdown)

        self._create_workbench()

    @property
    def engine(self) -> QQmlApplicationEngine | None:
        return self._engine

    @property
    def window(self) -> QQuickWindow | None:
        return self._window

    def _create_workbench(self) -> None:
        if self._engine is not None:
            return
        engine = self._engine_factory(self)
        engine.rootContext().setContextProperty(_CONTEXT_PROPERTY, self._controller)
        engine.load(QUrl.fromLocalFile(str(self._source_path)))
        roots = engine.rootObjects()
        if len(roots) != 1 or not isinstance(roots[0], QQuickWindow):
            if hasattr(engine, "deleteLater"):
                engine.deleteLater()
            raise RuntimeError(
                f"QML 工作台必须从 {self._source_path} 加载唯一的 QQuickWindow 根对象"
            )
        window = roots[0]
        window.setPersistentGraphics(False)
        window.setPersistentSceneGraph(False)
        if self._last_geometry is not None:
            window.setGeometry(self._last_geometry)
        engine.quit.connect(self._application.quit)
        self._engine = engine
        self._window = window
        self._sync_window_theme(force=True)

    def _sync_window_theme(self, *, force: bool = False) -> None:
        window = self._window
        if window is None:
            return
        preference = self._controller.themePreference
        effective_theme = self._controller.effectiveTheme
        signature = (id(window), preference, effective_theme)
        if not force and signature == self._last_theme_signature:
            return
        # Record first: setting QStyleHints can synchronously emit a color-scheme
        # change that flows back through WorkbenchController.stateChanged.
        self._last_theme_signature = signature
        self._theme_applier(
            self._application,
            window,
            preference,
            effective_theme,
        )

    def _dispose_workbench(self) -> None:
        engine = self._engine
        window = self._window
        self._engine = None
        self._window = None
        if window is not None:
            self._last_geometry = window.geometry()
            self._was_maximized = window.visibility() == QWindow.Visibility.Maximized
            window.hide()
            window.releaseResources()
        if engine is not None and hasattr(engine, "deleteLater"):
            engine.deleteLater()

    def show(self) -> None:
        if (
            not self._shutdown_called
            and not self._hidden_for_live
            and self._selector is None
        ):
            self._create_workbench()
            assert self._window is not None
            if self._was_maximized:
                self._window.showMaximized()
            else:
                self._window.show()
            # Qt's Windows platform plugin reapplies non-client-area defaults
            # from its queued show processing. Reapply on the next event-loop
            # turn so the title bar reflects the selected theme on screen.
            shown_window = self._window
            QTimer.singleShot(
                0,
                lambda: self._sync_shown_window_theme(shown_window),
            )

    def _sync_shown_window_theme(self, shown_window: QQuickWindow) -> None:
        if self._window is shown_window and shown_window.isVisible():
            self._sync_window_theme(force=True)

    def _hide_for_live(self) -> None:
        self._hidden_for_live = True
        self._dispose_workbench()

    def _restore_after_live(self) -> None:
        if self._shutdown_called:
            return
        self._hidden_for_live = False
        if self._selector is None:
            self.show()

    def _open_region_selector(self, monitor_index: int) -> None:
        if self._shutdown_called:
            return
        if self._selector is not None:
            self._selector.raise_()
            self._selector.activateWindow()
            return

        self._create_workbench()
        assert self._window is not None
        self._restore_after_selector = self._window.isVisible()
        self._window.hide()
        screens = self._application.screens()
        if not 0 <= monitor_index < len(screens):
            self._controller.cancelRegionSelection()
            self._restore_window_if_allowed()
            return

        try:
            selector = self._selector_factory(screens[monitor_index])
        except Exception as exc:
            self._controller.cancelRegionSelection()
            self._restore_window_if_allowed()
            self._controller.reportHostError("无法打开区域选择器", str(exc))
            return
        self._selector = selector
        selector.finished.connect(
            lambda result, active_selector=selector: self._finish_region_selection(
                active_selector,
                result,
            )
        )
        selector.open()

    def _finish_region_selection(self, selector: RegionSelector, result: int) -> None:
        if selector is not self._selector:
            return
        self._selector = None
        try:
            region = selector.selected_region
            if result == int(QDialog.DialogCode.Accepted) and region is not None:
                self._controller.acceptRegionSelection(*region)
            else:
                self._controller.cancelRegionSelection()
        finally:
            selector.deleteLater()
            self._restore_window_if_allowed()

    def _restore_window_if_allowed(self) -> None:
        if (
            self._restore_after_selector
            and self._selector is None
            and not self._hidden_for_live
        ):
            self.show()
        if self._selector is None:
            self._restore_after_selector = False

    def shutdown(self) -> None:
        if self._shutdown_called:
            return
        self._shutdown_called = True
        self._dispose_workbench()
        self._controller.shutdown()


def run(
    config_path: Path,
    *,
    duration_seconds: float | None = None,
    probe_ocr_devices: bool = True,
) -> int:
    """Run the native QML workbench with bounded test/probe controls."""

    if duration_seconds is not None and duration_seconds <= 0:
        raise ValueError("--duration 必须大于 0")

    _use_customizable_quick_style()
    _startup_message("creating QApplication")
    app = QApplication.instance() or QApplication([GUI_PROCESS_NAME])
    app.setApplicationName(PRODUCT_NAME)
    app.setApplicationDisplayName(PRODUCT_NAME)
    _startup_message(f"Qt platform: {app.platformName()}")
    _startup_message("building native QML workbench")
    controller = WorkbenchController(
        Path(config_path),
        probe_ocr_devices=probe_ocr_devices,
    )
    try:
        host = QmlWorkbenchHost(controller, application=app)
    except Exception:
        controller.shutdown()
        raise
    window = host.window
    if window is None:
        host.shutdown()
        raise RuntimeError("QML 工作台未创建窗口")
    screen = app.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        window.setPosition(
            max(
                available.left(),
                available.left() + (available.width() - window.width()) // 2,
            ),
            max(
                available.top(),
                available.top() + (available.height() - window.height()) // 2,
            ),
        )
    _startup_message("showing native QML workbench")
    host.show()

    def announce_ready() -> None:
        current_window = host.window
        if current_window is None:
            return
        if app.platformName() == "windows":
            current_window.raise_()
            current_window.requestActivate()
        geometry = current_window.geometry()
        _startup_message(
            "event loop ready; "
            f"visible={current_window.isVisible()} geometry="
            f"{geometry.x()},{geometry.y()},{geometry.width()},{geometry.height()}"
        )

    QTimer.singleShot(0, announce_ready)
    if duration_seconds is not None:
        QTimer.singleShot(round(duration_seconds * 1000), app.quit)
    try:
        exit_code = app.exec()
        _startup_message(f"event loop exited with code {exit_code}")
        return exit_code
    finally:
        host.shutdown()

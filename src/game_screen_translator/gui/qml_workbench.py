from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QColor,
    QFontDatabase,
    QIcon,
    QScreen,
    QWindow,
)
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QDialog, QSystemTrayIcon, QWidget

from game_screen_translator.branding import GUI_PROCESS_NAME, PRODUCT_NAME

from .region_selector import RegionSelector
from .runtime import (
    ACTIVATION_MESSAGE,
    ACTIVATION_WINDOW_TITLE,
    GuiRuntimeError,
    WindowsGlobalHotkey,
)
from .theme import (
    HOTKEY_BEHAVIOR_START_ONLY,
    HOTKEY_BEHAVIOR_TOGGLE,
    HOTKEY_BEHAVIOR_TOGGLE_SHOW,
)
from .workbench_controller import WorkbenchController


_CONTEXT_PROPERTY = "workbench"
_DEFAULT_QML_PATH = Path(__file__).with_name("qml") / "Main.qml"
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36
_REGISTERED_DISPLAY_FONT_IDS: list[int] = []
_SYSTEM_DISPLAY_FONTS_CHECKED = False


def _startup_message(message: str) -> None:
    print(f"[{PRODUCT_NAME} GUI] {message}", flush=True)


def _use_customizable_quick_style() -> None:
    """Select a non-native Controls style before loading customized controls."""

    QQuickStyle.setStyle("Basic")


def _register_optional_system_display_fonts() -> None:
    """Expose installed display faces to Qt when Windows does not enumerate them."""

    global _SYSTEM_DISPLAY_FONTS_CHECKED
    if _SYSTEM_DISPLAY_FONTS_CHECKED or sys.platform != "win32":
        return
    _SYSTEM_DISPLAY_FONTS_CHECKED = True
    font_directory = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for filename in (
        "ARIALN.TTF",
        "ARIALNB.TTF",
        "ARIALNI.TTF",
        "ARIALNBI.TTF",
        "ARIBLK.TTF",
    ):
        font_path = font_directory / filename
        if not font_path.is_file():
            continue
        try:
            font_id = QFontDatabase.addApplicationFont(str(font_path))
        except (OSError, RuntimeError):
            continue
        if font_id >= 0:
            _REGISTERED_DISPLAY_FONT_IDS.append(font_id)


def _use_smooth_quick_rendering() -> None:
    """Use curve glyphs as the default for every Text item in the workbench."""

    QQuickWindow.setTextRenderType(
        QQuickWindow.TextRenderType.CurveTextRendering,
    )


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


def _set_windows_caption_color(window_id: int, attribute: int, color: QColor) -> None:
    """Set a Windows 11 DWM title-bar COLORREF attribute when supported."""

    import ctypes

    colorref = ctypes.c_uint(color.red() | (color.green() << 8) | (color.blue() << 16))
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
        attribute,
        ctypes.byref(colorref),
        ctypes.sizeof(colorref),
    )


def _build_refra_icon() -> QIcon:
    """Load the prism-only runtime icon used by the app window and tray."""

    icon_path = Path(__file__).with_name("assets") / "refra-prism.ico"
    return QIcon(str(icon_path))


def _workbench_titlebar_colors(
    window: QQuickWindow,
) -> tuple[QColor, QColor] | None:
    """Read the active skin's title surface and text colors from its QML theme."""

    for object_name in ("prismTheme", "dohnaTheme"):
        theme = window.findChild(QObject, object_name)
        if theme is None or not theme.property("active"):
            continue
        surface = QColor(theme.property("headerSurface"))
        text = QColor(theme.property("text"))
        if surface.isValid() and text.isValid():
            return surface, text
    return None


def _apply_workbench_window_theme(
    application: QApplication,
    window: QQuickWindow,
    preference: str,
    effective_theme: str,
    *,
    platform_name: str | None = None,
    dwm_setter: Callable[[int, bool], None] | None = None,
    dwm_color_setter: Callable[[int, int, QColor], None] | None = None,
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
        colors = _workbench_titlebar_colors(window)
        if colors is not None:
            surface, text = colors
            set_color = dwm_color_setter or _set_windows_caption_color
            for attribute, color in (
                (_DWMWA_CAPTION_COLOR, surface),
                (_DWMWA_TEXT_COLOR, text),
            ):
                try:
                    set_color(native_window_id, attribute, color)
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                    # Explicit caption colors are unavailable before Windows 11.
                    pass
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        pass


class _ActivationWindow(QWidget):
    """A hidden native target that survives QML resource disposal."""

    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint,
        )
        self._callback = callback
        self.setWindowTitle(ACTIVATION_WINDOW_TITLE)
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setFixedSize(1, 1)
        # Creating the native handle makes FindWindowW/PostMessageW usable
        # while the QML workbench is intentionally disposed in the tray.
        self.winId()
        self.hide()

    def nativeEvent(self, _event_type, message):  # noqa: N802
        try:
            pointer = int(message)
            if pointer == 0:
                return False, 0

            class _Message(ctypes.Structure):
                _fields_ = (
                    ("hwnd", ctypes.c_void_p),
                    ("message", ctypes.c_uint32),
                    ("wParam", ctypes.c_size_t),
                    ("lParam", ctypes.c_ssize_t),
                    ("time", ctypes.c_uint32),
                    ("pt_x", ctypes.c_long),
                    ("pt_y", ctypes.c_long),
                )

            native = ctypes.cast(pointer, ctypes.POINTER(_Message)).contents
            if native.message == ACTIVATION_MESSAGE:
                self._callback()
                return True, 0
        except (TypeError, ValueError, OSError):
            pass
        return super().nativeEvent(_event_type, message)


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
        tray_factory: Callable[[QApplication], QSystemTrayIcon] | None = None,
    ) -> None:
        super().__init__()
        app = application or QApplication.instance()
        if app is None:
            raise RuntimeError("QmlWorkbenchHost 需要已经创建的 QApplication")

        _register_optional_system_display_fonts()
        _use_customizable_quick_style()
        _use_smooth_quick_rendering()

        self._application = app
        self._controller = controller
        self._engine_factory = engine_factory
        self._source_path = (qml_path or _DEFAULT_QML_PATH).resolve()
        self._selector_factory = selector_factory
        self._theme_applier = theme_applier or _apply_workbench_window_theme
        self._app_icon = _build_refra_icon()
        self._selector: RegionSelector | None = None
        self._restore_after_selector = False
        self._hidden_for_live = False
        self._shutdown_called = False
        self._engine: QQmlApplicationEngine | None = None
        self._window: QQuickWindow | None = None
        self._last_geometry: QRect | None = None
        self._was_maximized = False
        self._last_theme_signature: tuple[int, str, str, str] | None = None
        self._tray_icon: QSystemTrayIcon | None = None
        self._global_hotkey: WindowsGlobalHotkey | None = None
        self._activation_window: _ActivationWindow | None = None
        self._activation_restore_pending = False
        self._hotkey_dispatch_in_progress = False
        self._pending_hotkey_stop_behavior: str | None = None

        set_window_icon = getattr(self._application, "setWindowIcon", None)
        if callable(set_window_icon):
            set_window_icon(self._app_icon)

        # The workbench must retain QApplication's normal last-window exit
        # behavior whenever live translation is not running.  Background
        # residency is enabled only while the live HUD/tray owns the session.
        self._set_quit_on_last_window_closed(True)

        controller.stateChanged.connect(self._sync_window_theme)
        controller.regionSelectionRequested.connect(self._open_region_selector)
        controller.liveReady.connect(self._hide_for_live)
        controller.liveFinished.connect(self._finish_hotkey_stop)
        controller.liveFailed.connect(self._fail_hotkey_stop)
        hide_requested = getattr(controller, "workbenchHideRequested", None)
        if hide_requested is not None and hasattr(hide_requested, "connect"):
            hide_requested.connect(self._hide_to_tray)
        app.aboutToQuit.connect(self.shutdown)

        if tray_factory is not None:
            self._tray_icon = tray_factory(self._application)
        elif isinstance(self._application, QApplication):
            self._tray_icon = QSystemTrayIcon(self._application)
        if self._tray_icon is not None:
            self._tray_icon.setIcon(self._app_icon)
            self._tray_icon.setToolTip(f"{PRODUCT_NAME} · 双击打开工作台")
            self._tray_icon.activated.connect(self._on_tray_activated)
            self._tray_icon.hide()

        self._create_workbench()
        self._activation_window = _ActivationWindow(
            self._activate_from_second_instance,
        )
        self._global_hotkey = WindowsGlobalHotkey(
            self._application,
            self._start_live_from_hotkey,
            self._report_hotkey_error,
        )
        set_hotkey_registrar = getattr(controller, "set_hotkey_registrar", None)
        if callable(set_hotkey_registrar):
            set_hotkey_registrar(self._register_hotkey_for_controller)
        self._configure_hotkey(getattr(controller, "hotkeyPreference", "Ctrl+Alt+T"))

    @property
    def tray_icon(self) -> QSystemTrayIcon | None:
        return self._tray_icon

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
        window.setIcon(self._app_icon)
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
        skin = getattr(self._controller, "skinPreference", "prism")
        preference = "light" if skin == "dohna" else self._controller.themePreference
        effective_theme = self._controller.effectiveTheme
        signature = (id(window), skin, preference, effective_theme)
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

    def _report_hotkey_error(self, message: str) -> None:
        reporter = getattr(self._controller, "reportHostError", None)
        if callable(reporter):
            reporter("全局快捷键不可用", message)

    def _configure_hotkey(self, value: str) -> None:
        hotkey = self._global_hotkey
        if hotkey is None:
            return
        try:
            self._register_hotkey_for_controller(value)
        except (GuiRuntimeError, ValueError, TypeError) as exc:
            self._report_hotkey_error(str(exc))

    def _register_hotkey_for_controller(self, value: str) -> None:
        hotkey = self._global_hotkey
        if hotkey is None:
            return
        hotkey.register(value)

    def _start_live_from_hotkey(self) -> None:
        if self._shutdown_called or self._hotkey_dispatch_in_progress:
            return

        behavior = getattr(
            self._controller,
            "hotkeyBehaviorPreference",
            HOTKEY_BEHAVIOR_START_ONLY,
        )
        if behavior not in {
            HOTKEY_BEHAVIOR_START_ONLY,
            HOTKEY_BEHAVIOR_TOGGLE,
            HOTKEY_BEHAVIOR_TOGGLE_SHOW,
        }:
            behavior = HOTKEY_BEHAVIOR_START_ONLY

        phase = self._hotkey_run_phase()
        if phase in {"starting", "stopping"}:
            return
        if phase == "running":
            if behavior == HOTKEY_BEHAVIOR_START_ONLY:
                return
            self._stop_live_from_hotkey(behavior)
            return

        start_live = getattr(self._controller, "startLive", None)
        if not callable(start_live):
            return
        # startLive() validates synchronously and pumps QApplication events
        # before creating the child process. Keep a host-side guard around the
        # whole call so a reentrant WM_HOTKEY cannot start a second session.
        self._hotkey_dispatch_in_progress = True
        try:
            start_live()
        finally:
            self._hotkey_dispatch_in_progress = False

    def _hotkey_run_phase(self) -> str:
        phase = getattr(self._controller, "runPhase", None)
        if isinstance(phase, str):
            return phase
        return "running" if bool(getattr(self._controller, "running", False)) else "stopped"

    def _stop_live_from_hotkey(self, behavior: str) -> None:
        stop_live = getattr(self._controller, "stopLive", None)
        if not callable(stop_live):
            return
        self._hotkey_dispatch_in_progress = True
        self._pending_hotkey_stop_behavior = behavior
        try:
            stop_live()
        finally:
            # A failed shutdown request leaves the controller in running state;
            # clear the host intent so a later hotkey can retry normally.
            if self._hotkey_run_phase() != "stopping":
                self._pending_hotkey_stop_behavior = None
            self._hotkey_dispatch_in_progress = False

    def _set_quit_on_last_window_closed(self, enabled: bool) -> None:
        setter = getattr(self._application, "setQuitOnLastWindowClosed", None)
        if callable(setter):
            setter(enabled)

    def _hide_for_live(self) -> None:
        self._set_quit_on_last_window_closed(False)
        self._hidden_for_live = True
        self._show_live_tray()
        self._dispose_workbench()

    def _show_live_tray(self) -> None:
        if self._tray_icon is not None:
            self._tray_icon.show()

    def _hide_live_tray(self) -> None:
        if self._tray_icon is not None:
            self._tray_icon.hide()

    def _hide_to_tray(self) -> None:
        if self._shutdown_called:
            return
        self._set_quit_on_last_window_closed(False)
        self._hidden_for_live = True
        self._show_live_tray()
        self._dispose_workbench()

    def _activate_from_second_instance(self) -> None:
        if self._shutdown_called:
            return
        phase = getattr(self._controller, "runPhase", None)
        if phase == "stopping":
            self._activation_restore_pending = True
            return
        running = bool(getattr(self._controller, "running", False))
        if not running:
            self._restore_workbench(activate=True)
            return
        self._activation_restore_pending = True
        stop_live = getattr(self._controller, "stopLive", None)
        if not callable(stop_live):
            self._activation_restore_pending = False
            self._restore_workbench(activate=True)
            self._report_activation_stop_failure()
            return
        accepted = stop_live()
        if accepted is False:
            self._activation_restore_pending = False
            self._restore_workbench(activate=True)
            if bool(getattr(self._controller, "running", False)):
                self._report_activation_stop_failure()

    def _activate_from_tray(self) -> None:
        if self._shutdown_called:
            return
        self._activation_restore_pending = False
        self._restore_workbench(activate=True)

    def hide_to_tray(self) -> None:
        """Enter background residency for a Windows logon-started GUI."""

        self._hide_to_tray()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason != QSystemTrayIcon.ActivationReason.DoubleClick:
            return
        if self._shutdown_called:
            return
        self._activate_from_tray()

    def _restore_workbench(self, *, activate: bool = False) -> None:
        running = bool(getattr(self._controller, "running", False))
        self._set_quit_on_last_window_closed(not running)
        self._hidden_for_live = False
        self._hide_live_tray()
        if self._selector is None:
            self.show()
        if activate and self._window is not None:
            self._window.raise_()
            self._window.requestActivate()

    def _report_activation_stop_failure(self) -> None:
        reporter = getattr(self._controller, "reportHostError", None)
        if callable(reporter):
            reporter(
                "停止实时翻译失败",
                "无法请求实时翻译正常关闭；实时翻译仍在运行，已恢复主窗口。",
            )

    def _restore_after_live(self) -> None:
        if self._shutdown_called:
            return
        activate = self._activation_restore_pending
        self._activation_restore_pending = False
        self._restore_workbench(activate=activate)

    def _keep_hidden_after_live(self) -> None:
        if self._shutdown_called:
            return
        self._set_quit_on_last_window_closed(False)
        self._hidden_for_live = True
        self._show_live_tray()

    def _finish_hotkey_stop(self) -> None:
        behavior = self._pending_hotkey_stop_behavior
        self._pending_hotkey_stop_behavior = None
        if self._activation_restore_pending:
            self._restore_after_live()
            return
        if behavior == HOTKEY_BEHAVIOR_TOGGLE and self._window is None:
            self._keep_hidden_after_live()
            return
        if behavior == HOTKEY_BEHAVIOR_TOGGLE_SHOW:
            self._restore_after_live()
            window = self._window
            if window is not None:
                window.raise_()
                window.requestActivate()
            return
        self._restore_after_live()

    def _fail_hotkey_stop(self) -> None:
        self._pending_hotkey_stop_behavior = None
        self._restore_after_live()

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
        self._set_quit_on_last_window_closed(True)
        self._hide_live_tray()
        if self._global_hotkey is not None:
            self._global_hotkey.close()
        if self._activation_window is not None:
            self._activation_window.close()
            self._activation_window.deleteLater()
            self._activation_window = None
        self._dispose_workbench()
        self._controller.shutdown()


def run(
    config_path: Path,
    *,
    duration_seconds: float | None = None,
    probe_ocr_devices: bool = True,
    startup: bool = False,
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
    if startup:
        _startup_message("starting in the system tray")
        host.hide_to_tray()
    else:
        _startup_message("showing native QML workbench")
        host.show()

    def announce_ready() -> None:
        current_window = host.window
        if current_window is None:
            if startup:
                _startup_message("event loop ready; visible=false tray=true")
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

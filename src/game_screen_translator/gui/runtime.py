"""Windows-only GUI lifecycle helpers.

The GUI already owns its settings and live-process state.  This module keeps
the small amount of Windows integration needed by the launcher (single
instance, logon startup and a global hotkey) out of the QML/controller code.
All helpers are no-ops or explicit errors outside the supported Windows GUI
runtime so the existing non-Windows test and development paths stay usable.
"""

from __future__ import annotations

import ctypes
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from game_screen_translator.branding import PRODUCT_NAME

try:  # Keep the core package importable when the optional GUI extra is absent.
    from PySide6.QtCore import QAbstractNativeEventFilter
except ImportError:  # pragma: no cover - exercised only without the GUI extra
    class QAbstractNativeEventFilter:  # type: ignore[no-redef]
        def __init__(self) -> None:
            pass


SINGLE_INSTANCE_MUTEX_NAME = f"Local\\{PRODUCT_NAME}.GUI"
GUI_WINDOW_TITLE = "RefraTranslator · Prism Workbench"
ACTIVATION_WINDOW_TITLE = f"{PRODUCT_NAME} · activation target"
ACTIVATION_MESSAGE = 0x8000 + 0x52
STARTUP_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_VALUE_NAME = PRODUCT_NAME
DEFAULT_HOTKEY = "Ctrl+Alt+T"

_ERROR_ALREADY_EXISTS = 183
_ERROR_HOTKEY_ALREADY_REGISTERED = 1409
_WM_HOTKEY = 0x0312
_HOTKEY_ID = 0x5246
_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_WIN = 0x0008
_MOD_NOREPEAT = 0x4000
_ACTIVATION_RETRY_TIMEOUT_SECONDS = 2.0
_ACTIVATION_RETRY_INTERVAL_SECONDS = 0.05


class GuiRuntimeError(RuntimeError):
    """Raised when a Windows GUI integration cannot be installed."""


@dataclass(frozen=True, slots=True)
class HotkeySpec:
    """The display form and Win32 registration values for one hotkey."""

    display: str
    modifiers: int
    virtual_key: int


_MODIFIER_NAMES = {
    "ctrl": ("Ctrl", _MOD_CONTROL),
    "control": ("Ctrl", _MOD_CONTROL),
    "alt": ("Alt", _MOD_ALT),
    "shift": ("Shift", _MOD_SHIFT),
    "win": ("Win", _MOD_WIN),
    "windows": ("Win", _MOD_WIN),
}
_SPECIAL_KEYS = {
    "space": ("Space", 0x20),
    "tab": ("Tab", 0x09),
    "enter": ("Enter", 0x0D),
    "return": ("Enter", 0x0D),
    "esc": ("Esc", 0x1B),
    "escape": ("Esc", 0x1B),
    "backspace": ("Backspace", 0x08),
    "insert": ("Insert", 0x2D),
    "delete": ("Delete", 0x2E),
    "home": ("Home", 0x24),
    "end": ("End", 0x23),
    "pageup": ("PageUp", 0x21),
    "pagedown": ("PageDown", 0x22),
    "left": ("Left", 0x25),
    "right": ("Right", 0x27),
    "up": ("Up", 0x26),
    "down": ("Down", 0x28),
}


def parse_hotkey(value: str) -> HotkeySpec:
    """Parse a conservative, user-facing ``Ctrl+Alt+T`` hotkey string."""

    if not isinstance(value, str):
        raise GuiRuntimeError("全局快捷键必须是文本，例如 Ctrl+Alt+T")
    parts = tuple(part.strip() for part in value.split("+") if part.strip())
    if len(parts) < 2:
        raise GuiRuntimeError("全局快捷键必须包含修饰键和主键，例如 Ctrl+Alt+T")

    modifiers = 0
    seen_modifiers: set[int] = set()
    for raw_part in parts[:-1]:
        modifier = _MODIFIER_NAMES.get(raw_part.casefold())
        if modifier is None:
            raise GuiRuntimeError(f"未知快捷键修饰键：{raw_part}")
        label, flag = modifier
        if flag in seen_modifiers:
            raise GuiRuntimeError(f"快捷键修饰键重复：{label}")
        seen_modifiers.add(flag)
        modifiers |= flag

    raw_key = parts[-1]
    key_name = raw_key.casefold()
    key: tuple[str, int] | None = _SPECIAL_KEYS.get(key_name)
    if key is None and len(raw_key) == 1 and raw_key.isascii():
        if raw_key.isalpha() or raw_key.isdigit():
            key = (raw_key.upper(), ord(raw_key.upper()))
    if key is None and len(raw_key) >= 2 and raw_key[0].casefold() == "f":
        try:
            function_number = int(raw_key[1:])
        except ValueError:
            function_number = -1
        if 1 <= function_number <= 24:
            key = (f"F{function_number}", 0x70 + function_number - 1)
    if key is None:
        raise GuiRuntimeError(
            "未知快捷键主键；支持 A-Z、0-9、F1-F24、方向键和常用编辑键"
        )
    key_label, virtual_key = key
    # Canonical ordering makes the persisted setting and the UI stable even
    # when the user enters Shift+Ctrl+T.
    ordered = [
        label
        for label, flag in (
            ("Ctrl", _MOD_CONTROL),
            ("Alt", _MOD_ALT),
            ("Shift", _MOD_SHIFT),
            ("Win", _MOD_WIN),
        )
        if modifiers & flag
    ]
    return HotkeySpec("+".join((*ordered, key_label)), modifiers, virtual_key)


def startup_command(project_root: Path) -> str:
    """Return the per-user Run command that opens this project's GUI in tray."""

    batch = (project_root.resolve() / "start_gui.bat").resolve()
    # The outer quotes belong to cmd.exe's /c parsing; the inner quotes keep a
    # project path containing spaces valid.
    return f'cmd.exe /d /c ""{batch}" --startup"'


def _load_winreg():
    if sys.platform != "win32":
        raise GuiRuntimeError("开机启动只支持 Windows 10/11")
    try:
        import winreg
    except ImportError as exc:  # pragma: no cover - only possible on non-Windows
        raise GuiRuntimeError("当前 Python 不支持 Windows 注册表") from exc
    return winreg


def startup_enabled(project_root: Path | None = None) -> bool:
    """Read whether the product's current-user logon entry exists."""

    value = startup_entry()
    if value is None:
        return False
    if project_root is None:
        return bool(value)
    expected = startup_command(project_root)
    return value.casefold() == expected.casefold()


def startup_entry() -> str | None:
    """Return the exact current-user Run value for transaction rollback."""

    if sys.platform != "win32":
        return None
    winreg = _load_winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_PATH) as key:
            value, _kind = winreg.QueryValueEx(key, STARTUP_VALUE_NAME)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise GuiRuntimeError(f"读取开机启动设置失败：{exc}") from exc
    if not isinstance(value, str):
        raise GuiRuntimeError("开机启动注册表值不是文本")
    return value


def restore_startup_entry(value: str | None) -> None:
    """Restore an exact previously-read Run value, including its absence."""

    winreg = _load_winreg()
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            STARTUP_REGISTRY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if value is None:
                try:
                    key.DeleteValue(STARTUP_VALUE_NAME)
                except FileNotFoundError:
                    pass
            else:
                key.SetValueEx(STARTUP_VALUE_NAME, 0, winreg.REG_SZ, value)
    except OSError as exc:
        raise GuiRuntimeError(f"恢复开机启动设置失败：{exc}") from exc


def set_startup_enabled(project_root: Path, enabled: bool) -> str | None:
    """Create or remove the current-user logon entry without elevation."""

    winreg = _load_winreg()
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            STARTUP_REGISTRY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                command = startup_command(project_root)
                key.SetValueEx(STARTUP_VALUE_NAME, 0, winreg.REG_SZ, command)
                return command
            try:
                key.DeleteValue(STARTUP_VALUE_NAME)
            except FileNotFoundError:
                pass
    except OSError as exc:
        action = "开启" if enabled else "关闭"
        raise GuiRuntimeError(f"{action}开机启动失败：{exc}") from exc
    return None


class SingleInstanceGuard:
    """Hold a named mutex for the complete launcher process lifetime."""

    def __init__(self, name: str = SINGLE_INSTANCE_MUTEX_NAME) -> None:
        self.name = name
        self._handle: int | None = None
        self._owns_mutex = False

    def acquire(self) -> bool:
        if sys.platform != "win32":
            self._owns_mutex = True
            return True
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = (
            ctypes.c_void_p,
            ctypes.c_bool,
            ctypes.c_wchar_p,
        )
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.GetLastError.restype = ctypes.c_uint32
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            raise GuiRuntimeError("无法建立 GUI 单实例互斥体")
        self._handle = int(handle)
        if int(kernel32.GetLastError()) == _ERROR_ALREADY_EXISTS:
            self.release()
            return False
        self._owns_mutex = True
        return True

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        self._owns_mutex = False
        if handle is not None and sys.platform == "win32":
            try:
                ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))
            except (AttributeError, OSError):
                pass

    def __enter__(self) -> "SingleInstanceGuard":
        if not self.acquire():
            raise GuiRuntimeError("GUI 已在运行")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def activate_existing_window(
    *,
    timeout_seconds: float = _ACTIVATION_RETRY_TIMEOUT_SECONDS,
    retry_interval_seconds: float = _ACTIVATION_RETRY_INTERVAL_SECONDS,
) -> bool:
    """Ask the surviving activation target to restore the workbench."""

    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        user32.FindWindowW.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.PostMessageW.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        user32.PostMessageW.restype = ctypes.c_bool
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        interval = max(0.0, retry_interval_seconds)
        while True:
            hwnd = user32.FindWindowW(None, ACTIVATION_WINDOW_TITLE)
            if hwnd and user32.PostMessageW(hwnd, ACTIVATION_MESSAGE, 0, 0):
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0 or interval <= 0:
                return False
            time.sleep(min(interval, remaining))
    except (AttributeError, OSError, TypeError, ValueError):
        return False


class WindowsGlobalHotkey(QAbstractNativeEventFilter):
    """Register one process-wide hotkey through Qt's native message queue."""

    def __init__(
        self,
        application,
        callback: Callable[[], None],
        error_callback: Callable[[str], None],
        *,
        hotkey_id: int = _HOTKEY_ID,
    ) -> None:
        super().__init__()
        self._application = application
        self._callback = callback
        self._error_callback = error_callback
        self._hotkey_id = hotkey_id
        self._registered = False
        self._spec: HotkeySpec | None = None
        self._native_filter_installed = False

    @property
    def registered(self) -> bool:
        return self._registered

    @property
    def spec(self) -> HotkeySpec | None:
        return self._spec

    def _supported(self) -> bool:
        try:
            return (
                sys.platform == "win32"
                and self._application.platformName() == "windows"
            )
        except (AttributeError, RuntimeError):
            return False

    @staticmethod
    def _user32_api():
        loader = getattr(ctypes, "WinDLL", None)
        if loader is not None:
            return loader("user32", use_last_error=True)
        return ctypes.windll.user32

    @staticmethod
    def _set_api_signature(function, argtypes, restype) -> None:
        function.argtypes = argtypes
        function.restype = restype

    def _unregister_native(self) -> None:
        if not self._registered or sys.platform != "win32":
            return
        user32 = self._user32_api()
        unregister = user32.UnregisterHotKey
        self._set_api_signature(
            unregister,
            (ctypes.c_void_p, ctypes.c_int),
            ctypes.c_bool,
        )
        unregister(None, self._hotkey_id)

    def _register_native(self, spec: HotkeySpec) -> None:
        user32 = self._user32_api()
        register = user32.RegisterHotKey
        self._set_api_signature(
            register,
            (ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint),
            ctypes.c_bool,
        )
        if register(
            None,
            self._hotkey_id,
            spec.modifiers | _MOD_NOREPEAT,
            spec.virtual_key,
        ):
            return
        error = ctypes.get_last_error()
        if error == _ERROR_HOTKEY_ALREADY_REGISTERED:
            raise GuiRuntimeError(f"快捷键 {spec.display} 已被其他程序占用")
        raise GuiRuntimeError(f"注册快捷键 {spec.display} 失败（错误码 {error}）")

    def register(self, value: str) -> bool:
        spec = parse_hotkey(value)
        if self._registered and self._spec == spec:
            return True
        previous_spec = self._spec
        previous_registered = self._registered
        self._unregister_native()
        self._registered = False
        self._spec = None
        if not self._supported():
            self._spec = spec
            return False
        try:
            self._register_native(spec)
            self._registered = True
            self._spec = spec
            install_filter = getattr(
                self._application,
                "installNativeEventFilter",
                None,
            )
            if callable(install_filter) and not self._native_filter_installed:
                install_filter(self)
                self._native_filter_installed = True
            return True
        except Exception:
            if self._registered:
                try:
                    self._unregister_native()
                except (AttributeError, OSError, TypeError, ValueError):
                    pass
            self._registered = False
            self._spec = None
            if previous_registered and previous_spec is not None:
                try:
                    self._register_native(previous_spec)
                    self._registered = True
                    self._spec = previous_spec
                    if not self._native_filter_installed:
                        install_filter = getattr(
                            self._application,
                            "installNativeEventFilter",
                            None,
                        )
                        if callable(install_filter):
                            install_filter(self)
                            self._native_filter_installed = True
                except Exception:
                    self._registered = False
                    self._spec = None
            raise

    def unregister(self) -> None:
        try:
            self._unregister_native()
        except (AttributeError, OSError, TypeError, ValueError):
            pass
        if self._native_filter_installed:
            remove_filter = getattr(self._application, "removeNativeEventFilter", None)
            if callable(remove_filter):
                remove_filter(self)
            self._native_filter_installed = False
        self._registered = False
        self._spec = None

    def nativeEventFilter(self, _event_type, message):  # noqa: N802
        if not self._registered or sys.platform != "win32":
            return False, 0
        try:
            pointer = int(message)
            if pointer == 0:
                return False, 0
            # MSG is ABI-stable on Windows for the fields used here.
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
            if native.message != _WM_HOTKEY or native.wParam != self._hotkey_id:
                return False, 0
            self._callback()
            return True, 0
        except (TypeError, ValueError, OSError):
            return False, 0

    def close(self) -> None:
        self.unregister()


__all__ = [
    "DEFAULT_HOTKEY",
    "ACTIVATION_MESSAGE",
    "ACTIVATION_WINDOW_TITLE",
    "GUI_WINDOW_TITLE",
    "GuiRuntimeError",
    "HotkeySpec",
    "SingleInstanceGuard",
    "WindowsGlobalHotkey",
    "activate_existing_window",
    "parse_hotkey",
    "set_startup_enabled",
    "restore_startup_entry",
    "startup_command",
    "startup_entry",
    "startup_enabled",
]

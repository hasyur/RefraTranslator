from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from game_screen_translator.gui import runtime


def test_parse_hotkey_canonicalizes_modifiers_and_accepts_function_keys() -> None:
    assert runtime.parse_hotkey("Shift+Ctrl+T") == runtime.HotkeySpec(
        "Ctrl+Shift+T", 0x0002 | 0x0004, ord("T")
    )
    assert runtime.parse_hotkey("ctrl+alt+f8").display == "Ctrl+Alt+F8"


@pytest.mark.parametrize("value", ("T", "Ctrl", "Ctrl+Ctrl+T", "Meta+T", "Ctrl+F25"))
def test_parse_hotkey_rejects_ambiguous_or_unsupported_values(value: str) -> None:
    with pytest.raises(runtime.GuiRuntimeError):
        runtime.parse_hotkey(value)


def test_startup_registry_round_trip_uses_the_project_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Key:
        def __init__(self, values: dict[str, str]) -> None:
            self.values = values

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def SetValueEx(self, name, _reserved, _kind, value):  # noqa: N802
            self.values[name] = value

        def DeleteValue(self, name):  # noqa: N802
            if name not in self.values:
                raise FileNotFoundError(name)
            del self.values[name]

    values: dict[str, str] = {}

    class Winreg:
        HKEY_CURRENT_USER = object()
        KEY_SET_VALUE = 2
        REG_SZ = 1

        @staticmethod
        def CreateKeyEx(*_args):  # noqa: N802
            return Key(values)

        @staticmethod
        def OpenKey(*_args):  # noqa: N802
            if not values:
                raise FileNotFoundError
            return Key(values)

        @staticmethod
        def QueryValueEx(key, name):  # noqa: N802
            return key.values[name], 1

    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setattr(runtime, "_load_winreg", lambda: Winreg)

    command = runtime.set_startup_enabled(tmp_path, True)
    assert command == runtime.startup_command(tmp_path)
    assert values[runtime.STARTUP_VALUE_NAME] == command
    assert runtime.startup_enabled(tmp_path)

    runtime.set_startup_enabled(tmp_path, False)
    assert not values
    assert not runtime.startup_enabled(tmp_path)


def test_single_instance_guard_is_releasable_outside_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    guard = runtime.SingleInstanceGuard("test")
    assert guard.acquire()
    guard.release()


def test_second_launcher_activates_existing_window_and_skips_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activated: list[bool] = []

    class ExistingGuard:
        def acquire(self) -> bool:
            return False

        def release(self) -> None:
            activated.append(True)

    monkeypatch.setattr("game_screen_translator.gui_entry.SingleInstanceGuard", ExistingGuard)
    monkeypatch.setattr(
        "game_screen_translator.gui_entry.activate_existing_window",
        lambda: activated.append(True) or True,
    )
    monkeypatch.setattr(
        "game_screen_translator.gui_entry._run_owned",
        lambda *_args, **_kwargs: pytest.fail("second launcher must not start a worker"),
    )

    from game_screen_translator import gui_entry

    assert gui_entry.run(project_root=Path(".")) == 0
    assert activated == [True, True]


def test_activation_retries_until_existing_target_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NativeFunction:
        def __init__(self, callback):
            self._callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            return self._callback(*args)

    class User32:
        def __init__(self) -> None:
            self.find_calls = 0
            self.posted: list[tuple[int, int]] = []
            self.FindWindowW = NativeFunction(self._find_window)  # noqa: N802
            self.PostMessageW = NativeFunction(self._post_message)  # noqa: N802
            self.ShowWindow = NativeFunction(lambda *_args: True)  # noqa: N802
            self.SetForegroundWindow = NativeFunction(  # noqa: N802
                lambda *_args: True,
            )

        def _find_window(self, _class_name, title):
            self.find_calls += 1
            if (
                title == runtime.ACTIVATION_WINDOW_TITLE
                and self.find_calls >= 4
            ):
                return 123
            return 0

        def _post_message(self, hwnd, message, _wparam, _lparam):
            self.posted.append((hwnd, message))
            return True

    user32 = User32()
    sleeps: list[float] = []
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setattr(runtime.ctypes, "windll", SimpleNamespace(user32=user32))
    monkeypatch.setattr(runtime.time, "sleep", sleeps.append)

    assert runtime.activate_existing_window(
        timeout_seconds=1.0,
        retry_interval_seconds=0.01,
    )
    assert user32.posted == [(123, runtime.ACTIVATION_MESSAGE)]
    assert sleeps


def test_activation_timeout_is_reported_without_starting_another_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activated: list[bool] = []
    failures: list[str] = []

    class ExistingGuard:
        def acquire(self) -> bool:
            return False

        def release(self) -> None:
            activated.append(True)

    monkeypatch.setattr("game_screen_translator.gui_entry.SingleInstanceGuard", ExistingGuard)
    monkeypatch.setattr(
        "game_screen_translator.gui_entry.activate_existing_window",
        lambda: False,
    )
    monkeypatch.setattr(
        "game_screen_translator.gui_entry._show_failure",
        failures.append,
    )

    from game_screen_translator import gui_entry

    assert gui_entry.run(project_root=Path(".")) == 1
    assert activated == [True]
    assert failures == [
        "RefraTranslator is already running but did not become ready "
        "within the activation timeout."
    ]


def test_hotkey_registration_reports_windows_conflict_without_external_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NativeFunction:
        def __init__(self, callback):
            self._callback = callback
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            return self._callback(*args)

    class User32:
        def __init__(self) -> None:
            self.registered: set[tuple[int, int]] = set()
            self.RegisterHotKey = NativeFunction(self._register)  # noqa: N802
            self.UnregisterHotKey = NativeFunction(self._unregister)  # noqa: N802

        def _register(self, _hwnd, hotkey_id, _modifiers, virtual_key):
            if virtual_key == ord("G"):
                # This exercises ctypes' real thread-local last-error API;
                # the production code must not rely on a patched reader.
                runtime.ctypes.set_last_error(1409)
                return False
            self.registered.add((hotkey_id, virtual_key))
            return True

        def _unregister(self, _hwnd, hotkey_id):
            self.registered = {
                registration
                for registration in self.registered
                if registration[0] != hotkey_id
            }
            return True

    class Application:
        def platformName(self):  # noqa: N802
            return "windows"

        def installNativeEventFilter(self, event_filter):  # noqa: N802
            self.event_filter = event_filter

        def removeNativeEventFilter(self, _event_filter):  # noqa: N802
            return None

    monkeypatch.setattr(runtime.sys, "platform", "win32")
    user32 = User32()
    monkeypatch.setattr(
        runtime.WindowsGlobalHotkey,
        "_user32_api",
        staticmethod(lambda: user32),
    )
    errors: list[str] = []
    hotkey = runtime.WindowsGlobalHotkey(Application(), lambda: None, errors.append)

    assert hotkey.register("Ctrl+Alt+T")
    assert hotkey.spec is not None
    assert hotkey.spec.display == "Ctrl+Alt+T"
    assert (hotkey._hotkey_id, ord("T")) in user32.registered

    with pytest.raises(runtime.GuiRuntimeError, match="已被其他程序占用"):
        hotkey.register("Ctrl+Alt+G")

    assert hotkey.spec is not None
    assert hotkey.spec.display == "Ctrl+Alt+T"
    assert (hotkey._hotkey_id, ord("T")) in user32.registered
    assert (hotkey._hotkey_id, ord("G")) not in user32.registered
    assert user32.RegisterHotKey.argtypes == (
        runtime.ctypes.c_void_p,
        runtime.ctypes.c_int,
        runtime.ctypes.c_uint,
        runtime.ctypes.c_uint,
    )


def test_hotkey_native_filter_returns_qt_tuple_when_unbound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Application:
        def platformName(self):  # noqa: N802
            return "windows"

    monkeypatch.setattr(runtime.sys, "platform", "win32")
    hotkey = runtime.WindowsGlobalHotkey(Application(), lambda: None, lambda _: None)

    assert hotkey.nativeEventFilter(b"windows_dispatcher_MSG", 0) == (False, 0)

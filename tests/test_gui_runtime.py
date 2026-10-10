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


def test_hotkey_registration_reports_windows_conflict_without_external_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class User32:
        def RegisterHotKey(self, *_args):  # noqa: N802
            return False

        def UnregisterHotKey(self, *_args):  # noqa: N802
            return True

    class Application:
        def platformName(self):  # noqa: N802
            return "windows"

        def installNativeEventFilter(self, event_filter):  # noqa: N802
            self.event_filter = event_filter

        def removeNativeEventFilter(self, _event_filter):  # noqa: N802
            return None

    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setattr(runtime.ctypes, "windll", SimpleNamespace(user32=User32()))
    monkeypatch.setattr(runtime.ctypes, "get_last_error", lambda: 1409)
    errors: list[str] = []
    hotkey = runtime.WindowsGlobalHotkey(Application(), lambda: None, errors.append)

    with pytest.raises(runtime.GuiRuntimeError, match="已被其他程序占用"):
        hotkey.register("Ctrl+Alt+T")

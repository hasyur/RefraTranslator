from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from game_screen_translator import gui_entry


def test_pythonw_entry_does_not_mirror_output_to_the_parent_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gui_entry.sys, "executable", "C:/Python/pythonw.exe")

    assert gui_entry._default_mirror() is None


def test_shared_gui_backend_runs_probe_and_gui_with_the_same_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "config.example.toml").write_text("example = true\n", encoding="utf-8")
    worker = tmp_path / ".venv" / "Scripts" / "python.exe"
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []

    monkeypatch.setattr(gui_entry, "_worker_python", lambda: worker)

    def fake_run_logged(command, **kwargs) -> int:
        commands.append([str(argument) for argument in command])
        environments.append(kwargs["environment"])
        return 0

    monkeypatch.setattr(gui_entry, "_run_logged", fake_run_logged)
    mirror = StringIO()

    assert (
        gui_entry.run(
            ["--duration", "0.25"],
            project_root=tmp_path,
            mirror=mirror,
        )
        == 0
    )

    assert (tmp_path / "config.toml").read_text(encoding="utf-8") == (
        "example = true\n"
    )
    assert len(commands) == 2
    assert commands[0][0] == commands[1][0] == str(worker)
    assert commands[0][-2] == "-c"
    assert "QApplication([])" in commands[0][-1]
    assert commands[1][-6:] == [
        "game_screen_translator",
        "--config",
        str(tmp_path / "config.toml"),
        "gui",
        "--duration",
        "0.25",
    ]
    assert environments[0] is environments[1]
    assert environments[0]["QT_QPA_PLATFORM"] == "windows"
    assert environments[0]["QT_PLUGIN_PATH"] == ""

    log = (tmp_path / "output" / "launcher.log").read_text(encoding="utf-8")
    assert "RefraTranslator launcher diagnostics" in log
    assert "Checking the isolated Python and GUI dependencies" in log
    assert "Starting RefraTranslator GUI" in log
    assert "Starting RefraTranslator GUI" in mirror.getvalue()


def test_shared_gui_backend_stops_after_a_failed_dependency_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "config.toml").write_text("local = true\n", encoding="utf-8")
    monkeypatch.setattr(
        gui_entry,
        "_worker_python",
        lambda: tmp_path / ".venv" / "Scripts" / "python.exe",
    )
    commands: list[list[str]] = []

    def fail_probe(command, **_kwargs) -> int:
        commands.append([str(argument) for argument in command])
        return 7

    monkeypatch.setattr(gui_entry, "_run_logged", fail_probe)

    assert gui_entry.run(project_root=tmp_path, mirror=StringIO()) == 7
    assert len(commands) == 1
    assert commands[0][-2] == "-c"
    log = (tmp_path / "output" / "launcher.log").read_text(encoding="utf-8")
    assert "Dependency check failed with code 7" in log

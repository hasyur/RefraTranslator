"""Shared Windows GUI startup backend for normal and debug entry points."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Sequence, TextIO


_GUI_DEPENDENCY_PROBE = (
    "import sys; "
    "print('Python:', sys.version, flush=True); "
    "print('Executable:', sys.executable, flush=True); "
    "import PySide6; "
    "print('PySide6:', PySide6.__version__, flush=True); "
    "from PySide6.QtWidgets import QApplication; "
    "from PySide6.QtQml import QQmlApplicationEngine; "
    "from PySide6.QtQuick import QQuickWindow; "
    "from PySide6.QtQuickControls2 import QQuickStyle; "
    "print('Qt Quick/QML imports: OK', flush=True); "
    "app = QApplication([]); "
    "print('Qt platform:', app.platformName(), flush=True); "
    "import game_screen_translator.gui.qml_workbench; "
    "print('QML workbench module import: OK', flush=True)"
)


def _emit(log: TextIO, mirror: TextIO | None, text: str = "") -> None:
    line = f"{text}\n"
    log.write(line)
    log.flush()
    if mirror is not None:
        mirror.write(line)
        mirror.flush()


def _emit_child_output(
    log: TextIO,
    mirror: TextIO | None,
    text: str,
) -> None:
    log.write(text)
    log.flush()
    if mirror is not None:
        mirror.write(text)
        mirror.flush()


def _worker_python() -> Path:
    executable = Path(sys.executable).resolve()
    worker = executable.with_name("python.exe") if os.name == "nt" else executable
    if not worker.is_file():
        raise FileNotFoundError(f"Python worker not found: {worker}")
    return worker


def _worker_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONFAULTHANDLER": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8": "1",
            "QT_QPA_PLATFORM": "windows",
            "QT_PLUGIN_PATH": "",
            "QT_QPA_PLATFORM_PLUGIN_PATH": "",
        }
    )
    return environment


def _prepare_config(project_root: Path) -> Path:
    config_path = project_root / "config.toml"
    if config_path.is_file():
        return config_path

    template_path = project_root / "config.example.toml"
    if not template_path.is_file():
        raise FileNotFoundError(f"Configuration template not found: {template_path}")
    shutil.copyfile(template_path, config_path)
    return config_path


def _run_logged(
    command: Sequence[str],
    *,
    project_root: Path,
    environment: dict[str, str],
    log: TextIO,
    mirror: TextIO | None,
) -> int:
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        [str(argument) for argument in command],
        cwd=project_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
    )
    assert process.stdout is not None
    with process.stdout:
        for line in process.stdout:
            _emit_child_output(log, mirror, line)
    return process.wait()


def _show_failure(message: str) -> None:
    if os.name != "nt":
        return
    ctypes.windll.user32.MessageBoxW(0, message, "RefraTranslator", 0x10)


def _default_mirror() -> TextIO | None:
    if Path(sys.executable).name.casefold() == "pythonw.exe":
        return None
    return sys.stdout


def run(
    arguments: Sequence[str] | None = None,
    *,
    project_root: Path | None = None,
    mirror: TextIO | None = None,
) -> int:
    root = (project_root or Path.cwd()).resolve()
    output_dir = root / "output"
    log_path = output_dir / "launcher.log"
    console = _default_mirror() if mirror is None else mirror

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        log = log_path.open("w", encoding="utf-8", buffering=1)
    except OSError as exc:
        if console is not None:
            console.write(f"RefraTranslator launcher failed: {exc}\n")
            console.flush()
        else:
            _show_failure(f"RefraTranslator could not start.\n\n{exc}")
        return 1

    exit_code = 1
    with log:
        try:
            _emit(log, console, "RefraTranslator launcher diagnostics")
            _emit(log, console, f"Working directory: {root}")
            config_path = _prepare_config(root)
            worker = _worker_python()
            environment = _worker_environment()

            _emit(log, console, "Checking the isolated Python and GUI dependencies...")
            exit_code = _run_logged(
                [
                    str(worker),
                    "-u",
                    "-X",
                    "utf8",
                    "-X",
                    "faulthandler",
                    "-c",
                    _GUI_DEPENDENCY_PROBE,
                ],
                project_root=root,
                environment=environment,
                log=log,
                mirror=console,
            )
            if exit_code != 0:
                _emit(log, console, f"Dependency check failed with code {exit_code}.")
            else:
                _emit(log, console, "Starting RefraTranslator GUI...")
                exit_code = _run_logged(
                    [
                        str(worker),
                        "-u",
                        "-X",
                        "utf8",
                        "-X",
                        "faulthandler",
                        "-m",
                        "game_screen_translator",
                        "--config",
                        str(config_path),
                        "gui",
                        *(arguments if arguments is not None else sys.argv[1:]),
                    ],
                    project_root=root,
                    environment=environment,
                    log=log,
                    mirror=console,
                )
                if exit_code != 0:
                    _emit(log, console, f"GUI exited unexpectedly with code {exit_code}.")
        except Exception:
            _emit_child_output(log, console, traceback.format_exc())
            exit_code = 1

    if exit_code != 0 and console is None:
        _show_failure(
            "RefraTranslator could not start "
            f"(exit code {exit_code}).\n\nDiagnostic log:\n{log_path}"
        )
    return exit_code


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())

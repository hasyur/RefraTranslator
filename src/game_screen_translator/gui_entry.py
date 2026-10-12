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

from game_screen_translator.gui.runtime import (
    SingleInstanceGuard,
    activate_existing_window,
)


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


def _prepare_config(project_root: Path, template_root: Path | None = None) -> Path:
    config_path = project_root / "config.toml"
    if config_path.is_file():
        return config_path

    template_path = (template_root or project_root) / "config.example.toml"
    if not template_path.is_file():
        raise FileNotFoundError(f"Configuration template not found: {template_path}")
    shutil.copyfile(template_path, config_path)
    return config_path


def _install_root() -> Path:
    override = os.environ.get("REFRATRANSLATOR_INSTALL_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    executable = Path(sys.executable).resolve()
    # The relocatable Python runtime lives in {app}\\runtime.
    return executable.parent.parent


def _installed_data_root(install_root: Path) -> Path:
    override = os.environ.get("REFRATRANSLATOR_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    default_root = (
        Path(local_app_data).expanduser()
        if local_app_data
        else Path.home() / "AppData" / "Local"
    ) / "RefraTranslator"
    # Preserve an existing portable install's config, profiles and cache in
    # place when setup is run over that directory. The source remains intact.
    if (default_root / "config.toml").is_file():
        return default_root.resolve()
    if (install_root / "config.toml").is_file():
        return install_root.resolve()
    cwd = Path.cwd().resolve()
    if cwd != install_root and (cwd / "config.toml").is_file():
        return cwd
    return default_root.resolve()


def _duration_argument(arguments: Sequence[str]) -> str | None:
    for index, argument in enumerate(arguments):
        if argument == "--duration" and index + 1 < len(arguments):
            return arguments[index + 1]
        if argument.startswith("--duration="):
            return argument.partition("=")[2]
    return None


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


def _run_owned(
    arguments: Sequence[str] | None = None,
    *,
    project_root: Path | None = None,
    mirror: TextIO | None = None,
    installed: bool = False,
) -> int:
    install_root = (project_root or _install_root()).resolve() if installed else None
    root = (
        _installed_data_root(install_root)
        if installed and install_root is not None
        else (project_root or Path.cwd()).resolve()
    )
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
            config_path = _prepare_config(root, install_root)
            worker = _worker_python()
            environment = _worker_environment()
            if installed:
                environment.update(
                    {
                        "REFRATRANSLATOR_INSTALLED": "1",
                        "REFRATRANSLATOR_INSTALL_DIR": str(install_root),
                        "REFRATRANSLATOR_DATA_DIR": str(root),
                    }
                )

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
                if installed:
                    _emit(log, console, "Checking first-run OCR resources...")
                    first_run_command = [
                        str(worker),
                        "-u",
                        "-X",
                        "utf8",
                        "-X",
                        "faulthandler",
                        "-m",
                        "game_screen_translator.first_run",
                        "--config",
                        str(config_path),
                    ]
                    duration = _duration_argument(arguments or ())
                    if duration is not None:
                        first_run_command.extend(("--duration", duration))
                    exit_code = _run_logged(
                        first_run_command,
                        project_root=install_root,
                        environment=environment,
                        log=log,
                        mirror=console,
                    )
                if exit_code == 0:
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
                        project_root=root if not installed else install_root,
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


def run(
    arguments: Sequence[str] | None = None,
    *,
    project_root: Path | None = None,
    mirror: TextIO | None = None,
) -> int:
    """Run one launcher, foregrounding the existing GUI on a second start."""

    guard = SingleInstanceGuard()
    try:
        if not guard.acquire():
            if activate_existing_window():
                return 0
            _show_failure(
                "RefraTranslator is already running but did not become ready "
                "within the activation timeout."
            )
            return 1
        values = list(sys.argv[1:] if arguments is None else arguments)
        installed = "--installed" in values
        values = [value for value in values if value != "--installed"]
        return _run_owned(
            values,
            project_root=project_root,
            mirror=mirror,
            installed=installed,
        )
    finally:
        guard.release()


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())

"""Install the smoke EXE and verify its own runtime and GUI in a fresh directory."""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pip._vendor.packaging.utils import canonicalize_name

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_metadata import load_core_requirements, read_version


ROOT = Path(__file__).resolve().parents[1]


class VerificationError(RuntimeError):
    pass


def _isolated_environment(run_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.upper().startswith(("PYTHON", "QT_", "CONDA", "REFRATRANSLATOR_")):
            environment.pop(key)
    environment.pop("VIRTUAL_ENV", None)
    windows = Path(environment.get("WINDIR", r"C:\Windows"))
    environment.update({
        "PATH": os.pathsep.join((str(windows / "System32"), str(windows))),
        "USERPROFILE": str(run_root / "user"),
        "LOCALAPPDATA": str(run_root / "user" / "AppData" / "Local"),
        "APPDATA": str(run_root / "user" / "AppData" / "Roaming"),
        "TEMP": str(run_root / "temp"),
        "TMP": str(run_root / "temp"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
        "QT_QPA_PLATFORM": "windows",
        "QT_PLUGIN_PATH": "",
        "QT_QPA_PLATFORM_PLUGIN_PATH": "",
    })
    for key in ("USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP"):
        Path(environment[key]).mkdir(parents=True, exist_ok=True)
    return environment


def _run(
    command: list[str], *, cwd: Path, environment: dict[str, str],
    timeout: float, log_path: Path,
) -> str:
    # A Windows job owns the launcher and its Python children, even when taskkill
    # cannot enumerate processes (for example, inside a restricted runner).
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command, cwd=cwd, env=environment, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        job = _own_process_tree(process) if os.name == "nt" else None
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            if job is not None:
                kernel, handle = job
                if not kernel.TerminateJobObject(handle, 1):
                    process.kill()
            else:
                process.kill()
            process.wait(timeout=15)
            raise VerificationError(f"Timed out: {command[0]}; see {log_path}") from exc
        finally:
            if job is not None:
                kernel, handle = job
                kernel.CloseHandle(handle)
    output = log_path.read_text(encoding="utf-8", errors="replace")
    if code != 0:
        raise VerificationError(f"Exit code {code}: {command[0]}; see {log_path}\n{output}")
    return output


def _own_process_tree(process: subprocess.Popen) -> tuple:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel.TerminateJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateJobObjectW(None, None)
    if not handle or not kernel.AssignProcessToJobObject(handle, int(process._handle)):
        error = ctypes.get_last_error()
        if handle:
            kernel.CloseHandle(handle)
        process.kill()
        process.wait(timeout=15)
        raise VerificationError(f"Could not isolate the verification process tree: Windows error {error}")
    return kernel, handle


_RUNTIME_PROBE = """
import hashlib, importlib.metadata as metadata, json, sys
from pathlib import Path
import httpx, numpy, PIL, PySide6, dxcam
import game_screen_translator as package
pins = __PINS__
dependencies = {}
for name in pins:
    distribution = metadata.distribution(name)
    dependencies[name] = {
        'version': distribution.version,
        'location': str(Path(distribution.locate_file('')).resolve()),
    }
manifest = Path(package.__file__).with_name('ocr_wheel_manifest.json')
print(json.dumps({
    'version': package.__version__,
    'executable': sys.executable,
    'package_file': package.__file__,
    'dependencies': dependencies,
    'ocr_manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
}))
"""


def _check_probe(payload: dict, install_root: Path, pins: dict[str, str]) -> None:
    expected_version = read_version(ROOT)
    if payload["version"] != expected_version:
        raise VerificationError(f"Installed application version differs from {expected_version}")
    if Path(payload["executable"]).resolve() != install_root / "runtime" / "python.exe":
        raise VerificationError("Probe used a Python outside the installed runtime")
    if not Path(payload["package_file"]).resolve().is_relative_to(install_root):
        raise VerificationError("Probe imported the application outside the install directory")
    for name, expected in pins.items():
        dependency = payload["dependencies"].get(name, {})
        if dependency.get("version") != expected:
            raise VerificationError(f"Installed dependency {name} differs from fixed version {expected}")
        if not Path(dependency["location"]).resolve().is_relative_to(install_root):
            raise VerificationError(f"Installed dependency {name} came from outside the install directory")
    manifest = ROOT / "packaging" / "ocr_wheel_manifest.json"
    if payload["ocr_manifest_sha256"] != hashlib.sha256(manifest.read_bytes()).hexdigest():
        raise VerificationError("Installed OCR manifest differs from the release manifest")


def _check_launcher_log(log_path: Path, runtime_python: Path) -> None:
    if not log_path.is_file():
        raise VerificationError("Installed launcher did not create its diagnostic log")
    log = log_path.read_text(encoding="utf-8", errors="replace")
    required = (
        f"Executable: {runtime_python}",
        "QML workbench module import: OK",
        "Checking first-run OCR resources...",
        "Starting RefraTranslator GUI...",
        "showing native QML workbench",
        "event loop ready; visible=True",
        "event loop exited with code 0",
    )
    for marker in required:
        if marker not in log:
            raise VerificationError(f"Launcher log is missing {marker!r}; see {log_path}")
    if "Traceback (most recent call last)" in log:
        raise VerificationError(f"Launcher log contains a traceback; see {log_path}")


def verify(installer: Path, work_dir: Path, *, duration: float = 1, timeout: float = 120) -> dict:
    if os.name != "nt":
        raise VerificationError("The installer verification requires Windows x64")
    if not math.isfinite(duration) or not math.isfinite(timeout) or duration <= 0 or timeout <= 0:
        raise VerificationError("Duration and timeout must be positive finite seconds")
    installer = installer.expanduser().resolve()
    if not installer.is_file():
        raise VerificationError(f"Installer not found: {installer}")
    # This build variant shares the production payload and leaves no registry/shortcut entries.
    if installer.name != "RefraTranslator-Portable-Smoke.exe":
        raise VerificationError("Use RefraTranslator-Portable-Smoke.exe for an isolated installation")
    work_dir = work_dir.expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(prefix="run-", dir=work_dir)).resolve()
    install_root = run_root / "安装目录 with spaces"
    environment = _isolated_environment(run_root)
    report = {"status": "failed", "installer": str(installer), "run_root": str(run_root)}
    install_command = [
        str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
        f"/DIR={install_root}",
    ]
    try:
        _run(
            [*install_command, f"/LOG={run_root / 'install.log'}"],
            cwd=run_root, environment=environment, timeout=timeout,
            log_path=run_root / "installer-output.log",
        )
        runtime_python = install_root / "runtime" / "python.exe"
        launcher = install_root / "RefraTranslator.exe"
        if not runtime_python.is_file() or not launcher.is_file():
            raise VerificationError("Installer did not create the application launcher and embedded runtime")
        pins = {}
        for requirement in load_core_requirements(ROOT):
            pins[canonicalize_name(requirement.name)] = next(iter(requirement.specifier)).version
        probe_output = _run(
            [str(runtime_python), "-I", "-c", _RUNTIME_PROBE.replace("__PINS__", repr(pins))],
            cwd=run_root, environment=environment, timeout=timeout,
            log_path=run_root / "runtime-probe.log",
        )
        probe = json.loads(probe_output.strip().splitlines()[-1])
        _check_probe(probe, install_root, pins)
        _run(
            [str(runtime_python), "-I", "-m", "pip", "check"],
            cwd=run_root, environment=environment, timeout=timeout,
            log_path=run_root / "pip-check.log",
        )
        _run(
            [str(launcher), "--duration", str(duration)],
            cwd=run_root, environment=environment, timeout=timeout,
            log_path=run_root / "launcher-output.log",
        )
        data_root = install_root
        config_path = data_root / "config.toml"
        if not config_path.is_file():
            raise VerificationError("Installed launcher did not prepare an isolated user configuration")
        if (Path(environment["LOCALAPPDATA"]) / "RefraTranslator").exists():
            raise VerificationError("Installed launcher unexpectedly wrote to the legacy user-data directory")
        _check_launcher_log(data_root / "output" / "launcher.log", runtime_python)
        # The first-run dialog was deferred. No model or GPU wheel download should have started.
        resource_directories = ("ocr-wheelhouse", "paddlex", "local-llm")
        if any(
            path.is_file()
            for directory in resource_directories
            for path in (data_root / ".cache" / directory).rglob("*")
        ):
            raise VerificationError("Startup smoke test unexpectedly downloaded resources")

        # User-created files must survive replacement of the application payload.
        preserved = {
            config_path: config_path.read_bytes() + b"\n# Reinstall preservation probe\n",
            data_root / "output" / "launcher.log": (data_root / "output" / "launcher.log").read_bytes(),
            data_root / "profiles" / "install-verification.keep": b"user profile data",
            data_root / ".cache" / "local-llm" / "models" / "install-verification.keep": b"downloaded model data",
            runtime_python.parent / "Lib" / "site-packages" / "install-verification.keep": b"first-run runtime payload",
        }
        for path, payload in preserved.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        _run(
            [*install_command, f"/LOG={run_root / 'reinstall.log'}"],
            cwd=run_root, environment=environment, timeout=timeout,
            log_path=run_root / "reinstaller-output.log",
        )
        for path, expected in preserved.items():
            if not path.is_file() or path.read_bytes() != expected:
                raise VerificationError(f"Reinstallation changed user data: {path}")
        report.update({"status": "passed", "runtime": probe, "install_root": str(install_root),
                       "data_root": str(data_root), "duration_seconds": duration,
                       "reinstall_preserved_paths": [str(path) for path in preserved]})
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        report_path = run_root / "verification-report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Installation verification report: {report_path}", flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--work-dir", type=Path, default=ROOT / "build" / "windows-install-validation")
    parser.add_argument("--duration", type=float, default=1)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    try:
        report = verify(args.installer, args.work_dir, duration=args.duration, timeout=args.timeout)
    except (VerificationError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Installation verification failed: {exc}\n")
    # Hosted Windows runners may pipe stdout through a legacy code page.
    # Keep console JSON ASCII-safe; the retained UTF-8 report preserves names.
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

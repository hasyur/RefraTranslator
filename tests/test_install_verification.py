from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from game_screen_translator import __version__


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "refra_verify_windows_install", ROOT / "packaging" / "verify_windows_install.py"
)
assert spec is not None and spec.loader is not None
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def test_verification_environment_cannot_use_development_python_or_user_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "C:/development/Python")
    monkeypatch.setenv("PYTHONPATH", "C:/development/src")
    monkeypatch.setenv("PYTHONHOME", "C:/development/Python")
    monkeypatch.setenv("VIRTUAL_ENV", "C:/development/venv")
    monkeypatch.setenv("QT_PLUGIN_PATH", "C:/development/Qt")
    monkeypatch.setenv("REFRATRANSLATOR_OCR_MANIFEST_PATH", "C:/user/old-manifest.json")
    monkeypatch.setenv("REFRATRANSLATOR_INSTALL_DIR", "C:/user/existing-app")

    environment = verifier._isolated_environment(tmp_path)

    assert "development" not in environment["PATH"]
    assert "PYTHONPATH" not in environment and "PYTHONHOME" not in environment
    assert "VIRTUAL_ENV" not in environment
    assert "REFRATRANSLATOR_OCR_MANIFEST_PATH" not in environment
    assert "REFRATRANSLATOR_INSTALL_DIR" not in environment
    assert environment["QT_PLUGIN_PATH"] == ""
    for name in ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "REFRATRANSLATOR_DATA_DIR"):
        assert Path(environment[name]).is_relative_to(tmp_path)
        assert Path(environment[name]).is_dir()
    assert os.environ["PYTHONPATH"] == "C:/development/src"


def test_zero_exit_without_a_ready_gui_is_rejected(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime" / "python.exe"
    log = tmp_path / "launcher.log"
    log.write_text(
        f"Executable: {runtime}\nQML workbench module import: OK\n"
        "Checking first-run OCR resources...\nStarting RefraTranslator GUI...\n"
        "showing native QML workbench\nevent loop exited with code 0\n",
        encoding="utf-8",
    )
    with pytest.raises(verifier.VerificationError, match="event loop ready"):
        verifier._check_launcher_log(log, runtime)
    with log.open("a", encoding="utf-8") as handle:
        handle.write("event loop ready; visible=True geometry=0,0,800,600\n")
    verifier._check_launcher_log(log, runtime)
    with log.open("a", encoding="utf-8") as handle:
        handle.write("Traceback (most recent call last)\n")
    with pytest.raises(verifier.VerificationError, match="traceback"):
        verifier._check_launcher_log(log, runtime)


def _probe_fixture(install_root: Path) -> dict:
    return {
        "version": __version__,
        "executable": str(install_root / "runtime" / "python.exe"),
        "package_file": str(install_root / "runtime" / "Lib" / "site-packages" / "game_screen_translator" / "__init__.py"),
        "dependencies": {"httpx": {"version": "0.28.1", "location": str(install_root / "runtime" / "Lib" / "site-packages")}},
        "ocr_manifest_sha256": hashlib.sha256((ROOT / "packaging" / "ocr_wheel_manifest.json").read_bytes()).hexdigest(),
    }


@pytest.mark.parametrize("field", ["version", "executable", "package_file", "dependency", "location", "manifest"])
def test_probe_rejects_version_drift_or_dependencies_from_the_host(
    tmp_path: Path, field: str,
) -> None:
    install_root = tmp_path / "app"
    probe = _probe_fixture(install_root)
    verifier._check_probe(probe, install_root, {"httpx": "0.28.1"})
    if field in ("version", "executable", "package_file"):
        probe[field] = "9.9.9" if field == "version" else str(tmp_path / "development" / field)
    elif field == "dependency":
        probe["dependencies"]["httpx"]["version"] = "0.29.0"
    elif field == "location":
        probe["dependencies"]["httpx"]["location"] = str(tmp_path / "development")
    else:
        probe["ocr_manifest_sha256"] = "0" * 64
    with pytest.raises(verifier.VerificationError):
        verifier._check_probe(probe, install_root, {"httpx": "0.28.1"})


def test_failed_command_preserves_its_diagnostic_output(tmp_path: Path) -> None:
    log = tmp_path / "command.log"
    with pytest.raises(verifier.VerificationError, match="Exit code 7"):
        verifier._run(
            [sys.executable, "-c", "print('probe failure', flush=True); raise SystemExit(7)"],
            cwd=tmp_path, environment=os.environ.copy(), timeout=10, log_path=log,
        )
    assert "probe failure" in log.read_text(encoding="utf-8")


def test_timed_out_command_is_stopped(tmp_path: Path) -> None:
    with pytest.raises(verifier.VerificationError, match="Timed out"):
        verifier._run(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=tmp_path, environment=os.environ.copy(), timeout=0.1,
            log_path=tmp_path / "timeout.log",
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows process tree ownership")
def test_timeout_also_stops_the_launchers_child_process(tmp_path: Path) -> None:
    import ctypes
    from ctypes import wintypes

    child_record = tmp_path / "child-pid.txt"
    program = (
        "import subprocess, sys, time; from pathlib import Path; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        f"Path({str(child_record)!r}).write_text(str(child.pid)); time.sleep(60)"
    )
    with pytest.raises(verifier.VerificationError, match="Timed out"):
        verifier._run(
            [sys.executable, "-c", program], cwd=tmp_path,
            environment=os.environ.copy(), timeout=1, log_path=tmp_path / "child-timeout.log",
        )
    child_pid = int(child_record.read_text())
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000, False, child_pid)  # SYNCHRONIZE
    if handle:
        try:
            assert kernel.WaitForSingleObject(handle, 1000) == 0  # terminated
        finally:
            kernel.CloseHandle(handle)


@pytest.mark.skipif(os.name != "nt", reason="Windows installer orchestration")
def test_failed_install_keeps_a_failure_report_in_a_unique_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer = tmp_path / "RefraTranslator-Portable-Smoke.exe"
    installer.write_bytes(b"test stub")
    work_dir = tmp_path / "validation"
    work_dir.mkdir()
    existing = work_dir / "user-file.txt"
    existing.write_text("keep", encoding="utf-8")

    def fail(*args, **kwargs):
        raise verifier.VerificationError("installer failed")

    monkeypatch.setattr(verifier, "_run", fail)
    with pytest.raises(verifier.VerificationError, match="installer failed"):
        verifier.verify(installer, work_dir)
    reports = list(work_dir.glob("run-*/verification-report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["status"] == "failed" and report["error"] == "installer failed"
    assert existing.read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(os.name != "nt", reason="Windows installer orchestration")
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_duration_is_rejected_before_installation(tmp_path: Path, value: float) -> None:
    with pytest.raises(verifier.VerificationError, match="positive finite"):
        verifier.verify(tmp_path / "missing.exe", tmp_path / "validation", duration=value)
    assert not (tmp_path / "validation").exists()

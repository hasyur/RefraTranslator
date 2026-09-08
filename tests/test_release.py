from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

from game_screen_translator.config import load_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_RELEASE_FILES = (
    "LICENSE",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "bootstrap.ps1",
    "config.example.toml",
    "install.bat",
    "start_gui.bat",
    "start_test_scenes.bat",
    "update.bat",
    "update.ps1",
)
QML_SOURCE_FILES = tuple(
    sorted(
        (
            PROJECT_ROOT
            / "src"
            / "game_screen_translator"
            / "gui"
            / "qml"
        ).rglob("*.qml")
    )
)
PUBLIC_ENDPOINT_FILES = (
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "config.example.toml",
    PROJECT_ROOT / "scripts" / "render_launcher_preview.py",
    PROJECT_ROOT / "src" / "game_screen_translator" / "gui" / "launcher.py",
    PROJECT_ROOT / "src" / "game_screen_translator" / "gui" / "qml_workbench.py",
    PROJECT_ROOT / "src" / "game_screen_translator" / "gui" / "workbench_controller.py",
    *QML_SOURCE_FILES,
)
PRIVATE_HTTP_ENDPOINT = re.compile(
    r"https?://(?:"
    r"10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
    r")(?::\d+)?"
)


def test_public_config_template_is_valid() -> None:
    config = load_config(PROJECT_ROOT / "config.example.toml")

    assert config.translation.base_url == "http://127.0.0.1:1234/v1"
    assert config.ocr.device == "gpu:0"


def test_public_endpoint_examples_do_not_expose_private_lan_addresses() -> None:
    assert QML_SOURCE_FILES
    findings = []
    for path in PUBLIC_ENDPOINT_FILES:
        text = path.read_text(encoding="utf-8")
        findings.extend(
            f"{path.relative_to(PROJECT_ROOT)}: {match.group(0)}"
            for match in PRIVATE_HTTP_ENDPOINT.finditer(text)
        )

    assert findings == []


def test_release_metadata_declares_and_bundles_notices() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    project = pyproject["project"]

    assert project["license"] == "Apache-2.0"
    assert set(project["license-files"]) == {"LICENSE", "THIRD_PARTY_NOTICES.md"}
    assert set(pyproject["build-system"]["requires"]) <= set(
        project["optional-dependencies"]["dev"]
    )
    assert (PROJECT_ROOT / "LICENSE").is_file()
    assert (PROJECT_ROOT / "THIRD_PARTY_NOTICES.md").is_file()
    assert "dxcam[winrt]>=0.3,<0.4" in project["optional-dependencies"]["gui"]
    assert "ocr" not in project["optional-dependencies"]
    assert any(
        dependency.startswith("paddlepaddle-gpu")
        for dependency in project["optional-dependencies"]["ocr-gpu"]
    )


def test_release_metadata_bundles_the_native_qml_workbench() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        package_data = tomllib.load(handle)["tool"]["setuptools"]["package-data"]

    gui_data = set(package_data["game_screen_translator.gui"])
    assert {
        "qml/*.qml",
        "qml/components/*.qml",
        "qml/pages/*.qml",
    } <= gui_data
    manifest = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "recursive-include src/game_screen_translator/gui/qml *.qml" in manifest


def test_built_archives_contain_the_exact_native_qml_workbench(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "dist"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    wheels = list(output_dir.glob("*.whl"))
    source_archives = list(output_dir.glob("*.tar.gz"))
    assert len(wheels) == 1
    assert len(source_archives) == 1

    qml_root = PROJECT_ROOT / "src" / "game_screen_translator" / "gui" / "qml"
    expected = {
        path.relative_to(qml_root).as_posix()
        for path in qml_root.rglob("*.qml")
    }

    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_qml = {
            name.split("game_screen_translator/gui/qml/", 1)[1]
            for name in archive.namelist()
            if "game_screen_translator/gui/qml/" in name
            and name.endswith(".qml")
        }
    with tarfile.open(source_archives[0], "r:gz") as archive:
        sdist_qml = {
            name.split("game_screen_translator/gui/qml/", 1)[1]
            for name in archive.getnames()
            if "game_screen_translator/gui/qml/" in name
            and name.endswith(".qml")
        }

    assert wheel_qml == expected
    assert sdist_qml == expected


def test_launcher_preview_uses_the_production_qml_workbench() -> None:
    preview = (
        PROJECT_ROOT / "scripts" / "render_launcher_preview.py"
    ).read_text(encoding="utf-8")

    assert "WorkbenchController" in preview
    assert "QmlWorkbenchHost" in preview
    assert "LauncherWindow" not in preview


def test_source_release_manifest_includes_first_run_files() -> None:
    manifest = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    for relative_path in SOURCE_RELEASE_FILES:
        assert (PROJECT_ROOT / relative_path).is_file()
        assert f"include {relative_path}" in manifest


def test_bootstrap_script_is_ascii_for_windows_powershell_51() -> None:
    script = (PROJECT_ROOT / "bootstrap.ps1").read_bytes()

    assert script.decode("ascii")


def test_bootstrap_gui_install_uses_nvidia_gpu_without_device_prompt() -> None:
    script = (PROJECT_ROOT / "bootstrap.ps1").read_text(encoding="ascii")

    assert "[switch]$WithGpuOcr" in script
    assert "$installGpuOcr = $WithGui -or $WithGpuOcr" in script
    assert 'Write-Host "OCR installation selected: NVIDIA GPU ($GpuCuda)"' in script
    assert "Read-OcrDeviceChoice" not in script
    assert "[switch]$WithOcr" not in script
    assert "$OcrDevice" not in script


def test_bootstrap_rejects_max_path_unsafe_ocr_install_location() -> None:
    script = (PROJECT_ROOT / "bootstrap.ps1").read_text(encoding="ascii")

    assert "function Assert-OcrInstallPathLength" in script
    assert "predicated_tile_access_iterator_residual_last.h" in script
    assert "if ($paddleDeepPath.Length -le 259)" in script
    assert "if ($installGpuOcr)" in script
    path_check_call = "Assert-OcrInstallPathLength -ProjectRoot $projectRoot"
    venv_creation = "if (-not (Test-Path -LiteralPath $venvPython))"
    assert script.index(path_check_call) < script.index(venv_creation)


def test_bootstrap_migrates_legacy_ocr_config_to_nvidia_gpu() -> None:
    script = (PROJECT_ROOT / "bootstrap.ps1").read_text(encoding="ascii")

    assert "function Update-NvidiaOcrConfig" in script
    assert "cpu_threads" in script
    assert 'device = `"gpu:0`"' in script
    assert "Update-NvidiaOcrConfig -ConfigPath $localConfig" in script


def test_bootstrap_removes_only_pip_cache_after_success_unless_kept() -> None:
    script = (PROJECT_ROOT / "bootstrap.ps1").read_text(encoding="ascii")

    assert "[switch]$KeepInstallCache" in script
    assert 'Join-Path (Join-Path $resolvedProjectRoot ".cache") "pip"' in script
    assert "[System.StringComparer]::OrdinalIgnoreCase.Equals(" in script
    assert "[System.IO.FileAttributes]::ReparsePoint" in script
    assert (
        "Remove-Item -LiteralPath $resolvedPipCache -Recurse -Force "
        "-ErrorAction Stop"
    ) in script
    cleanup_call = (
        "Clear-PipInstallCache -ProjectRoot $projectRoot "
        "-PipCachePath $pipCache"
    )
    assert cleanup_call in script
    assert script.index("Invoke-VenvPython -m pip install --cache-dir $pipCache --editable") < (
        script.index(cleanup_call)
    )
    assert 'Write-Host "Keeping installer download cache: $pipCache"' in script


def test_gui_batch_preserves_native_crash_diagnostics() -> None:
    script = (PROJECT_ROOT / "start_gui.bat").read_text(encoding="ascii")

    assert "-X faulthandler" in script
    assert "QApplication([])" in script
    assert "QQmlApplicationEngine" in script
    assert "QQuickWindow" in script
    assert "QQuickStyle" in script
    assert "game_screen_translator.gui.qml_workbench" in script
    assert "game_screen_translator.gui.launcher" not in script
    assert "launcher.log" in script
    assert 'set "QT_QPA_PLATFORM=windows"' in script
    assert 'set "QT_PLUGIN_PATH="' in script
    assert 'if not "%launcher_exit%"=="0" goto :launch_failed' in script
    assert "launcher exited unexpectedly" in script
    assert "if errorlevel 1 pause" not in script.lower()


def test_install_batch_runs_gui_bootstrap_and_preserves_exit_code() -> None:
    script = (PROJECT_ROOT / "install.bat").read_text(encoding="ascii")

    assert 'cd /d "%~dp0"' in script
    assert '-File "%~dp0bootstrap.ps1" -WithGui' in script
    assert 'set "install_exit=%ERRORLEVEL%"' in script
    assert 'exit /b %install_exit%' in script
    assert "start_gui.bat" in script


def test_update_batch_runs_powershell_updater_and_preserves_exit_code() -> None:
    script = (PROJECT_ROOT / "update.bat").read_text(encoding="ascii")

    assert 'cd /d "%~dp0"' in script
    assert '-File "%~dp0update.ps1"' in script
    assert 'set "update_exit=%ERRORLEVEL%"' in script
    assert 'exit /b %update_exit%' in script


def test_update_script_uses_safe_incremental_main_update() -> None:
    script = (PROJECT_ROOT / "update.ps1").read_bytes()
    text = script.decode("ascii")

    assert '$supportedBranches = @("main", "master")' in text
    assert 'if ($currentBranch -notin $supportedBranches)' in text
    assert 'if ($currentBranch -eq "master")' in text
    assert "Legacy master branch detected" in text
    assert '"--porcelain"' in text
    assert '"--untracked-files=no"' in text
    assert '@("pull", "--ff-only", "origin", "main")' in text
    assert "diff --quiet" in text
    assert "$oldCommit $newCommit -- pyproject.toml" in text
    assert "-File $bootstrapPath -WithGui" in text
    assert '$venvPython = Join-Path $projectRoot ".venv\\Scripts\\python.exe"' in text
    assert "if ($environmentMissing -or $dependencyChanged)" in text
    assert "GitHub ZIP downloads cannot be" in text


@pytest.mark.skipif(os.name != "nt", reason="update.ps1 requires Windows PowerShell")
def test_update_script_fast_forwards_a_clean_legacy_master_clone(
    tmp_path: Path,
) -> None:
    git = shutil.which("git")
    powershell = shutil.which("powershell.exe")
    if git is None or powershell is None:
        pytest.skip("Git and Windows PowerShell are required")

    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    legacy = tmp_path / "legacy"

    def run(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            arguments,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    run(git, "init", "--bare", str(remote))
    run(git, "init", "--initial-branch=main", str(seed))
    run(git, "config", "user.name", "RefraTranslator Test", cwd=seed)
    run(git, "config", "user.email", "test@example.invalid", cwd=seed)
    shutil.copy2(PROJECT_ROOT / "update.ps1", seed / "update.ps1")
    (seed / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="ascii")
    (seed / "bootstrap.ps1").write_text(
        'throw "bootstrap should not run"\n',
        encoding="ascii",
    )
    run(git, "add", ".", cwd=seed)
    run(git, "commit", "-m", "base", cwd=seed)
    run(git, "remote", "add", "origin", str(remote), cwd=seed)
    run(git, "push", "-u", "origin", "main", cwd=seed)

    run(git, "clone", "--branch", "main", str(remote), str(legacy))
    run(git, "branch", "-m", "master", cwd=legacy)
    venv_python = legacy / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_bytes(b"")

    (seed / "source.txt").write_text("new source\n", encoding="ascii")
    run(git, "add", "source.txt", cwd=seed)
    run(git, "commit", "-m", "remote update", cwd=seed)
    run(git, "push", "origin", "main", cwd=seed)

    completed = run(
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(legacy / "update.ps1"),
        cwd=legacy,
    )

    assert "Legacy master branch detected" in completed.stdout
    assert "Updated source:" in completed.stdout
    assert "keeping the existing .venv" in completed.stdout
    assert run(git, "branch", "--show-current", cwd=legacy).stdout.strip() == "master"
    assert run(git, "rev-parse", "HEAD", cwd=legacy).stdout == run(
        git,
        "rev-parse",
        "HEAD",
        cwd=seed,
    ).stdout
    assert (legacy / "source.txt").read_text(encoding="ascii") == "new source\n"
    assert venv_python.is_file()

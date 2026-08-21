from __future__ import annotations

import re
import tomllib
from pathlib import Path

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
PUBLIC_ENDPOINT_FILES = (
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "config.example.toml",
    PROJECT_ROOT / "scripts" / "render_launcher_preview.py",
    PROJECT_ROOT / "src" / "game_screen_translator" / "gui" / "launcher.py",
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
    assert config.ocr.device == "cpu"


def test_public_endpoint_examples_do_not_expose_private_lan_addresses() -> None:
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
        project = tomllib.load(handle)["project"]

    assert project["license"] == "Apache-2.0"
    assert set(project["license-files"]) == {"LICENSE", "THIRD_PARTY_NOTICES.md"}
    assert (PROJECT_ROOT / "LICENSE").is_file()
    assert (PROJECT_ROOT / "THIRD_PARTY_NOTICES.md").is_file()
    assert "dxcam[winrt]>=0.3,<0.4" in project["optional-dependencies"]["gui"]


def test_source_release_manifest_includes_first_run_files() -> None:
    manifest = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    for relative_path in SOURCE_RELEASE_FILES:
        assert (PROJECT_ROOT / relative_path).is_file()
        assert f"include {relative_path}" in manifest


def test_bootstrap_script_is_ascii_for_windows_powershell_51() -> None:
    script = (PROJECT_ROOT / "bootstrap.ps1").read_bytes()

    assert script.decode("ascii")


def test_bootstrap_gui_install_prompts_for_ocr_device_with_nvidia_default() -> None:
    script = (PROJECT_ROOT / "bootstrap.ps1").read_text(encoding="ascii")

    assert '[ValidateSet("CPU", "NVIDIA", "None")]' in script
    assert 'elseif ($WithGui)' in script
    assert '$ocrInstallDevice = Read-OcrDeviceChoice' in script
    assert 'Write-Host "  [1] NVIDIA GPU (default)"' in script
    assert 'if ([string]::IsNullOrWhiteSpace($choice)) { return "nvidia" }' in script
    assert 'Write-Host "  [2] CPU"' in script


def test_bootstrap_rejects_max_path_unsafe_ocr_install_location() -> None:
    script = (PROJECT_ROOT / "bootstrap.ps1").read_text(encoding="ascii")

    assert "function Assert-OcrInstallPathLength" in script
    assert "predicated_tile_access_iterator_residual_last.h" in script
    assert "if ($paddleDeepPath.Length -le 259)" in script
    assert "if ($installCpuOcr -or $installGpuOcr)" in script
    path_check_call = "Assert-OcrInstallPathLength -ProjectRoot $projectRoot"
    venv_creation = "if (-not (Test-Path -LiteralPath $venvPython))"
    assert script.index(path_check_call) < script.index(venv_creation)


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

    assert 'if ($currentBranch -ne "main")' in text
    assert '"--porcelain"' in text
    assert '"--untracked-files=no"' in text
    assert '@("pull", "--ff-only", "origin", "main")' in text
    assert "diff --quiet" in text
    assert "$oldCommit $newCommit -- pyproject.toml" in text
    assert "-File $bootstrapPath -WithGui" in text
    assert '$venvPython = Join-Path $projectRoot ".venv\\Scripts\\python.exe"' in text
    assert "if ($environmentMissing -or $dependencyChanged)" in text
    assert "GitHub ZIP downloads cannot be" in text

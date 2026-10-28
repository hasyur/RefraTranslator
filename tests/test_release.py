from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
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
    "start_gui(debug).bat",
    "start_test_scenes.bat",
)
PUBLIC_TEST_FILES = tuple(
    sorted(
        path.relative_to(PROJECT_ROOT).as_posix()
        for pattern in ("tests/test_*.py", "tests/integration/test_*.py")
        for path in PROJECT_ROOT.glob(pattern)
    )
)
MANUAL_RELEASE_FILES = (
    "tests/manual/animated_ocr_scenes.py",
    "tests/manual/README.md",
)
PACKAGING_RELEASE_FILES = (
    "packaging/README.md",
    "packaging/build_windows_installer.py",
    "packaging/prepare_ocr_manifest.py",
    "packaging/windows_installer.iss",
    "packaging/windows_launcher.cs",
    "packaging/release_metadata.py",
    "packaging/requirements-core.txt",
    "packaging/ocr_wheel_manifest.json",
    "packaging/verify_windows_install.py",
    "packaging/releases/v0.1.0-alpha.4.md",
    "packaging/releases/v0.1.0-alpha.5.md",
)
PUBLIC_TEST_MANIFEST_ENTRIES = (
    "include tests/test_*.py",
    "include tests/integration/test_*.py",
    "include tests/manual/animated_ocr_scenes.py",
    "include tests/manual/README.md",
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
        "assets/*.ico",
        "qml/shared/*.qml",
        "qml/skins/prism/*.qml",
        "qml/skins/prism/components/*.qml",
        "qml/skins/prism/pages/*.qml",
        "qml/skins/prism/assets/*.png",
        "qml/skins/dohna/*.qml",
        "qml/skins/dohna/components/*.qml",
        "qml/skins/dohna/pages/*.qml",
        "qml/skins/dohna/assets/*.png",
    } <= gui_data
    manifest = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "recursive-include src/game_screen_translator/gui/qml *.qml" in manifest
    assert "recursive-include src/game_screen_translator/gui/qml *.png" in manifest
    assert "include src/game_screen_translator/gui/assets/*.ico" in manifest


def test_built_archives_contain_the_exact_native_qml_workbench(
    tmp_path: Path,
) -> None:
    build_root = tmp_path / "source"
    shutil.copytree(
        PROJECT_ROOT,
        build_root,
        ignore=shutil.ignore_patterns(
            ".git",
            ".local-tools",
            ".cache",
            ".codex",
            ".agents",
            ".venv",
            ".pytest_cache",
            "__pycache__",
            "*.egg-info",
            "build",
            "dist",
        ),
    )
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
        cwd=build_root,
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
    expected_assets = {
        path.relative_to(qml_root).as_posix()
        for path in qml_root.rglob("*.png")
    }
    icon_path = (
        PROJECT_ROOT
        / "src"
        / "game_screen_translator"
        / "gui"
        / "assets"
        / "refra-translator.ico"
    )

    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_names = set(archive.namelist())
        wheel_icon = "game_screen_translator/gui/assets/refra-translator.ico"
        assert wheel_icon in wheel_names
        assert archive.read(wheel_icon) == icon_path.read_bytes()
        wheel_qml = {
            name.split("game_screen_translator/gui/qml/", 1)[1]
            for name in wheel_names
            if "game_screen_translator/gui/qml/" in name
            and name.endswith(".qml")
        }
        wheel_asset_members = {
            name.split("game_screen_translator/gui/qml/", 1)[1]: name
            for name in wheel_names
            if "game_screen_translator/gui/qml/" in name
            and name.endswith(".png")
        }
        assert set(wheel_asset_members) == expected_assets
        for relative, member in wheel_asset_members.items():
            assert archive.read(member) == (qml_root / relative).read_bytes()
    with tarfile.open(source_archives[0], "r:gz") as archive:
        sdist_names = set(archive.getnames())
        sdist_icon = next(
            name
            for name in sdist_names
            if name.endswith("/src/game_screen_translator/gui/assets/refra-translator.ico")
        )
        archived_icon = archive.extractfile(sdist_icon)
        assert archived_icon is not None
        assert archived_icon.read() == icon_path.read_bytes()
        sdist_qml = {
            name.split("game_screen_translator/gui/qml/", 1)[1]
            for name in sdist_names
            if "game_screen_translator/gui/qml/" in name
            and name.endswith(".qml")
        }
        sdist_asset_members = {
            name.split("game_screen_translator/gui/qml/", 1)[1]: name
            for name in sdist_names
            if "game_screen_translator/gui/qml/" in name
            and name.endswith(".png")
        }
        assert set(sdist_asset_members) == expected_assets
        for relative, member in sdist_asset_members.items():
            archived = archive.extractfile(member)
            assert archived is not None
            assert archived.read() == (qml_root / relative).read_bytes()

    assert wheel_qml == expected
    assert sdist_qml == expected
    sdist_files = {name.split("/", 1)[1] for name in sdist_names if "/" in name}
    assert set(SOURCE_RELEASE_FILES) <= sdist_files
    assert set(PUBLIC_TEST_FILES) <= sdist_files
    assert set(MANUAL_RELEASE_FILES) <= sdist_files
    assert set(PACKAGING_RELEASE_FILES) <= sdist_files
    assert {"update.bat", "update.ps1"}.isdisjoint(sdist_files)
    assert not any(
        name == "scripts" or name.startswith("scripts/") for name in sdist_files
    )
    assert not any(
        name == ".local-tools" or name.startswith(".local-tools/")
        for name in sdist_files
    )
    allowed_test_files = set(PUBLIC_TEST_FILES) | set(MANUAL_RELEASE_FILES)
    assert {
        name
        for name in sdist_files
        if name.startswith("tests/") and Path(name).suffix in {".py", ".md"}
    } <= allowed_test_files
    assert not any(
        name.startswith("tests/") and Path(name).suffix not in {"", ".py", ".md"}
        for name in sdist_files
    )
    assert not any(
        name.startswith(("tests/", "scripts/", ".local-tools/"))
        for name in wheel_names
    )
    assert any(
        name.endswith("game_screen_translator/gui_entry.py")
        for name in wheel_names
    )
    assert any(
        name.endswith("game_screen_translator/gui_entry.py")
        for name in sdist_names
    )


def test_manifest_prunes_experimental_files_in_a_minimal_release_fixture(
    tmp_path: Path,
) -> None:
    fixture_root = tmp_path / "release-fixture"
    fixture_root.mkdir()
    for relative_path in ("pyproject.toml", "MANIFEST.in", *SOURCE_RELEASE_FILES):
        destination = fixture_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative_path, destination)

    shutil.copytree(
        PROJECT_ROOT / "src",
        fixture_root / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"),
    )
    for relative_path in (*PUBLIC_TEST_FILES, *MANUAL_RELEASE_FILES):
        destination = fixture_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative_path, destination)

    script_sentinel = fixture_root / "scripts" / "experimental_probe.py"
    local_sentinel = fixture_root / ".local-tools" / "tests" / "test_experiment.py"
    script_sentinel.parent.mkdir()
    local_sentinel.parent.mkdir(parents=True)
    script_sentinel.write_text("raise SystemExit(0)\n", encoding="utf-8")
    local_sentinel.write_text("raise SystemExit(0)\n", encoding="utf-8")

    output_dir = fixture_root / "dist"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(output_dir),
        ],
        cwd=fixture_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    wheels = list(output_dir.glob("*.whl"))
    source_archives = list(output_dir.glob("*.tar.gz"))
    assert len(wheels) == 1
    assert len(source_archives) == 1

    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_names = set(archive.namelist())
    with tarfile.open(source_archives[0], "r:gz") as archive:
        sdist_files = {
            name.split("/", 1)[1]
            for name in archive.getnames()
            if "/" in name
        }

    assert "scripts/experimental_probe.py" not in sdist_files
    assert ".local-tools/tests/test_experiment.py" not in sdist_files
    assert not any(
        name.startswith(("scripts/", ".local-tools/")) for name in sdist_files
    )
    assert not any(
        name.startswith(("scripts/", ".local-tools/")) for name in wheel_names
    )


def test_source_release_manifest_includes_first_run_files() -> None:
    manifest = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    for relative_path in SOURCE_RELEASE_FILES:
        assert (PROJECT_ROOT / relative_path).is_file()
        assert f"include {relative_path}" in manifest
    for entry in PUBLIC_TEST_MANIFEST_ENTRIES:
        assert entry in manifest
    assert "recursive-include scripts" not in manifest
    assert "recursive-include tests *.py" not in manifest
    assert "recursive-include tests/manual *.md" not in manifest
    assert "prune scripts" in manifest
    assert "prune .local-tools" in manifest


def test_public_staging_ignores_a_nested_private_tools_checkout(
    tmp_path: Path,
) -> None:
    git_executable = shutil.which("git")
    assert git_executable is not None
    checkout = tmp_path / "public-checkout"
    checkout.mkdir()
    shutil.copy2(PROJECT_ROOT / ".gitignore", checkout / ".gitignore")
    public_test = checkout / "tests" / "test_public_marker.py"
    public_test.parent.mkdir()
    public_test.write_text("def test_public_marker(): pass\n", encoding="utf-8")

    private_checkout = checkout / ".local-tools"
    private_test = private_checkout / "tests" / "test_private_marker.py"
    private_test.parent.mkdir(parents=True)
    private_test.write_text("def test_private_marker(): pass\n", encoding="utf-8")

    def run_git(root: Path, *arguments: str) -> str:
        completed = subprocess.run(
            [git_executable, *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        return completed.stdout

    run_git(checkout, "init", "--quiet")
    run_git(private_checkout, "init", "--quiet")
    run_git(checkout, "add", "-A")

    tracked = set(run_git(checkout, "ls-files").splitlines())
    assert tracked == {".gitignore", "tests/test_public_marker.py"}
    staged = run_git(checkout, "diff", "--cached", "--name-status").splitlines()
    assert all(".local-tools" not in entry for entry in staged)
    staged_modes = {
        entry.split(maxsplit=1)[0]
        for entry in run_git(checkout, "ls-files", "--stage").splitlines()
    }
    assert all(
        mode != "160000"
        for mode in staged_modes
    )


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


def test_gui_batch_entrypoints_delegate_to_the_same_backend() -> None:
    normal = (PROJECT_ROOT / "start_gui.bat").read_text(encoding="ascii")
    debug = (PROJECT_ROOT / "start_gui(debug).bat").read_text(encoding="ascii")
    shared_invocation = "-s -X utf8 -m game_screen_translator.gui_entry %*"

    assert shared_invocation in normal
    assert shared_invocation in debug
    assert 'start "" /b "%LAUNCHER_PYTHON%"' in normal
    assert ">nul 2>&1" in normal
    assert ".venv\\Scripts\\pythonw.exe" in normal
    assert ".venv\\Scripts\\python.exe" in debug
    assert "start " not in debug
    assert "QApplication" not in normal + debug
    assert "QT_QPA_PLATFORM" not in normal + debug


def test_shared_gui_backend_preserves_native_crash_diagnostics() -> None:
    script = (
        PROJECT_ROOT / "src" / "game_screen_translator" / "gui_entry.py"
    ).read_text(encoding="utf-8")

    assert "-X" in script
    assert "faulthandler" in script
    assert "QApplication([])" in script
    assert "QQmlApplicationEngine" in script
    assert "QQuickWindow" in script
    assert "QQuickStyle" in script
    assert "game_screen_translator.gui.qml_workbench" in script
    assert '"launcher.log"' in script
    assert '"QT_QPA_PLATFORM": "windows"' in script
    assert '"QT_PLUGIN_PATH": ""' in script
    assert "subprocess.CREATE_NO_WINDOW" in script
    assert '"game_screen_translator"' in script


def test_install_batch_runs_gui_bootstrap_and_preserves_exit_code() -> None:
    script = (PROJECT_ROOT / "install.bat").read_text(encoding="ascii")

    assert 'cd /d "%~dp0"' in script
    assert '-File "%~dp0bootstrap.ps1" -WithGui' in script
    assert 'set "install_exit=%ERRORLEVEL%"' in script
    assert 'exit /b %install_exit%' in script
    assert "start_gui.bat" in script


def test_readme_installation_guide_matches_supported_environment() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        requires_python = tomllib.load(handle)["project"]["requires-python"]

    assert requires_python == ">=3.11,<3.14"
    assert "64 位 Windows 10 或 Windows 11" in readme
    assert "不需要先安装 Python" in readme
    assert "64 位 Python 3.11、3.12 或 3.13" in readme
    assert "nvidia-smi" in readme
    assert "C:\\RefraTranslator" in readme
    assert readme.index("`install.bat`") < readme.index("`start_gui.bat`")


def test_readme_installation_guide_documents_installer_contract() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "`.venv` 虚拟环境" in readme
    assert "再次安装时保留已有配置" in readme
    assert "安装成功后清理 `.cache\\pip`" in readme
    assert "只删除项目根目录中的 `.venv`" in readme
    assert "安装目录下的 `output\\launcher.log`" in readme
    assert "程序文件、配置、游戏档案、日志、模型和运行资源统一保存在" in readme
    assert "旧目录会保持原样，不自动搬移或清理" in readme
    assert "`output\\launcher.log`" in readme
    assert "`output\\live.log`" in readme
    assert "再次运行 `RefraTranslator-Setup.exe`" in readme
    assert "-WithGui -WithDev" in readme
    assert "WindowsApps\\python.exe" in readme
    assert "where.exe python" in readme


def test_readme_keeps_the_exe_user_journey_before_source_development() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    user_guide, developer_guide = readme.split("\n## 源码安装与开发（可选）\n", 1)

    assert "https://github.com/hasyur/RefraTranslator/releases)" in user_guide
    assert "Assets / 附件" in user_guide
    assert "普通用户推荐使用 EXE 安装版" in user_guide
    assert "`RefraTranslator-Setup.exe`" in user_guide
    assert "`RefraTranslator.exe`" in user_guide
    assert "勾选 **创建桌面快捷方式**" in user_guide
    for developer_entry in ("install.bat", "start_gui.bat", "bootstrap.ps1", "git pull"):
        assert developer_entry not in user_guide
        assert developer_entry in developer_guide


def test_archived_release_notes_keep_user_instructions_without_validation_logs() -> None:
    for tag in ("v0.1.0-alpha.4", "v0.1.0-alpha.5"):
        notes = (PROJECT_ROOT / f"packaging/releases/{tag}.md").read_text(encoding="utf-8")

        assert "## 本版改动" in notes
        assert "## 安装与升级" in notes
        assert "选择原安装目录" in notes
        assert "SHA256SUMS.txt" in notes
        assert "## 验证" not in notes
        assert "Windows CI" not in notes
        assert "项通过" not in notes

    alpha4 = (PROJECT_ROOT / "packaging/releases/v0.1.0-alpha.4.md").read_text(encoding="utf-8")
    alpha5 = (PROJECT_ROOT / "packaging/releases/v0.1.0-alpha.5.md").read_text(encoding="utf-8")
    assert re.search(r"发布源码提交：`[0-9a-f]{40}`", alpha4)
    assert re.search(
        r"应用代码基线：`cba105cfb57a29c2b56258f335b2375d18566862`", alpha5
    )


def test_readme_explains_exe_first_run_and_in_place_updates() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    user_guide = readme.split("\n## 源码安装与开发（可选）\n", 1)[0]
    update_guide = user_guide.split("\n## 更新\n", 1)[1].split("\n## 常见问题\n", 1)[0]

    assert "首次使用屏幕识别还需下载约 **3 GiB**" in user_guide
    assert "13 GiB 可用磁盘空间" in user_guide
    assert "总下载进度" in user_guide and "当前文件进度" in user_guide
    assert "**TRANSLATION / 翻译 → 下载并使用** 单独准备" in user_guide
    assert "### EXE 安装版" in update_guide
    assert "关闭 RefraTranslator，包括仍在托盘中运行的程序" in update_guide
    assert "选择原安装目录" in update_guide
    assert "无需先卸载" in update_guide
    assert "保留安装目录中的配置、游戏档案、日志、模型和已准备的运行资源" in update_guide

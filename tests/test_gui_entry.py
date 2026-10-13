from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from game_screen_translator import gui_entry
from game_screen_translator.config import load_config
from game_screen_translator.profiles import (
    apply_profile_runtime_settings,
    create_game_profile,
    load_game_profile,
)


@pytest.fixture(autouse=True)
def _isolate_launcher_mutex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Keep launcher tests independent of an already running user workbench.
    guard_type = gui_entry.SingleInstanceGuard
    mutex_name = (
        f"Local\\RefraTranslator.GUI.test.{tmp_path.parent.name}.{tmp_path.name}"
    )
    monkeypatch.setattr(gui_entry, "SingleInstanceGuard", lambda: guard_type(mutex_name))


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


def test_installed_launcher_keeps_data_in_install_root_and_runs_first_run_preparation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_root = tmp_path / "installed-app"
    install_root.mkdir()
    template = Path(__file__).resolve().parents[1] / "config.example.toml"
    (install_root / "config.example.toml").write_bytes(template.read_bytes())
    data_root = install_root
    worker = tmp_path / "runtime" / "python.exe"
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []
    monkeypatch.setenv("REFRATRANSLATOR_DATA_DIR", str(tmp_path / "ignored-data-override"))
    monkeypatch.setattr(gui_entry, "_worker_python", lambda: worker)

    def fake_run_logged(command, **kwargs) -> int:
        commands.append([str(argument) for argument in command])
        environments.append(kwargs["environment"])
        return 0

    monkeypatch.setattr(gui_entry, "_run_logged", fake_run_logged)

    assert gui_entry.run(
        ["--installed", "--duration", "0.5"],
        project_root=install_root,
        mirror=StringIO(),
    ) == 0

    config_path = data_root / "config.toml"
    assert config_path.read_bytes() == template.read_bytes()
    config = load_config(config_path)
    assert config.translation.backend == "builtin"
    assert config.translation.builtin_model == "Hy-MT2-1.8B-Q8_0.gguf"
    create_game_profile(config_path, config, "first-game")
    profile = load_game_profile(config_path, config, "first-game")
    runtime = apply_profile_runtime_settings(config, profile)
    assert runtime.translation.backend == "builtin"
    assert runtime.translation.builtin_model == "Hy-MT2-1.8B-Q8_0.gguf"
    assert len(commands) == 3
    assert commands[1][commands[1].index("game_screen_translator.first_run") :] == [
        "game_screen_translator.first_run",
        "--config",
        str(config_path),
        "--duration",
        "0.5",
    ]
    assert commands[2][-6:] == [
        "game_screen_translator",
        "--config",
        str(config_path),
        "gui",
        "--duration",
        "0.5",
    ]
    assert environments[0]["REFRATRANSLATOR_INSTALLED"] == "1"
    assert environments[0]["REFRATRANSLATOR_DATA_DIR"] == str(data_root.resolve())
    assert environments[0]["QML_DISK_CACHE_PATH"] == str(install_root / ".cache" / "qt" / "qml")
    assert environments[0]["QSG_RHI_PIPELINE_CACHE_LOAD"] == str(install_root / ".cache" / "qt" / "pipeline.cache")
    assert environments[0]["QSG_RHI_PIPELINE_CACHE_SAVE"] == environments[0]["QSG_RHI_PIPELINE_CACHE_LOAD"]
    assert (install_root / ".cache" / "qt" / "qml").is_dir()
    assert all(environment is environments[0] for environment in environments)
    assert not (tmp_path / "ignored-data-override").exists()


@pytest.mark.parametrize("backend", ["external", "builtin"])
def test_prepare_config_preserves_saved_backend(
    tmp_path: Path, backend: str,
) -> None:
    config_path = tmp_path / "config.toml"
    saved = (
        '[translation]\n'
        f'backend = "{backend}"\n'
        'base_url = "http://server.test/v1"\n'
        'model = "saved-model"\n'
        'builtin_model = "Hy-MT2-7B-Q4_K_M.gguf"\n'
    ).encode("utf-8")
    config_path.write_bytes(saved)
    template_root = Path(__file__).resolve().parents[1]

    assert gui_entry._prepare_config(tmp_path, template_root) == config_path
    assert config_path.read_bytes() == saved
    assert load_config(config_path).translation.backend == backend


def test_installed_root_is_derived_from_its_own_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_root = tmp_path / "安装目录 with spaces"
    monkeypatch.setattr(gui_entry.sys, "executable", str(install_root / "runtime" / "pythonw.exe"))
    monkeypatch.setenv("REFRATRANSLATOR_INSTALL_DIR", str(tmp_path / "stale-install"))
    assert gui_entry._install_root() == install_root.resolve()


def test_existing_user_directory_and_working_directory_cannot_redirect_installed_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = tmp_path / "LocalAppData" / "RefraTranslator"
    legacy.mkdir(parents=True)
    (legacy / "config.toml").write_text("legacy config", encoding="utf-8")
    (legacy / "keep.part").write_bytes(b"resume me")
    unrelated = tmp_path / "working-directory"
    unrelated.mkdir()
    (unrelated / "config.toml").write_text("unrelated config", encoding="utf-8")
    install_root = tmp_path / "installed-app"
    install_root.mkdir()
    (install_root / "config.example.toml").write_text("fresh = true\n", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(legacy.parent))
    monkeypatch.chdir(unrelated)
    monkeypatch.setattr(gui_entry, "_worker_python", lambda: install_root / "runtime" / "python.exe")
    monkeypatch.setattr(gui_entry, "_run_logged", lambda *_args, **_kwargs: 0)

    assert gui_entry.run(["--installed", "--duration", "0.1"], project_root=install_root, mirror=StringIO()) == 0
    assert (install_root / "config.toml").read_text(encoding="utf-8") == "fresh = true\n"
    assert (install_root / "output" / "launcher.log").is_file()
    assert (legacy / "config.toml").read_text(encoding="utf-8") == "legacy config"
    assert (legacy / "keep.part").read_bytes() == b"resume me"
    assert not (legacy / "output").exists()


def test_manual_data_copy_in_install_root_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_root = tmp_path / "installed-app"
    install_root.mkdir()
    config = install_root / "config.toml"
    config.write_text("copied = true\n", encoding="utf-8")
    model = install_root / ".cache" / "local-llm" / "models" / "existing.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"existing model")
    partial = model.with_name("unfinished.gguf.part")
    partial.write_bytes(b"unfinished download")
    monkeypatch.setattr(gui_entry, "_worker_python", lambda: install_root / "runtime" / "python.exe")
    monkeypatch.setattr(gui_entry, "_run_logged", lambda *_args, **_kwargs: 0)
    assert gui_entry.run(["--installed"], project_root=install_root, mirror=StringIO()) == 0
    assert config.read_text(encoding="utf-8") == "copied = true\n"
    assert model.read_bytes() == b"existing model"
    assert partial.read_bytes() == b"unfinished download"

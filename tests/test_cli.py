import argparse
import os
import subprocess
import sys
from pathlib import Path

import pytest

from game_screen_translator.cli import _parse_region, _parser, main
from game_screen_translator.config import load_config
from game_screen_translator.profiles import (
    ProfileCaptureSettings,
    create_game_profile,
    save_profile_capture_settings,
)


def test_cli_configures_openblas_before_command_specific_imports() -> None:
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.pop("OPENBLAS_NUM_THREADS", None)
    existing_python_path = environment.get("PYTHONPATH")
    python_paths = [str(project_root / "src")]
    if existing_python_path:
        python_paths.append(existing_python_path)
    environment["PYTHONPATH"] = os.pathsep.join(python_paths)

    script = """
import os
import sys

import game_screen_translator.cli

assert os.environ["OPENBLAS_NUM_THREADS"] == "1"
unexpected = {
    "numpy",
    "game_screen_translator.ocr.paddle",
    "game_screen_translator.preview.renderer",
    "game_screen_translator.translation.local_backend",
    "game_screen_translator.translation.transport",
}.intersection(sys.modules)
assert not unexpected, sorted(unexpected)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr


def test_parse_region() -> None:
    assert _parse_region("10, 20, 800, 300") == (10, 20, 800, 300)


def test_cli_uses_refra_translator_name() -> None:
    parser = _parser()

    assert parser.prog == "refra-translator"
    assert "RefraTranslator" in parser.description


@pytest.mark.parametrize("value", ["1,2,3", "1,2,no,4", "-1,2,3,4"])
def test_parse_region_rejects_invalid_value(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_region(value)


def test_profile_cli_manual_correction_translates_without_server(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[translation]
provider = "openai_compatible"
base_url = "http://127.0.0.1:1/v1"
model = "hy-mt1.5-7b"
""",
        encoding="utf-8",
    )

    assert main(
        [
            "--config",
            str(config_path),
            "profile",
            "init",
            "game",
            "--name",
            "测试游戏",
        ]
    ) == 0
    assert main(
        [
            "--config",
            str(config_path),
            "profile",
            "correct",
            "game",
            "待て。",
            "等等。",
        ]
    ) == 0
    capsys.readouterr()

    assert main(
        [
            "--config",
            str(config_path),
            "translate",
            "待て。",
            "--profile",
            "game",
        ]
    ) == 0
    assert capsys.readouterr().out.strip() == "等等。"

    assert main(
        ["--config", str(config_path), "profile", "info", "game"]
    ) == 0
    info = capsys.readouterr().out
    assert "测试游戏 (game)" in info
    assert "人工修订：1 条（命中 1 次）" in info


def test_live_uses_saved_profile_capture_settings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[translation]
provider = "openai_compatible"
base_url = "http://127.0.0.1:1234/v1"
model = "hy-mt1.5-7b"
""",
        encoding="utf-8",
    )
    config = load_config(config_path)
    profile = create_game_profile(config_path, config, "game")
    save_profile_capture_settings(
        profile,
        ProfileCaptureSettings(monitor_index=2, region=(10, 20, 800, 240)),
    )
    received = []

    import game_screen_translator.live.runtime as live_runtime

    def fake_run_live(runtime_config, config_path_argument, **kwargs):
        received.append((runtime_config, config_path_argument, kwargs))
        return 0

    monkeypatch.setattr(live_runtime, "run_live", fake_run_live)

    assert main(
        [
            "--config",
            str(config_path),
            "live",
            "--profile",
            "game",
        ]
    ) == 0
    live = received[0][0].live
    assert (live.monitor_index, live.left, live.top, live.width, live.height) == (
        2,
        10,
        20,
        800,
        240,
    )
    assert received[0][2]["profile"].profile_id == "game"

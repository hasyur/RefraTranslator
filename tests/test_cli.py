import argparse
import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from game_screen_translator.cli import _parse_region, _parser, main
from game_screen_translator.config import load_config
from game_screen_translator.ocr.types import OcrText
from game_screen_translator.profiles import (
    ProfileCaptureSettings,
    create_game_profile,
    save_profile_custom_prompt,
    save_profile_capture_settings,
    save_profile_runtime_settings,
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


@pytest.mark.parametrize(
    "arguments",
    (
        ["doctor"],
        ["translate", "待て。"],
        ["preview", "screen.png"],
        ["live"],
    ),
)
def test_translation_commands_require_a_profile(arguments: list[str]) -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(arguments)


@pytest.mark.parametrize("value", ["1,2,3", "1,2,no,4", "-1,2,3,4"])
def test_parse_region_rejects_invalid_value(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_region(value)


def _create_profile_with_runtime_settings(config_path: Path):
    machine_config = load_config(config_path)
    profile = create_game_profile(config_path, machine_config, "game")
    save_profile_runtime_settings(
        profile,
        replace(
            machine_config,
            translation=replace(
                machine_config.translation,
                base_url="http://127.0.0.1:4321/v1",
                model="profile-model",
                target_language="繁體中文",
                max_concurrency=7,
            ),
            ocr=replace(
                machine_config.ocr,
                language="japan",
                min_score=0.91,
                detection_model="profile-det",
                recognition_model="profile-rec",
                model_source="modelscope",
                device="gpu:1",
                detection_max_side=2048,
                text_filter_enabled=False,
                text_merge_enabled=False,
                translate_latin=False,
                translate_han_only=True,
            ),
            preview=replace(
                machine_config.preview,
                blur_radius=13.0,
                overlay_opacity=0.15,
                font_path="profile-font.ttf",
            ),
            recording=replace(
                machine_config.recording,
                browser_overlay_enabled=True,
                browser_overlay_port=48765,
            ),
            live=replace(
                machine_config.live,
                change_poll_fps=11,
                change_threshold=5.0,
                stable_observations=2,
                stable_ms=120,
                clear_after_ms=1200,
                context_pairs=5,
                max_batch_size=6,
                capture_backend="winrt",
                ocr_cooldown_ms=70,
                settle_rescan_ms=700,
                idle_rescan_ms=2500,
                dynamic_roi_enabled=True,
                debug_border=True,
                dynamic_roi_response_target_ms=650,
                dynamic_roi_settle_ms=220,
                dynamic_roi_ocr_interval_ms=450,
                dynamic_roi_max_coalesce_ms=480,
            ),
        ),
    )
    return machine_config, profile


def _patch_passthrough_backend(monkeypatch, received):
    import game_screen_translator.translation.local_backend as local_backend

    @contextmanager
    def fake_backend(config, config_path):
        received.append((config, config_path))
        yield config

    monkeypatch.setattr(local_backend, "managed_translation_backend", fake_backend)


def test_doctor_uses_profile_translation_settings(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[translation]
provider = "openai_compatible"
base_url = "http://127.0.0.1:1234/v1"
model = "machine-model"
""",
        encoding="utf-8",
    )
    _create_profile_with_runtime_settings(config_path)
    backend_calls = []
    _patch_passthrough_backend(monkeypatch, backend_calls)

    import game_screen_translator.translation.transport as transport_module

    transports = []

    class FakeTransport:
        def __init__(self, translation):
            self.translation = translation
            transports.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def list_models(self):
            return (self.translation.model,)

    monkeypatch.setattr(transport_module, "OpenAICompatibleTransport", FakeTransport)

    assert main(
        [
            "--config",
            str(config_path),
            "doctor",
            "--profile",
            "game",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert "http://127.0.0.1:4321/v1/" in output
    assert "profile-model（可用）" in output
    assert len(backend_calls) == 1
    runtime_config = backend_calls[0][0]
    assert runtime_config.translation.model == "profile-model"
    assert runtime_config.translation.max_concurrency == 7
    assert runtime_config.translation.target_language == "繁體中文"
    assert transports[0].translation == runtime_config.translation


def test_translate_uses_profile_translation_and_prompt(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[translation]
provider = "openai_compatible"
base_url = "http://127.0.0.1:1234/v1"
model = "machine-model"
""",
        encoding="utf-8",
    )
    _machine_config, profile = _create_profile_with_runtime_settings(config_path)
    save_profile_custom_prompt(profile, "Galgame 专有译名")
    backend_calls = []
    _patch_passthrough_backend(monkeypatch, backend_calls)

    import game_screen_translator.translation.transport as transport_module

    transports = []
    prompts = []

    class FakeTransport:
        def __init__(self, translation):
            self.translation = translation
            transports.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def complete(self, prompt):
            prompts.append(prompt)
            return '<target><sn id="1">你好。</sn></target>'

    monkeypatch.setattr(transport_module, "OpenAICompatibleTransport", FakeTransport)

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
    assert capsys.readouterr().out.strip() == "你好。"
    assert len(backend_calls) == 1
    runtime_config = backend_calls[0][0]
    assert runtime_config.translation.model == "profile-model"
    assert runtime_config.translation.base_url == "http://127.0.0.1:4321/v1"
    assert transports[0].translation == runtime_config.translation
    assert "Galgame 专有译名" in prompts[0]


def test_preview_uses_profile_ocr_translation_and_overlay_settings(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[translation]
provider = "openai_compatible"
base_url = "http://127.0.0.1:1234/v1"
model = "machine-model"
""",
        encoding="utf-8",
    )
    _create_profile_with_runtime_settings(config_path)
    image_path = tmp_path / "screen.png"
    output_path = tmp_path / "preview.png"
    image_path.write_bytes(b"test image")
    backend_calls = []
    _patch_passthrough_backend(monkeypatch, backend_calls)

    import game_screen_translator.ocr.paddle as paddle_module
    import game_screen_translator.preview.renderer as renderer_module
    import game_screen_translator.translation.transport as transport_module

    ocr_calls = []

    class FakeOcrEngine:
        def __init__(self, **kwargs):
            ocr_calls.append(kwargs)

        def recognize(self, source_path):
            assert source_path == image_path
            return (
                OcrText(
                    "待て。",
                    0.99,
                    ((10, 10), (220, 10), (220, 70), (10, 70)),
                ),
            )

    render_calls = []

    def fake_render_preview(
        source_path,
        destination,
        observations,
        translations,
        preview_config,
    ):
        render_calls.append(
            (source_path, destination, observations, translations, preview_config)
        )
        return Path(destination)

    transports = []

    class FakeTransport:
        def __init__(self, translation):
            self.translation = translation
            transports.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def complete(self, _prompt):
            return '<target><sn id="1">你好。</sn></target>'

    monkeypatch.setattr(paddle_module, "PaddleOcrEngine", FakeOcrEngine)
    monkeypatch.setattr(renderer_module, "render_preview", fake_render_preview)
    monkeypatch.setattr(transport_module, "OpenAICompatibleTransport", FakeTransport)

    assert main(
        [
            "--config",
            str(config_path),
            "preview",
            str(image_path),
            "--output",
            str(output_path),
            "--profile",
            "game",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert output.splitlines()[-1] == f"预览已保存：{output_path}"
    assert ocr_calls[0]["language"] == "japan"
    assert ocr_calls[0]["min_score"] == 0.91
    assert ocr_calls[0]["detection_model"] == "profile-det"
    assert ocr_calls[0]["recognition_model"] == "profile-rec"
    assert ocr_calls[0]["model_source"] == "modelscope"
    assert ocr_calls[0]["device"] == "gpu:1"
    assert ocr_calls[0]["detection_max_side"] == 2048
    assert len(backend_calls) == 1
    runtime_config = backend_calls[0][0]
    assert runtime_config.translation.model == "profile-model"
    assert transports[0].translation == runtime_config.translation
    assert render_calls[0][4].blur_radius == 13.0
    assert render_calls[0][4].overlay_opacity == 0.15


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
    save_profile_runtime_settings(
        profile,
        replace(
            config,
            translation=replace(config.translation, model="profile-model"),
            ocr=replace(config.ocr, device="gpu:2", detection_max_side=1920),
            preview=replace(config.preview, overlay_opacity=0.0),
            live=replace(config.live, change_poll_fps=9, debug_border=True),
        ),
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
    runtime_config = received[0][0]
    assert runtime_config.translation.model == "profile-model"
    assert runtime_config.ocr.device == "gpu:2"
    assert runtime_config.ocr.detection_max_side == 1920
    assert runtime_config.preview.overlay_opacity == 0.0
    assert runtime_config.live.change_poll_fps == 9
    assert runtime_config.live.debug_border is True
    assert received[0][2]["debug_border"] is None
    assert received[0][2]["profile"].profile_id == "game"

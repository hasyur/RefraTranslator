from pathlib import Path

import pytest

from game_screen_translator.config import (
    ConfigError,
    load_config,
    save_runtime_selection,
    save_translation_selection,
)


def _write(path: Path, extra: str = "") -> None:
    path.write_text(
        """
[translation]
provider = "openai_compatible"
base_url = "http://127.0.0.1:1234/v1"
model = "hy-mt1.5-7b"
max_concurrency = 3
"""
        + extra,
        encoding="utf-8",
    )


def test_load_config_normalizes_base_url(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path)

    config = load_config(path)

    assert config.translation.normalized_base_url == "http://127.0.0.1:1234/v1/"
    assert config.translation.max_concurrency == 3
    assert config.ocr.language == "japan"
    assert config.ocr.cache_dir == ".cache/paddlex"
    assert config.ocr.detection_model == "PP-OCRv6_small_det"
    assert config.ocr.recognition_model == "PP-OCRv6_small_rec"
    assert config.ocr.device == "cpu"
    assert config.ocr.cpu_threads == 2
    assert config.ocr.detection_max_side == 1280
    assert config.live.capture_backend == "dxgi"
    assert config.live.stable_observations == 2
    assert config.live.capture_fps == 15
    assert config.live.change_poll_fps == 6
    assert config.live.ocr_cooldown_ms == 350
    assert config.profiles.root_dir == "profiles"


def test_load_config_rejects_unknown_field(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[ocr]\nunknown = true\n")

    with pytest.raises(ConfigError, match="未知字段"):
        load_config(path)


def test_load_config_requires_translation_section(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[ocr]\nlanguage='japan'\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="translation"):
        load_config(path)


def test_profile_root_must_stay_below_config_directory(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[profiles]\nroot_dir='../shared'\n")

    with pytest.raises(ConfigError, match="相对路径"):
        load_config(path)


def test_load_config_rejects_excessive_ocr_threads(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[ocr]\ncpu_threads=64\n")

    with pytest.raises(ConfigError, match="cpu_threads"):
        load_config(path)


def test_load_config_rejects_invalid_ocr_device(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[ocr]\ndevice='cuda'\n")

    with pytest.raises(ConfigError, match="ocr.device"):
        load_config(path)


def test_save_translation_selection_updates_only_two_values(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """# local config
[translation]
provider = "openai_compatible"
base_url = "http://old.test/v1" # replaced
model = "old-model"
temperature = 0.25

[live]
capture_fps = 12
""",
        encoding="utf-8",
    )

    saved = save_translation_selection(
        path,
        base_url="http://new.test:9000/v1",
        model="new-model",
    )

    assert saved.translation.base_url == "http://new.test:9000/v1"
    assert saved.translation.model == "new-model"
    assert saved.translation.temperature == 0.25
    assert saved.live.capture_fps == 12
    text = path.read_text(encoding="utf-8")
    assert "# local config" in text
    assert "temperature = 0.25" in text
    assert "[live]" in text
    assert "capture_fps = 12" in text


def test_save_translation_selection_rejects_invalid_url_without_writing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(path)
    before = path.read_bytes()

    with pytest.raises(ConfigError, match="http"):
        save_translation_selection(path, base_url="not-a-url", model="model")

    assert path.read_bytes() == before


def test_save_runtime_selection_inserts_and_updates_ocr_device_atomically(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[live]\ncapture_fps=12\n")

    saved = save_runtime_selection(
        path,
        base_url="http://gpu.test/v1",
        model="small-model",
        ocr_device="gpu:1",
    )

    assert saved.translation.base_url == "http://gpu.test/v1"
    assert saved.translation.model == "small-model"
    assert saved.ocr.device == "gpu:1"
    assert saved.live.capture_fps == 12
    text = path.read_text(encoding="utf-8")
    assert "[ocr]" in text
    assert 'device = "gpu:1"' in text

    saved = save_runtime_selection(
        path,
        base_url="http://gpu.test/v1",
        model="small-model",
        ocr_device="cpu",
    )
    assert saved.ocr.device == "cpu"
    assert path.read_text(encoding="utf-8").count("device =") == 1


def test_save_runtime_selection_adds_device_to_existing_ocr_section(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[ocr]\nlanguage='japan'\n\n[live]\ncapture_fps=12\n")

    saved = save_runtime_selection(
        path,
        base_url="http://127.0.0.1:1234/v1",
        model="hy-mt1.5-7b",
        ocr_device="gpu:0",
    )

    assert saved.ocr.device == "gpu:0"
    assert saved.live.capture_fps == 12
    assert path.read_text(encoding="utf-8").count("device =") == 1


def test_save_runtime_selection_rejects_device_without_writing(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path)
    before = path.read_bytes()

    with pytest.raises(ConfigError, match="ocr.device"):
        save_runtime_selection(
            path,
            base_url="http://gpu.test/v1",
            model="model",
            ocr_device="gpu:-1",
        )

    assert path.read_bytes() == before

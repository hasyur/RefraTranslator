from pathlib import Path

import pytest

from game_screen_translator.config import ConfigError, load_config


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

from pathlib import Path

import pytest

from game_screen_translator.config import (
    ConfigError,
    DEFAULT_BROWSER_OVERLAY_PORT,
    DEFAULT_DARK_OVERLAY_OPACITY,
    LiveConfig,
    PreviewConfig,
    RecordingConfig,
    TranslationConfig,
    load_config,
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

    assert not hasattr(config.translation, "provider")
    assert config.translation.normalized_base_url == "http://127.0.0.1:1234/v1/"
    assert config.translation.max_concurrency == 3
    assert config.translation.backend == "external"
    assert config.translation.builtin_model == "Hy-MT2-1.8B-Q8_0.gguf"
    assert config.translation.builtin_cuda_device == "follow_ocr"
    assert config.translation.builtin_parallel == 1
    assert config.translation.builtin_total_context == 2048
    assert config.translation.builtin_max_output_tokens == 512
    assert config.translation.builtin_kv_cache_type == "f16"
    assert config.translation.builtin_temperature == 0.2
    assert config.translation.api_key == ""
    assert config.translation.api_key_env == "REFRA_TRANSLATOR_API_KEY"
    assert config.ocr.language == "japan"
    assert config.ocr.cache_dir == ".cache/paddlex"
    assert config.ocr.detection_model == "PP-OCRv6_small_det"
    assert config.ocr.recognition_model == "PP-OCRv6_small_rec"
    assert config.ocr.device == "gpu:0"
    assert config.ocr.detection_max_side == 1280
    assert config.ocr.text_filter_enabled is True
    assert config.ocr.text_merge_enabled is True
    assert config.ocr.text_merge_llm_arbitration_enabled is True
    assert config.ocr.translate_latin is True
    assert config.ocr.translate_han_only is False
    assert config.preview.overlay_opacity == DEFAULT_DARK_OVERLAY_OPACITY
    assert config.recording.browser_overlay_enabled is False
    assert config.recording.browser_overlay_port == DEFAULT_BROWSER_OVERLAY_PORT
    assert config.recording.browser_overlay_url.endswith(":47831/overlay")
    assert config.live.capture_backend == "dxgi"
    assert config.live.stable_observations == 1
    assert config.live.stable_ms == 0
    assert config.live.capture_fps == 12
    assert config.live.change_poll_fps == 6
    assert config.live.ocr_cooldown_ms == 0
    assert config.live.settle_rescan_ms == 500
    assert config.live.idle_rescan_ms == 2000
    assert config.live.dynamic_roi_enabled is False
    assert config.live.debug_border is False
    assert config.live.dynamic_roi_response_target_ms == 500
    assert config.live.dynamic_roi_settle_ms == 180
    assert config.live.dynamic_roi_ocr_interval_ms == 333
    assert config.live.dynamic_roi_max_coalesce_ms == 333
    assert config.profiles.root_dir == "profiles"


def test_default_api_key_name_falls_back_to_legacy_name(monkeypatch) -> None:
    monkeypatch.delenv("REFRA_TRANSLATOR_API_KEY", raising=False)
    monkeypatch.setenv("GAME_SCREEN_TRANSLATOR_API_KEY", "legacy-secret")
    config = TranslationConfig(
        base_url="http://127.0.0.1:1234/v1",
        model="model",
    )

    assert config.resolved_api_key == "legacy-secret"


def test_new_api_key_name_takes_priority(monkeypatch) -> None:
    monkeypatch.setenv("REFRA_TRANSLATOR_API_KEY", "new-secret")
    monkeypatch.setenv("GAME_SCREEN_TRANSLATOR_API_KEY", "legacy-secret")
    config = TranslationConfig(
        base_url="http://127.0.0.1:1234/v1",
        model="model",
    )

    assert config.resolved_api_key == "new-secret"


def test_explicit_api_key_takes_priority_over_environment(monkeypatch) -> None:
    monkeypatch.setenv("REFRA_TRANSLATOR_API_KEY", "environment-secret")
    config = TranslationConfig(
        base_url="http://127.0.0.1:1234/v1",
        model="model",
        api_key=" explicit-secret ",
    )

    assert config.api_key == "explicit-secret"
    assert config.resolved_api_key == "explicit-secret"


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


@pytest.mark.parametrize("provider", ["unsupported", 123])
def test_load_config_rejects_invalid_legacy_provider(
    tmp_path: Path,
    provider: object,
) -> None:
    path = tmp_path / "config.toml"
    _write(path)
    provider_literal = (
        f'"{provider}"' if isinstance(provider, str) else repr(provider)
    )
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'provider = "openai_compatible"',
            f"provider = {provider_literal}",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="provider"):
        load_config(path)


def test_profile_root_must_stay_below_config_directory(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[profiles]\nroot_dir='../shared'\n")

    with pytest.raises(ConfigError, match="相对路径"):
        load_config(path)


def test_load_config_rejects_removed_cpu_threads_option(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[ocr]\ncpu_threads=2\n")

    with pytest.raises(ConfigError, match="未知字段"):
        load_config(path)


def test_load_config_rejects_excessive_translation_concurrency(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(path)
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "max_concurrency = 3",
            "max_concurrency = 33",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="max_concurrency"):
        load_config(path)


def test_load_config_rejects_invalid_ocr_device(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[ocr]\ndevice='cuda'\n")

    with pytest.raises(ConfigError, match="ocr.device"):
        load_config(path)


def test_load_config_rejects_removed_cpu_ocr_device(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[ocr]\ndevice='cpu'\n")

    with pytest.raises(ConfigError, match="仅支持 NVIDIA GPU"):
        load_config(path)


def test_load_config_rejects_non_boolean_text_filter_option(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[ocr]\ntext_filter_enabled='yes'\n")

    with pytest.raises(ConfigError, match="text_filter_enabled"):
        load_config(path)


def test_load_config_rejects_non_boolean_text_merge_option(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[ocr]\ntext_merge_enabled='yes'\n")

    with pytest.raises(ConfigError, match="text_merge_enabled"):
        load_config(path)


def test_load_config_rejects_non_boolean_text_merge_arbitration_option(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[ocr]\ntext_merge_llm_arbitration_enabled='yes'\n")

    with pytest.raises(ConfigError, match="text_merge_llm_arbitration_enabled"):
        load_config(path)


def test_load_config_rejects_non_boolean_dynamic_roi_option(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[live]\ndynamic_roi_enabled='yes'\n")

    with pytest.raises(ConfigError, match="dynamic_roi_enabled"):
        load_config(path)


def test_live_config_rejects_non_boolean_debug_border() -> None:
    with pytest.raises(ConfigError, match="debug_border"):
        LiveConfig(debug_border=1)  # type: ignore[arg-type]


def test_recording_config_rejects_invalid_browser_overlay_values() -> None:
    with pytest.raises(ConfigError, match="browser_overlay_enabled"):
        RecordingConfig(browser_overlay_enabled=1)  # type: ignore[arg-type]
    with pytest.raises(ConfigError, match="browser_overlay_port"):
        RecordingConfig(browser_overlay_port=1023)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("dynamic_roi_response_target_ms", 99),
        ("dynamic_roi_settle_ms", -1),
        ("dynamic_roi_ocr_interval_ms", 49),
        ("dynamic_roi_max_coalesce_ms", 10_001),
    ),
)
def test_load_config_rejects_invalid_dynamic_roi_timing(
    tmp_path: Path,
    field: str,
    value: int,
) -> None:
    path = tmp_path / "config.toml"
    _write(path, f"\n[live]\n{field}={value}\n")

    with pytest.raises(ConfigError, match=field):
        load_config(path)


@pytest.mark.parametrize("field", ("settle_rescan_ms", "idle_rescan_ms"))
def test_load_config_rejects_excessive_rescan_interval(
    tmp_path: Path,
    field: str,
) -> None:
    path = tmp_path / "config.toml"
    _write(path, f"\n[live]\n{field}=60001\n")

    with pytest.raises(ConfigError, match=field):
        load_config(path)


@pytest.mark.parametrize("backend", ["local", "cuda", ""])
def test_translation_config_rejects_unknown_backend(backend: str) -> None:
    with pytest.raises(ConfigError, match="backend"):
        TranslationConfig(
            backend=backend,
            base_url="http://127.0.0.1:1234/v1",
            model="model",
        )


def test_translation_config_rejects_non_string_builtin_model() -> None:
    with pytest.raises(ConfigError, match="builtin_model"):
        TranslationConfig(
            base_url="http://127.0.0.1:1234/v1",
            model="model",
            builtin_model=123,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("builtin_cuda_device", "CUDA0", "builtin_cuda_device"),
        ("builtin_parallel", 0, "builtin_parallel"),
        ("builtin_parallel", 33, "builtin_parallel"),
        ("builtin_kv_cache_type", "q4_0", "builtin_kv_cache_type"),
        ("builtin_temperature", -0.1, "builtin_temperature"),
        ("builtin_temperature", 2.1, "builtin_temperature"),
    ],
)
def test_translation_config_rejects_invalid_builtin_cuda_setting(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ConfigError, match=message):
        TranslationConfig(
            base_url="http://127.0.0.1:1234/v1",
            model="model",
            **{field: value},
        )


def test_live_capture_fps_follows_change_poll_frequency(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        "\n[live]\ncapture_fps=99\nchange_poll_fps=7\n",
    )

    config = load_config(path)

    assert config.live.change_poll_fps == 7
    assert config.live.capture_fps == 14


def test_load_config_rejects_change_poll_frequency_above_derived_limit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[live]\nchange_poll_fps=121\n")

    with pytest.raises(ConfigError, match="change_poll_fps"):
        load_config(path)


def test_preview_config_accepts_continuous_gui_background_opacity_range() -> None:
    for opacity in (0.0, 0.23, DEFAULT_DARK_OVERLAY_OPACITY):
        assert PreviewConfig(overlay_opacity=opacity).overlay_opacity == opacity

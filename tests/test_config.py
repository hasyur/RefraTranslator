from pathlib import Path

import pytest

from game_screen_translator.config import (
    ConfigError,
    DEFAULT_BROWSER_OVERLAY_PORT,
    DEFAULT_DARK_OVERLAY_OPACITY,
    PreviewConfig,
    RecordingConfig,
    TranslationConfig,
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
    assert config.live.dynamic_roi_response_target_ms == 500
    assert config.live.dynamic_roi_settle_ms == 180
    assert config.live.dynamic_roi_ocr_interval_ms == 333
    assert config.live.dynamic_roi_max_coalesce_ms == 333
    assert config.profiles.root_dir == "profiles"


def test_default_api_key_name_falls_back_to_legacy_name(monkeypatch) -> None:
    monkeypatch.delenv("REFRA_TRANSLATOR_API_KEY", raising=False)
    monkeypatch.setenv("GAME_SCREEN_TRANSLATOR_API_KEY", "legacy-secret")
    config = TranslationConfig(
        provider="openai_compatible",
        base_url="http://127.0.0.1:1234/v1",
        model="model",
    )

    assert config.resolved_api_key == "legacy-secret"


def test_new_api_key_name_takes_priority(monkeypatch) -> None:
    monkeypatch.setenv("REFRA_TRANSLATOR_API_KEY", "new-secret")
    monkeypatch.setenv("GAME_SCREEN_TRANSLATOR_API_KEY", "legacy-secret")
    config = TranslationConfig(
        provider="openai_compatible",
        base_url="http://127.0.0.1:1234/v1",
        model="model",
    )

    assert config.resolved_api_key == "new-secret"


def test_explicit_api_key_takes_priority_over_environment(monkeypatch) -> None:
    monkeypatch.setenv("REFRA_TRANSLATOR_API_KEY", "environment-secret")
    config = TranslationConfig(
        provider="openai_compatible",
        base_url="http://127.0.0.1:1234/v1",
        model="model",
        api_key=" explicit-secret ",
    )

    assert config.api_key == "explicit-secret"
    assert config.resolved_api_key == "explicit-secret"


def test_save_runtime_selection_can_clear_explicit_api_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "config.toml"
    _write(path, 'api_key = "stored-secret"\n')
    monkeypatch.setenv("REFRA_TRANSLATOR_API_KEY", "environment-secret")

    saved = save_runtime_selection(
        path,
        base_url="http://127.0.0.1:1234/v1",
        model="hy-mt1.5-7b",
        api_key="",
        ocr_device="gpu:0",
    )

    assert saved.translation.api_key == ""
    assert saved.translation.resolved_api_key == "environment-secret"
    text = path.read_text(encoding="utf-8")
    assert 'api_key = ""' in text
    assert text.count("api_key =") == 1


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
        api_key='secret-"quoted"',
        max_concurrency=7,
        ocr_detection_max_side=960,
        ocr_text_filter_enabled=False,
        ocr_text_merge_enabled=False,
        preview_overlay_opacity=0.0,
        recording_browser_overlay_enabled=True,
        recording_browser_overlay_port=49001,
        ocr_cooldown_ms=125,
        settle_rescan_ms=750,
        idle_rescan_ms=3500,
        clear_after_ms=1350,
        dynamic_roi_enabled=True,
        change_poll_fps=8,
        dynamic_roi_response_target_ms=650,
        dynamic_roi_settle_ms=240,
        dynamic_roi_ocr_interval_ms=250,
        dynamic_roi_max_coalesce_ms=450,
    )

    assert saved.translation.base_url == "http://gpu.test/v1"
    assert saved.translation.model == "small-model"
    assert saved.translation.api_key == 'secret-"quoted"'
    assert saved.translation.max_concurrency == 7
    assert saved.ocr.device == "gpu:1"
    assert saved.ocr.detection_max_side == 960
    assert saved.ocr.text_filter_enabled is False
    assert saved.ocr.text_merge_enabled is False
    assert saved.preview.overlay_opacity == 0.0
    assert saved.recording.browser_overlay_enabled is True
    assert saved.recording.browser_overlay_port == 49001
    assert saved.recording.browser_overlay_url == "http://127.0.0.1:49001/overlay"
    assert saved.live.capture_fps == 16
    assert saved.live.ocr_cooldown_ms == 125
    assert saved.live.settle_rescan_ms == 750
    assert saved.live.idle_rescan_ms == 3500
    assert saved.live.clear_after_ms == 1350
    assert saved.live.dynamic_roi_enabled is True
    assert saved.live.change_poll_fps == 8
    assert saved.live.dynamic_roi_response_target_ms == 650
    assert saved.live.dynamic_roi_settle_ms == 240
    assert saved.live.dynamic_roi_ocr_interval_ms == 250
    assert saved.live.dynamic_roi_max_coalesce_ms == 450
    text = path.read_text(encoding="utf-8")
    assert "[ocr]" in text
    assert 'device = "gpu:1"' in text
    assert "detection_max_side = 960" in text
    assert "text_filter_enabled = false" in text
    assert "text_merge_enabled = false" in text
    assert "overlay_opacity = 0.0" in text
    assert "browser_overlay_enabled = true" in text
    assert "browser_overlay_port = 49001" in text
    assert "max_concurrency = 7" in text
    assert 'api_key = "secret-\\\"quoted\\\""' in text
    assert "ocr_cooldown_ms = 125" in text
    assert "settle_rescan_ms = 750" in text
    assert "idle_rescan_ms = 3500" in text
    assert "clear_after_ms = 1350" in text
    assert "dynamic_roi_enabled = true" in text
    assert "capture_fps = 16" in text
    assert "change_poll_fps = 8" in text
    assert "dynamic_roi_response_target_ms = 650" in text
    assert "dynamic_roi_settle_ms = 240" in text
    assert "dynamic_roi_ocr_interval_ms = 250" in text
    assert "dynamic_roi_max_coalesce_ms = 450" in text

    saved = save_runtime_selection(
        path,
        base_url="http://gpu.test/v1",
        model="small-model",
        ocr_device="gpu:0",
    )
    assert saved.ocr.device == "gpu:0"
    assert saved.translation.api_key == 'secret-"quoted"'
    assert saved.ocr.detection_max_side == 960
    assert saved.ocr.text_filter_enabled is False
    assert saved.ocr.text_merge_enabled is False
    assert saved.preview.overlay_opacity == 0.0
    assert saved.recording.browser_overlay_enabled is True
    assert saved.recording.browser_overlay_port == 49001
    assert saved.live.ocr_cooldown_ms == 125
    assert saved.live.settle_rescan_ms == 750
    assert saved.live.idle_rescan_ms == 3500
    assert saved.live.clear_after_ms == 1350
    assert saved.live.dynamic_roi_enabled is True
    assert saved.live.change_poll_fps == 8
    assert saved.live.dynamic_roi_response_target_ms == 650
    assert saved.live.dynamic_roi_settle_ms == 240
    assert saved.live.dynamic_roi_ocr_interval_ms == 250
    assert saved.live.dynamic_roi_max_coalesce_ms == 450
    assert path.read_text(encoding="utf-8").count("device =") == 1
    assert path.read_text(encoding="utf-8").count("api_key =") == 1
    assert (
        path.read_text(encoding="utf-8").count("browser_overlay_enabled =") == 1
    )
    assert path.read_text(encoding="utf-8").count("browser_overlay_port =") == 1
    assert path.read_text(encoding="utf-8").count("detection_max_side =") == 1
    assert path.read_text(encoding="utf-8").count("text_filter_enabled =") == 1
    assert path.read_text(encoding="utf-8").count("text_merge_enabled =") == 1
    assert path.read_text(encoding="utf-8").count("dynamic_roi_enabled =") == 1
    assert path.read_text(encoding="utf-8").count("capture_fps =") == 1
    assert path.read_text(encoding="utf-8").count("change_poll_fps =") == 1
    assert path.read_text(encoding="utf-8").count("clear_after_ms =") == 1
    assert (
        path.read_text(encoding="utf-8").count(
            "dynamic_roi_response_target_ms ="
        )
        == 1
    )
    assert path.read_text(encoding="utf-8").count("dynamic_roi_settle_ms =") == 1
    assert (
        path.read_text(encoding="utf-8").count("dynamic_roi_ocr_interval_ms =")
        == 1
    )
    assert (
        path.read_text(encoding="utf-8").count("dynamic_roi_max_coalesce_ms =")
        == 1
    )

    saved = save_runtime_selection(
        path,
        base_url="http://gpu.test/v1",
        model="small-model",
        ocr_device="gpu:0",
        ocr_text_filter_enabled=True,
        ocr_text_merge_enabled=True,
    )
    assert saved.ocr.text_filter_enabled is True
    assert saved.ocr.text_merge_enabled is True
    text = path.read_text(encoding="utf-8")
    assert "text_filter_enabled = true" in text
    assert text.count("text_filter_enabled =") == 1
    assert "text_merge_enabled = true" in text
    assert text.count("text_merge_enabled =") == 1


def test_save_runtime_selection_updates_existing_recording_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[recording]
browser_overlay_enabled = true
browser_overlay_port = 49001
""",
    )

    saved = save_runtime_selection(
        path,
        base_url="http://127.0.0.1:1234/v1",
        model="hy-mt1.5-7b",
        ocr_device="gpu:0",
        recording_browser_overlay_enabled=False,
        recording_browser_overlay_port=49002,
    )

    assert saved.recording.browser_overlay_enabled is False
    assert saved.recording.browser_overlay_port == 49002
    text = path.read_text(encoding="utf-8")
    assert "browser_overlay_enabled = false" in text
    assert "browser_overlay_port = 49002" in text
    assert text.count("browser_overlay_enabled =") == 1
    assert text.count("browser_overlay_port =") == 1


def test_save_runtime_selection_updates_existing_live_timing_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[live]
ocr_cooldown_ms = 350
settle_rescan_ms = 500
idle_rescan_ms = 2000
clear_after_ms = 900
dynamic_roi_response_target_ms = 500
dynamic_roi_settle_ms = 180
dynamic_roi_ocr_interval_ms = 333
dynamic_roi_max_coalesce_ms = 333
""",
    )

    saved = save_runtime_selection(
        path,
        base_url="http://127.0.0.1:1234/v1",
        model="hy-mt1.5-7b",
        ocr_device="gpu:0",
        ocr_cooldown_ms=0,
        settle_rescan_ms=900,
        idle_rescan_ms=5000,
        clear_after_ms=1400,
        dynamic_roi_response_target_ms=750,
        dynamic_roi_settle_ms=260,
        dynamic_roi_ocr_interval_ms=400,
        dynamic_roi_max_coalesce_ms=600,
    )

    assert saved.live.ocr_cooldown_ms == 0
    assert saved.live.settle_rescan_ms == 900
    assert saved.live.idle_rescan_ms == 5000
    assert saved.live.clear_after_ms == 1400
    assert saved.live.dynamic_roi_response_target_ms == 750
    assert saved.live.dynamic_roi_settle_ms == 260
    assert saved.live.dynamic_roi_ocr_interval_ms == 400
    assert saved.live.dynamic_roi_max_coalesce_ms == 600
    text = path.read_text(encoding="utf-8")
    assert "ocr_cooldown_ms = 0" in text
    assert "settle_rescan_ms = 900" in text
    assert "idle_rescan_ms = 5000" in text
    assert "clear_after_ms = 1400" in text
    assert "dynamic_roi_response_target_ms = 750" in text
    assert "dynamic_roi_settle_ms = 260" in text
    assert "dynamic_roi_ocr_interval_ms = 400" in text
    assert "dynamic_roi_max_coalesce_ms = 600" in text
    assert text.count("ocr_cooldown_ms =") == 1
    assert text.count("settle_rescan_ms =") == 1
    assert text.count("idle_rescan_ms =") == 1
    assert text.count("clear_after_ms =") == 1
    assert text.count("dynamic_roi_response_target_ms =") == 1
    assert text.count("dynamic_roi_settle_ms =") == 1
    assert text.count("dynamic_roi_ocr_interval_ms =") == 1
    assert text.count("dynamic_roi_max_coalesce_ms =") == 1


def test_save_runtime_selection_adds_device_to_existing_ocr_section(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(path, "\n[ocr]\nlanguage='japan'\n\n[live]\ncapture_fps=12\n")

    saved = save_runtime_selection(
        path,
        base_url="http://127.0.0.1:1234/v1",
        model="hy-mt1.5-7b",
        ocr_device="gpu:1",
    )

    assert saved.ocr.device == "gpu:1"
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


def test_save_runtime_selection_rejects_non_boolean_filter_without_writing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(path)
    before = path.read_bytes()

    with pytest.raises(ConfigError, match="text_filter_enabled"):
        save_runtime_selection(
            path,
            base_url="http://gpu.test/v1",
            model="model",
            ocr_device="gpu:0",
            ocr_text_filter_enabled="no",  # type: ignore[arg-type]
        )

    assert path.read_bytes() == before


def test_save_runtime_selection_rejects_non_boolean_merge_without_writing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(path)
    before = path.read_bytes()

    with pytest.raises(ConfigError, match="text_merge_enabled"):
        save_runtime_selection(
            path,
            base_url="http://gpu.test/v1",
            model="model",
            ocr_device="gpu:0",
            ocr_text_merge_enabled="no",  # type: ignore[arg-type]
        )

    assert path.read_bytes() == before


def test_save_runtime_selection_rejects_invalid_overlay_opacity_without_writing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(path)
    before = path.read_bytes()

    with pytest.raises(ConfigError, match="preview.overlay_opacity"):
        save_runtime_selection(
            path,
            base_url="http://gpu.test/v1",
            model="model",
            ocr_device="gpu:0",
            preview_overlay_opacity=1.1,
        )

    assert path.read_bytes() == before


def test_preview_config_accepts_the_two_gui_background_opacities() -> None:
    assert PreviewConfig(overlay_opacity=DEFAULT_DARK_OVERLAY_OPACITY).overlay_opacity > 0
    assert PreviewConfig(overlay_opacity=0.0).overlay_opacity == 0.0

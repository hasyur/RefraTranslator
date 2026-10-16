import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from game_screen_translator.capture_region import FULL_SCREEN_REGION, pixels_to_region_ratio
from game_screen_translator.config import AppConfig, LiveConfig, TranslationConfig
from game_screen_translator.domain import GlossaryEntry
from game_screen_translator.profiles import (
    MAX_CUSTOM_PROMPT_CHARACTERS,
    ProfileCaptureSettings,
    ProfileDeletionCleanupError,
    ProfileError,
    apply_profile_capture_settings,
    apply_profile_runtime_settings,
    create_game_profile,
    create_named_game_profile,
    delete_game_profile,
    list_game_profiles,
    load_game_profile,
    profile_id_from_display_name,
    save_profile_capture_settings,
    save_profile_custom_prompt,
    save_profile_glossary,
    save_profile_runtime_settings,
    validate_profile_id,
)



def _region_ratio(region):
    return pixels_to_region_ratio(region, (1920, 1080))


def _config() -> AppConfig:
    return AppConfig(
        translation=TranslationConfig(
            base_url="http://server.test/v1",
            model="hy-mt1.5-7b",
        )
    )


def test_delete_profile_removes_owned_data_and_preserves_other_files(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[translation]\n", encoding="utf-8")
    first = create_game_profile(config_path, _config(), "first")
    second = create_game_profile(config_path, _config(), "second")
    (first.directory / "last-run.json").write_text("{}", encoding="utf-8")
    model = tmp_path / "model.gguf"
    model.write_bytes(b"shared")

    delete_game_profile(config_path, _config(), first.profile_id)

    assert not first.directory.exists()
    assert load_game_profile(config_path, _config(), second.profile_id).directory == second.directory
    assert config_path.read_text(encoding="utf-8") == "[translation]\n"
    assert model.read_bytes() == b"shared"
    assert sorted(path.name for path in second.directory.parent.iterdir()) == ["second"]


def test_delete_profile_rename_failure_preserves_the_entire_profile(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    def fail(*args):
        raise PermissionError("目录被占用")
    monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(PermissionError, match="目录被占用"):
        delete_game_profile(config_path, _config(), "game")
    assert load_game_profile(config_path, _config(), "game").settings_path.is_file()
    assert sorted(path.name for path in profile.directory.parent.iterdir()) == ["game"]


def test_partial_cleanup_failure_leaves_no_selectable_broken_profile(tmp_path: Path, monkeypatch) -> None:
    from game_screen_translator import profiles as profiles_module
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    survivor = create_game_profile(config_path, _config(), "survivor")
    residual = []
    def fail(holding):
        residual.append(holding)
        (holding / "game/profile.toml").unlink()
        (holding / "game/settings.toml").unlink()
        raise PermissionError("缓存被占用")
    monkeypatch.setattr(profiles_module.shutil, "rmtree", fail)
    with pytest.raises(ProfileDeletionCleanupError, match="缓存被占用") as error:
        delete_game_profile(config_path, _config(), "game")
    assert str(residual[0]) in str(error.value)
    assert not profile.directory.exists()
    assert [item.profile_id for item in list_game_profiles(config_path, _config())] == [survivor.profile_id]


@pytest.mark.parametrize("profile_id", ["../other", "", "CON", "missing"])
def test_delete_profile_rejects_invalid_or_missing_targets(tmp_path: Path, profile_id: str) -> None:
    config_path = tmp_path / "config.toml"
    survivor = create_game_profile(config_path, _config(), "survivor")
    with pytest.raises(ProfileError):
        delete_game_profile(config_path, _config(), profile_id)
    assert survivor.manifest_path.is_file()


def test_delete_profile_rejects_manifest_id_mismatch(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    profile.manifest_path.write_text('id = "other"\n', encoding="utf-8")
    with pytest.raises(ProfileError, match="id 与目录名不一致"):
        delete_game_profile(config_path, _config(), "game")
    assert profile.directory.is_dir()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows directory junction")
def test_delete_profile_rejects_junction_to_another_profile(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    alias = profile.directory.parent / "alias"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(alias), str(profile.directory)],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, result.stderr
    with pytest.raises(ProfileError, match="链接目录"):
        delete_game_profile(config_path, _config(), "alias")
    assert profile.manifest_path.is_file()


def test_create_and_load_isolated_game_profile(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    created = create_game_profile(
        config_path,
        _config(),
        "赛博朋克2077",
        display_name="赛博朋克 2077",
    )

    assert created.directory == tmp_path / "profiles" / "赛博朋克2077"
    assert created.manifest_path.is_file()
    assert created.glossary_path.is_file()
    assert created.settings_path.is_file()
    assert created.database_path.is_file()
    settings_text = created.settings_path.read_text(encoding="utf-8")
    assert "provider =" not in settings_text
    assert "dynamic_roi_settle_ms" not in settings_text
    assert "dynamic_roi_ocr_interval_ms" not in settings_text
    assert "dynamic_roi_max_coalesce_ms" not in settings_text
    initial_runtime = apply_profile_runtime_settings(_config(), created)
    assert initial_runtime.translation.max_concurrency == 4
    assert initial_runtime.translation.builtin_parallel == 4
    assert initial_runtime.live.dynamic_roi_enabled is True
    assert initial_runtime.live.clear_after_ms == 150
    assert initial_runtime.live.dynamic_roi_response_target_ms == 350

    created.glossary_path.write_text(
        '[[terms]]\nsource = "フィクサー"\ntarget = "中间人"\n',
        encoding="utf-8",
    )
    loaded = load_game_profile(config_path, _config(), "赛博朋克2077")

    assert loaded.display_name == "赛博朋克 2077"
    assert [(term.source, term.target) for term in loaded.glossary] == [
        ("フィクサー", "中间人")
    ]
    assert len(loaded.glossary_revision) == 64


def test_visible_profile_name_derives_internal_id_and_handles_collisions(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"

    first = create_named_game_profile(config_path, _config(), "赛博朋克 2077")
    second = create_named_game_profile(config_path, _config(), "赛博朋克：2077")

    assert first.display_name == "赛博朋克 2077"
    assert first.profile_id == "赛博朋克-2077"
    assert second.profile_id == "赛博朋克-2077-2"
    assert profile_id_from_display_name(" Cyberpunk 2077 ") == "cyberpunk-2077"
    assert profile_id_from_display_name("🎮").startswith("profile-")
    with pytest.raises(ProfileError, match="已存在"):
        create_named_game_profile(config_path, _config(), "赛博朋克 2077")


@pytest.mark.parametrize(
    "profile_id",
    ["../other", "a/b", "a\\b", ".", "name space", "CON", "LPT1"],
)
def test_profile_id_cannot_escape_its_root(profile_id: str) -> None:
    with pytest.raises(ProfileError, match="Profile ID"):
        validate_profile_id(profile_id)


def test_profile_glossary_rejects_duplicate_sources(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    profile.glossary_path.write_text(
        """
[[terms]]
source = "ＡＢＣ"
target = "甲"

[[terms]]
source = "ABC"
target = "乙"
""",
        encoding="utf-8",
    )

    with pytest.raises(ProfileError, match="原文重复"):
        load_game_profile(config_path, _config(), "game")


def test_profile_must_be_initialized_explicitly(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="profile init"):
        load_game_profile(tmp_path / "config.toml", _config(), "missing")


def test_legacy_pixel_region_resets_even_with_partial_or_invalid_values(tmp_path: Path) -> None:
    machine = replace(_config(), live=LiveConfig(region_ratio=(0.1, 0.7, 0.8, 0.25)))
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, machine, "game")
    profile.settings_path.write_text(
        '[capture]\nmonitor_index=0\nleft="obsolete"\nwidth=-1\n'
        '[translation]\nmodel="keep-model"\ncustom_prompt="keep-prompt"\n',
        encoding="utf-8",
    )
    loaded = load_game_profile(config_path, machine, "game")
    assert loaded.capture_settings.region_ratio == FULL_SCREEN_REGION
    assert loaded.runtime_settings.translation.model == "keep-model"
    assert loaded.custom_prompt == "keep-prompt"
    saved = loaded.settings_path.read_text(encoding="utf-8")
    assert "left =" not in saved
    assert "width =" not in saved
    assert "region_ratio = [0.0, 0.0, 1.0, 1.0]" in saved

    save_profile_capture_settings(loaded, ProfileCaptureSettings(monitor_index=0, region_ratio=(0.1, 0.7, 0.8, 0.25)))
    reloaded = load_game_profile(config_path, machine, "game")
    assert reloaded.capture_settings.region_ratio == (0.1, 0.7, 0.8, 0.25)
    assert reloaded.custom_prompt == "keep-prompt"


@pytest.mark.parametrize("ratio", [(0, 0, 0, 1), (0.9, 0, 0.2, 1), (0, 0, float("nan"), 1)])
def test_profile_rejects_invalid_new_region_ratios(tmp_path: Path, ratio) -> None:
    with pytest.raises(ProfileError, match="比例"):
        ProfileCaptureSettings(monitor_index=0, region_ratio=ratio)
    profile = create_game_profile(tmp_path / "config.toml", _config(), "game")
    profile.settings_path.write_text(f"[capture]\nregion_ratio={list(ratio)!r}\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="比例"):
        load_game_profile(tmp_path / "config.toml", _config(), "game")


def test_profile_capture_settings_are_explicit_and_override_other_values(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    original = LiveConfig(region_ratio=_region_ratio((5, 6, 700, 200)), monitor_index=0)

    initial = apply_profile_capture_settings(original, profile.capture_settings)
    assert initial.region_ratio == FULL_SCREEN_REGION
    assert initial.monitor_index == 0

    saved = ProfileCaptureSettings(
        monitor_index=1,
        region_ratio=_region_ratio((100, 700, 1800, 350)),
    )
    save_profile_capture_settings(profile, saved)
    loaded = load_game_profile(config_path, _config(), "game")
    applied = apply_profile_capture_settings(original, loaded.capture_settings)

    assert loaded.capture_settings == saved
    assert applied.region_ratio == _region_ratio((100, 700, 1800, 350))
    assert applied.monitor_index == 1


def test_profile_runtime_settings_are_isolated_from_other_profiles(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    machine = _config()
    game = create_game_profile(config_path, machine, "game")
    create_game_profile(config_path, machine, "web")
    game_config = apply_profile_runtime_settings(machine, game)
    changed = replace(
        game_config,
        translation=replace(
            game_config.translation,
            backend="builtin",
            model="game-model",
            max_concurrency=6,
        ),
        ocr=replace(
            game_config.ocr,
            device="gpu:1",
            detection_max_side=1920,
            text_filter_enabled=False,
        ),
        preview=replace(game_config.preview, overlay_opacity=0.0),
        recording=replace(game_config.recording, browser_overlay_enabled=True),
        live=replace(
            game_config.live,
            change_poll_fps=10,
            dynamic_roi_enabled=False,
            debug_border=True,
            clear_after_ms=900,
            dynamic_roi_response_target_ms=700,
            idle_rescan_ms=4000,
        ),
    )

    save_profile_runtime_settings(game, changed)
    loaded_game = load_game_profile(config_path, machine, "game")
    loaded_web = load_game_profile(config_path, machine, "web")
    effective_game = apply_profile_runtime_settings(machine, loaded_game)
    effective_web = apply_profile_runtime_settings(machine, loaded_web)

    assert effective_game.translation.model == "game-model"
    assert effective_game.translation.max_concurrency == 6
    assert effective_game.ocr.device == "gpu:1"
    assert effective_game.ocr.detection_max_side == 1920
    assert effective_game.ocr.text_filter_enabled is False
    assert effective_game.preview.overlay_opacity == 0.0
    assert effective_game.recording.browser_overlay_enabled is True
    assert effective_game.live.change_poll_fps == 10
    assert effective_game.live.dynamic_roi_enabled is False
    assert effective_game.live.clear_after_ms == 900
    assert effective_game.live.dynamic_roi_response_target_ms == 700
    assert effective_game.live.debug_border is True
    assert effective_game.live.idle_rescan_ms == 4000
    assert effective_web.translation.model == machine.translation.model
    assert effective_web.ocr.device == machine.ocr.device
    assert effective_web.preview.overlay_opacity == machine.preview.overlay_opacity
    assert effective_web.live.debug_border is False
    assert effective_web.live.dynamic_roi_enabled is True
    assert effective_web.live.clear_after_ms == 150
    assert effective_web.live.dynamic_roi_response_target_ms == 350


def test_legacy_profile_settings_migrate_once_to_an_independent_snapshot(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    original = _config()
    profile = create_game_profile(config_path, original, "game")
    profile.settings_path.write_text(
        """
[capture]
monitor_index = 1
left = 10
top = 20
width = 800
height = 300

[translation]
provider = "openai_compatible"
custom_prompt = "保持角色口吻。"
""",
        encoding="utf-8",
    )

    migrated = load_game_profile(config_path, original, "game")
    migrated_text = migrated.settings_path.read_text(encoding="utf-8")
    assert "[ocr]" in migrated_text
    assert "[preview]" in migrated_text
    assert "[recording]" in migrated_text
    assert "[live]" in migrated_text
    assert "debug_border = false" in migrated_text
    assert "provider =" not in migrated_text

    changed_machine = replace(
        original,
        translation=replace(original.translation, model="changed-global-model"),
        ocr=replace(original.ocr, device="gpu:3", cache_dir="machine-cache"),
        preview=replace(original.preview, overlay_opacity=0.0),
        live=replace(original.live, debug_border=True),
    )
    reloaded = load_game_profile(config_path, changed_machine, "game")
    effective = apply_profile_runtime_settings(changed_machine, reloaded)

    assert effective.translation.model == original.translation.model
    assert effective.ocr.device == original.ocr.device
    assert effective.preview.overlay_opacity == original.preview.overlay_opacity
    assert effective.live.debug_border is False
    assert effective.ocr.cache_dir == "machine-cache"
    assert reloaded.capture_settings == ProfileCaptureSettings(
        monitor_index=1,
        region_ratio=FULL_SCREEN_REGION,
    )
    assert reloaded.custom_prompt == "保持角色口吻。"


def test_legacy_dynamic_roi_timing_is_validated_and_removed_on_migration(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    original = _config()
    profile = create_game_profile(config_path, original, "game")
    profile.settings_path.write_text(
        """
[live]
dynamic_roi_settle_ms = 0
dynamic_roi_ocr_interval_ms = 50
dynamic_roi_max_coalesce_ms = 10000
""",
        encoding="utf-8",
    )

    migrated = load_game_profile(config_path, original, "game")
    migrated_text = migrated.settings_path.read_text(encoding="utf-8")

    assert not hasattr(migrated.runtime_settings.live, "dynamic_roi_settle_ms")
    assert not hasattr(migrated.runtime_settings.live, "dynamic_roi_ocr_interval_ms")
    assert not hasattr(migrated.runtime_settings.live, "dynamic_roi_max_coalesce_ms")
    assert "dynamic_roi_settle_ms" not in migrated_text
    assert "dynamic_roi_ocr_interval_ms" not in migrated_text
    assert "dynamic_roi_max_coalesce_ms" not in migrated_text


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("dynamic_roi_settle_ms", -1),
        ("dynamic_roi_ocr_interval_ms", 49),
        ("dynamic_roi_max_coalesce_ms", 10_001),
    ),
)
def test_profile_rejects_invalid_legacy_dynamic_roi_timing(
    tmp_path: Path,
    field: str,
    value: int,
) -> None:
    config_path = tmp_path / "config.toml"
    config = _config()
    profile = create_game_profile(config_path, config, "game")
    settings = profile.settings_path.read_text(encoding="utf-8")
    profile.settings_path.write_text(
        settings.replace(
            "[live]\n",
            f"[live]\n{field} = {value}\n",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProfileError, match=field):
        load_game_profile(config_path, config, "game")


@pytest.mark.parametrize("provider", ['"unsupported"', "123"])
def test_profile_rejects_invalid_legacy_provider(
    tmp_path: Path,
    provider: str,
) -> None:
    config_path = tmp_path / "config.toml"
    config = _config()
    profile = create_game_profile(config_path, config, "game")
    settings = profile.settings_path.read_text(encoding="utf-8")
    profile.settings_path.write_text(
        settings.replace(
            "[translation]\n",
            f"[translation]\nprovider = {provider}\n",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProfileError, match="provider"):
        load_game_profile(config_path, config, "game")


def test_profile_custom_prompt_round_trips_and_survives_capture_updates(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    prompt = "这是一款近未来题材 RPG。\n角色对话偏口语。"

    save_profile_custom_prompt(profile, prompt)
    with_prompt = load_game_profile(config_path, _config(), "game")
    assert with_prompt.custom_prompt == prompt

    capture = ProfileCaptureSettings(monitor_index=1, region_ratio=_region_ratio((10, 20, 800, 300)))
    save_profile_capture_settings(with_prompt, capture)
    loaded = load_game_profile(config_path, _config(), "game")
    assert loaded.capture_settings == capture
    assert loaded.custom_prompt == prompt

    save_profile_custom_prompt(loaded, "")
    cleared = load_game_profile(config_path, _config(), "game")
    assert cleared.custom_prompt == ""
    assert cleared.capture_settings == capture


def test_profile_custom_prompt_has_a_bounded_size(tmp_path: Path) -> None:
    profile = create_game_profile(tmp_path / "config.toml", _config(), "game")

    with pytest.raises(ProfileError, match="不能超过"):
        save_profile_custom_prompt(
            profile,
            "x" * (MAX_CUSTOM_PROMPT_CHARACTERS + 1),
        )


def test_gui_glossary_save_and_profile_listing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    second = create_game_profile(config_path, _config(), "b", display_name="Beta")
    first = create_game_profile(config_path, _config(), "a", display_name="Alpha")

    save_profile_glossary(
        first,
        (GlossaryEntry("フィクサー", "中间人"), GlossaryEntry("仕事", "委托")),
    )
    loaded = load_game_profile(config_path, _config(), "a")

    assert [(entry.source, entry.target) for entry in loaded.glossary] == [
        ("フィクサー", "中间人"),
        ("仕事", "委托"),
    ]
    assert [profile.profile_id for profile in list_game_profiles(config_path, _config())] == [
        first.profile_id,
        second.profile_id,
    ]

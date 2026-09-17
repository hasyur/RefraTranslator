from dataclasses import replace
from pathlib import Path

import pytest

from game_screen_translator.config import AppConfig, LiveConfig, TranslationConfig
from game_screen_translator.domain import GlossaryEntry
from game_screen_translator.profiles import (
    MAX_CUSTOM_PROMPT_CHARACTERS,
    ProfileCaptureSettings,
    ProfileError,
    apply_profile_capture_settings,
    apply_profile_runtime_settings,
    create_game_profile,
    create_named_game_profile,
    list_game_profiles,
    load_game_profile,
    profile_id_from_display_name,
    save_profile_capture_settings,
    save_profile_custom_prompt,
    save_profile_glossary,
    save_profile_runtime_settings,
    validate_profile_id,
)


def _config() -> AppConfig:
    return AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-7b",
        )
    )


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


def test_profile_capture_settings_are_explicit_and_override_other_values(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    original = LiveConfig(left=5, top=6, width=700, height=200, monitor_index=0)

    initial = apply_profile_capture_settings(original, profile.capture_settings)
    assert (
        initial.left,
        initial.top,
        initial.width,
        initial.height,
        initial.monitor_index,
    ) == (0, 0, 0, 0, 0)

    saved = ProfileCaptureSettings(
        monitor_index=1,
        region=(100, 700, 1800, 350),
    )
    save_profile_capture_settings(profile, saved)
    loaded = load_game_profile(config_path, _config(), "game")
    applied = apply_profile_capture_settings(original, loaded.capture_settings)

    assert loaded.capture_settings == saved
    assert (
        applied.left,
        applied.top,
        applied.width,
        applied.height,
        applied.monitor_index,
    ) == (100, 700, 1800, 350, 1)


def test_profile_runtime_settings_are_isolated_from_other_profiles(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    machine = _config()
    game = create_game_profile(config_path, machine, "game")
    web = create_game_profile(config_path, machine, "web")
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
            dynamic_roi_enabled=True,
            debug_border=True,
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
    assert effective_game.live.dynamic_roi_enabled is True
    assert effective_game.live.debug_border is True
    assert effective_game.live.idle_rescan_ms == 4000
    assert effective_web.translation.model == machine.translation.model
    assert effective_web.ocr.device == machine.ocr.device
    assert effective_web.preview.overlay_opacity == machine.preview.overlay_opacity
    assert effective_web.live.debug_border is False


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
        region=(10, 20, 800, 300),
    )
    assert reloaded.custom_prompt == "保持角色口吻。"


def test_profile_custom_prompt_round_trips_and_survives_capture_updates(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    prompt = "这是一款近未来题材 RPG。\n角色对话偏口语。"

    save_profile_custom_prompt(profile, prompt)
    with_prompt = load_game_profile(config_path, _config(), "game")
    assert with_prompt.custom_prompt == prompt

    capture = ProfileCaptureSettings(monitor_index=1, region=(10, 20, 800, 300))
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

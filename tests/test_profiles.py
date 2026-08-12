from pathlib import Path

import pytest

from game_screen_translator.config import AppConfig, LiveConfig, TranslationConfig
from game_screen_translator.domain import GlossaryEntry
from game_screen_translator.profiles import (
    ProfileCaptureSettings,
    ProfileError,
    apply_profile_capture_settings,
    create_game_profile,
    list_game_profiles,
    load_game_profile,
    save_profile_capture_settings,
    save_profile_glossary,
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


def test_profile_capture_settings_override_only_saved_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    original = LiveConfig(left=5, top=6, width=700, height=200, monitor_index=0)

    assert apply_profile_capture_settings(original, profile.capture_settings) == original

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

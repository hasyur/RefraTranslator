from pathlib import Path

import pytest

from game_screen_translator.gui.theme import (
    GuiPreferences,
    GuiSettingsError,
    SKIN_DOHNA,
    SKIN_PRISM,
    THEME_DARK,
    THEME_LIGHT,
    load_gui_preferences,
    save_gui_preferences,
)


def _config(path: Path) -> Path:
    path.write_text("[translation]\n", encoding="utf-8")
    return path


def test_old_gui_preferences_default_to_prism(tmp_path: Path) -> None:
    config_path = _config(tmp_path / "config.toml")
    (tmp_path / ".gui-settings.toml").write_text(
        '[appearance]\ntheme = "dark"\n',
        encoding="utf-8",
    )

    preferences = load_gui_preferences(config_path)

    assert preferences == GuiPreferences(theme=THEME_DARK, skin=SKIN_PRISM)


@pytest.mark.parametrize(
    ("theme", "skin"),
    ((THEME_DARK, SKIN_PRISM), (THEME_LIGHT, SKIN_PRISM), (THEME_DARK, SKIN_DOHNA)),
)
def test_gui_preferences_round_trip_keeps_theme_and_skin(
    tmp_path: Path,
    theme: str,
    skin: str,
) -> None:
    config_path = _config(tmp_path / "config.toml")

    save_gui_preferences(config_path, GuiPreferences(theme=theme, skin=skin))

    assert load_gui_preferences(config_path) == GuiPreferences(theme=theme, skin=skin)


@pytest.mark.parametrize(
    "content",
    (
        '[appearance]\nskin = "unknown"\n',
        '[appearance]\nskin = 1\n',
        '[appearance]\ntheme = "dark"\nextra = true\n',
    ),
)
def test_invalid_skin_settings_are_rejected(tmp_path: Path, content: str) -> None:
    config_path = _config(tmp_path / "config.toml")
    (tmp_path / ".gui-settings.toml").write_text(content, encoding="utf-8")

    with pytest.raises(GuiSettingsError):
        load_gui_preferences(config_path)

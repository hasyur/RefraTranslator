from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from game_screen_translator.branding import PRODUCT_NAME


THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_OPTIONS = (
    (THEME_SYSTEM, "跟随系统"),
    (THEME_LIGHT, "浅色"),
    (THEME_DARK, "深色"),
)
_VALID_THEMES = frozenset(value for value, _label in THEME_OPTIONS)
GUI_SETTINGS_FILENAME = ".gui-settings.toml"


class GuiSettingsError(ValueError):
    """Raised when the project-local GUI preferences are invalid."""


@dataclass(frozen=True, slots=True)
class GuiPreferences:
    theme: str = THEME_SYSTEM

    def __post_init__(self) -> None:
        if self.theme not in _VALID_THEMES:
            choices = ", ".join(sorted(_VALID_THEMES))
            raise GuiSettingsError(f"界面主题必须是以下值之一：{choices}")


def gui_settings_path(config_path: Path) -> Path:
    return config_path.resolve().parent / GUI_SETTINGS_FILENAME


def load_gui_preferences(config_path: Path) -> GuiPreferences:
    path = gui_settings_path(config_path)
    if not path.is_file():
        return GuiPreferences()
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise GuiSettingsError(f"{path.name} 格式错误：{exc}") from exc

    appearance = data.get("appearance", {})
    if not isinstance(appearance, dict):
        raise GuiSettingsError("[appearance] 必须是 TOML 表")
    unknown = set(appearance) - {"theme"}
    if unknown:
        raise GuiSettingsError(
            f"[appearance] 含有未知字段：{', '.join(sorted(map(str, unknown)))}"
        )
    theme = appearance.get("theme", THEME_SYSTEM)
    if not isinstance(theme, str):
        raise GuiSettingsError("appearance.theme 必须是字符串")
    return GuiPreferences(theme=theme)


def save_gui_preferences(config_path: Path, preferences: GuiPreferences) -> Path:
    path = gui_settings_path(config_path)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    content = (
        f"# {PRODUCT_NAME} 的本机 GUI 设置；不会写入 Windows 注册表。\n"
        "[appearance]\n"
        f'theme = "{preferences.theme}"\n'
    )
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _windows_app_theme() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            use_light_theme, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except (FileNotFoundError, OSError, ValueError):
        return None
    return THEME_LIGHT if bool(use_light_theme) else THEME_DARK


def detect_system_theme(app: QApplication) -> str:
    windows_theme = _windows_app_theme()
    if windows_theme is not None:
        return windows_theme
    scheme = app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return THEME_DARK
    if scheme == Qt.ColorScheme.Light:
        return THEME_LIGHT
    window_color = app.palette().color(QPalette.ColorRole.Window)
    return THEME_DARK if window_color.lightness() < 128 else THEME_LIGHT


def effective_theme(preference: str, app: QApplication) -> str:
    if preference not in _VALID_THEMES:
        raise GuiSettingsError(f"未知界面主题：{preference}")
    return detect_system_theme(app) if preference == THEME_SYSTEM else preference

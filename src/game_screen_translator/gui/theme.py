from __future__ import annotations

import json
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from game_screen_translator.branding import PRODUCT_NAME
from game_screen_translator.profiles import ProfileError, validate_profile_id
from .runtime import DEFAULT_HOTKEY, GuiRuntimeError, parse_hotkey


THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_OPTIONS = (
    (THEME_SYSTEM, "跟随系统"),
    (THEME_LIGHT, "浅色"),
    (THEME_DARK, "深色"),
)
_VALID_THEMES = frozenset(value for value, _label in THEME_OPTIONS)
SKIN_PRISM = "prism"
SKIN_DOHNA = "dohna"
SKIN_AZURE = "azure"
SKIN_OPTIONS = (
    (SKIN_PRISM, "Prism"),
    (SKIN_DOHNA, "Dohna"),
    (SKIN_AZURE, "蓝色剪影"),
)
_VALID_SKINS = frozenset(value for value, _label in SKIN_OPTIONS)
HOTKEY_BEHAVIOR_START_ONLY = "start_only"
HOTKEY_BEHAVIOR_TOGGLE = "toggle"
HOTKEY_BEHAVIOR_TOGGLE_SHOW = "toggle_show"
HOTKEY_BEHAVIOR_OPTIONS = (
    (HOTKEY_BEHAVIOR_START_ONLY, "仅启动"),
    (HOTKEY_BEHAVIOR_TOGGLE, "启动 / 停止翻译"),
    (HOTKEY_BEHAVIOR_TOGGLE_SHOW, "启动 / 停止并打开 GUI"),
)
_VALID_HOTKEY_BEHAVIORS = frozenset(
    value for value, _label in HOTKEY_BEHAVIOR_OPTIONS
)
GUI_SETTINGS_FILENAME = ".gui-settings.toml"


class GuiSettingsError(ValueError):
    """Raised when the project-local GUI preferences are invalid."""


@dataclass(frozen=True, slots=True)
class GuiPreferences:
    theme: str = THEME_SYSTEM
    skin: str = SKIN_PRISM
    start_with_windows: bool = False
    hotkey: str = DEFAULT_HOTKEY
    hotkey_behavior: str = HOTKEY_BEHAVIOR_START_ONLY
    last_profile_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.last_profile_id, str):
            raise GuiSettingsError("behavior.last_profile_id 必须是字符串")
        if self.last_profile_id:
            try:
                object.__setattr__(self, "last_profile_id", validate_profile_id(self.last_profile_id))
            except ProfileError as exc:
                raise GuiSettingsError(f"behavior.last_profile_id 无效：{exc}") from exc
        if not isinstance(self.theme, str) or self.theme not in _VALID_THEMES:
            choices = ", ".join(sorted(_VALID_THEMES))
            raise GuiSettingsError(f"界面主题必须是以下值之一：{choices}")
        if not isinstance(self.skin, str) or self.skin not in _VALID_SKINS:
            choices = ", ".join(sorted(_VALID_SKINS))
            raise GuiSettingsError(f"界面皮肤必须是以下值之一：{choices}")
        if not isinstance(self.start_with_windows, bool):
            raise GuiSettingsError("behavior.start_with_windows 必须是布尔值")
        if (
            not isinstance(self.hotkey_behavior, str)
            or self.hotkey_behavior not in _VALID_HOTKEY_BEHAVIORS
        ):
            choices = ", ".join(sorted(_VALID_HOTKEY_BEHAVIORS))
            raise GuiSettingsError(
                f"behavior.hotkey_behavior 必须是以下值之一：{choices}"
            )
        try:
            canonical_hotkey = parse_hotkey(self.hotkey)
        except (GuiRuntimeError, TypeError, ValueError) as exc:
            raise GuiSettingsError(f"behavior.hotkey 无效：{exc}") from exc
        object.__setattr__(self, "hotkey", canonical_hotkey.display)


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
    unknown = set(appearance) - {"theme", "skin"}
    if unknown:
        raise GuiSettingsError(
            f"[appearance] 含有未知字段：{', '.join(sorted(map(str, unknown)))}"
        )
    theme = appearance.get("theme", THEME_SYSTEM)
    if not isinstance(theme, str):
        raise GuiSettingsError("appearance.theme 必须是字符串")
    skin = appearance.get("skin", SKIN_PRISM)
    if not isinstance(skin, str):
        raise GuiSettingsError("appearance.skin 必须是字符串")
    behavior = data.get("behavior", {})
    if not isinstance(behavior, dict):
        raise GuiSettingsError("[behavior] 必须是 TOML 表")
    unknown_behavior = set(behavior) - {
        "start_with_windows",
        "hotkey",
        "hotkey_behavior",
        "last_profile_id",
    }
    if unknown_behavior:
        raise GuiSettingsError(
            f"[behavior] 含有未知字段：{', '.join(sorted(map(str, unknown_behavior)))}"
        )
    start_with_windows = behavior.get("start_with_windows", False)
    if not isinstance(start_with_windows, bool):
        raise GuiSettingsError("behavior.start_with_windows 必须是布尔值")
    hotkey = behavior.get("hotkey", DEFAULT_HOTKEY)
    if not isinstance(hotkey, str):
        raise GuiSettingsError("behavior.hotkey 必须是字符串")
    hotkey_behavior = behavior.get(
        "hotkey_behavior",
        HOTKEY_BEHAVIOR_START_ONLY,
    )
    if not isinstance(hotkey_behavior, str):
        raise GuiSettingsError("behavior.hotkey_behavior 必须是字符串")
    return GuiPreferences(
        theme=theme,
        skin=skin,
        start_with_windows=start_with_windows,
        hotkey=hotkey,
        hotkey_behavior=hotkey_behavior,
        last_profile_id=behavior.get("last_profile_id", ""),
    )


def save_gui_preferences(config_path: Path, preferences: GuiPreferences) -> Path:
    path = gui_settings_path(config_path)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    content = (
        f"# {PRODUCT_NAME} 的本机 GUI 设置；不会写入 Windows 注册表。\n"
        "[appearance]\n"
        f'theme = "{preferences.theme}"\n'
        f'skin = "{preferences.skin}"\n'
        "\n"
        "[behavior]\n"
        f"start_with_windows = {'true' if preferences.start_with_windows else 'false'}\n"
        f'hotkey = "{preferences.hotkey}"\n'
        f'hotkey_behavior = "{preferences.hotkey_behavior}"\n'
        f'last_profile_id = {json.dumps(preferences.last_profile_id, ensure_ascii=False)}\n'
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


def effective_theme(
    preference: str,
    app: QApplication | None,
    *,
    skin: str = SKIN_PRISM,
) -> str:
    if preference not in _VALID_THEMES:
        raise GuiSettingsError(f"未知界面主题：{preference}")
    if skin not in _VALID_SKINS:
        raise GuiSettingsError(f"未知界面皮肤：{skin}")
    if skin in {SKIN_DOHNA, SKIN_AZURE}:
        return THEME_LIGHT
    if preference != THEME_SYSTEM:
        return preference
    return detect_system_theme(app) if app is not None else THEME_DARK

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
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


@dataclass(frozen=True, slots=True)
class ThemeColors:
    window: str
    panel: str
    input: str
    alternate: str
    text: str
    muted: str
    disabled: str
    border: str
    tab: str
    button: str
    button_hover: str
    accent: str
    accent_hover: str
    selection: str
    selected_text: str


_LIGHT_COLORS = ThemeColors(
    window="#f4f6f8",
    panel="#ffffff",
    input="#ffffff",
    alternate="#f7f9fb",
    text="#20242a",
    muted="#5d6874",
    disabled="#929aa3",
    border="#c8d0d9",
    tab="#e8edf2",
    button="#f7f9fb",
    button_hover="#e9eef4",
    accent="#1677ff",
    accent_hover="#095fc7",
    selection="#b8d8ff",
    selected_text="#101820",
)

_DARK_COLORS = ThemeColors(
    window="#171a21",
    panel="#20242d",
    input="#151820",
    alternate="#1b1f27",
    text="#f2f4f7",
    muted="#aeb7c2",
    disabled="#737d89",
    border="#414a57",
    tab="#292f39",
    button="#2a303a",
    button_hover="#353d49",
    accent="#3b8cff",
    accent_hover="#69a6ff",
    selection="#275f99",
    selected_text="#ffffff",
)


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


def theme_palette(theme: str) -> QPalette:
    colors = _colors(theme)
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: colors.window,
        QPalette.ColorRole.WindowText: colors.text,
        QPalette.ColorRole.Base: colors.input,
        QPalette.ColorRole.AlternateBase: colors.alternate,
        QPalette.ColorRole.ToolTipBase: colors.panel,
        QPalette.ColorRole.ToolTipText: colors.text,
        QPalette.ColorRole.Text: colors.text,
        QPalette.ColorRole.Button: colors.button,
        QPalette.ColorRole.ButtonText: colors.text,
        QPalette.ColorRole.BrightText: colors.selected_text,
        QPalette.ColorRole.Highlight: colors.selection,
        QPalette.ColorRole.HighlightedText: colors.selected_text,
        QPalette.ColorRole.PlaceholderText: colors.muted,
        QPalette.ColorRole.Link: colors.accent,
        QPalette.ColorRole.LinkVisited: colors.accent_hover,
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            role,
            QColor(colors.disabled),
        )
    return palette


def theme_stylesheet(theme: str) -> str:
    colors = _colors(theme)
    return f"""
        QMainWindow, QDialog {{
            background-color: {colors.window};
            color: {colors.text};
        }}
        QWidget {{ color: {colors.text}; }}
        QWidget#launcherCentral {{ background-color: {colors.window}; }}
        QLabel {{ background-color: transparent; }}
        QLabel#secondaryText {{ color: {colors.muted}; }}
        QTabWidget::pane {{
            border: 1px solid {colors.border};
            background-color: {colors.panel};
        }}
        QTabBar::tab {{
            padding: 8px 16px;
            color: {colors.muted};
            background-color: {colors.tab};
            border: 1px solid {colors.border};
            border-bottom: 0;
        }}
        QTabBar::tab:selected {{
            color: {colors.accent};
            background-color: {colors.panel};
        }}
        QTabBar::tab:disabled {{ color: {colors.disabled}; }}
        QLineEdit, QComboBox, QSpinBox, QTableWidget, QAbstractItemView {{
            color: {colors.text};
            background-color: {colors.input};
            selection-background-color: {colors.selection};
            selection-color: {colors.selected_text};
            border: 1px solid {colors.border};
            border-radius: 3px;
        }}
        QLineEdit, QComboBox, QSpinBox {{
            padding: 4px;
            min-height: 22px;
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTableWidget:focus {{
            border-color: {colors.accent};
        }}
        QComboBox QAbstractItemView {{
            background-color: {colors.input};
            color: {colors.text};
            outline: 0;
        }}
        QTableWidget {{
            gridline-color: {colors.border};
            alternate-background-color: {colors.alternate};
        }}
        QHeaderView::section, QTableCornerButton::section {{
            color: {colors.text};
            background-color: {colors.tab};
            padding: 7px;
            border: 0;
            border-right: 1px solid {colors.border};
            border-bottom: 1px solid {colors.border};
        }}
        QPushButton {{
            color: {colors.text};
            background-color: {colors.button};
            border: 1px solid {colors.border};
            border-radius: 4px;
            padding: 6px 12px;
        }}
        QPushButton:hover {{ background-color: {colors.button_hover}; }}
        QPushButton:pressed {{ border-color: {colors.accent}; }}
        QPushButton:disabled {{ color: {colors.disabled}; }}
        QPushButton#startButton {{
            background-color: {colors.accent};
            color: white;
            border: 0;
            border-radius: 5px;
            padding: 10px;
        }}
        QPushButton#startButton:hover {{ background-color: {colors.accent_hover}; }}
        QCheckBox {{ spacing: 7px; background-color: transparent; }}
        QStatusBar {{
            color: {colors.muted};
            background-color: {colors.window};
            border-top: 1px solid {colors.border};
        }}
        QStatusBar::item {{ border: 0; }}
        QToolTip {{
            color: {colors.text};
            background-color: {colors.panel};
            border: 1px solid {colors.border};
            padding: 4px;
        }}
        QScrollBar:vertical, QScrollBar:horizontal {{
            background: {colors.window};
            border: 0;
        }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background: {colors.border};
            border-radius: 4px;
            min-height: 24px;
            min-width: 24px;
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    """


def _colors(theme: str) -> ThemeColors:
    if theme == THEME_LIGHT:
        return _LIGHT_COLORS
    if theme == THEME_DARK:
        return _DARK_COLORS
    raise GuiSettingsError(f"样式只能应用浅色或深色主题，收到：{theme}")

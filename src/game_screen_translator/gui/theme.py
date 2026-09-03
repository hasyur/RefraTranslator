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
    success: str
    success_background: str
    warning: str
    warning_background: str
    danger: str
    danger_background: str


_LIGHT_COLORS = ThemeColors(
    window="#f5f6f8",
    panel="#ffffff",
    input="#f7f8fa",
    alternate="#eef1f5",
    text="#181b20",
    muted="#667085",
    disabled="#98a2b3",
    border="#e5e7eb",
    tab="#eef2f6",
    button="#eef1f5",
    button_hover="#e4e8ee",
    accent="#3b82f6",
    accent_hover="#2563eb",
    selection="#dbeafe",
    selected_text="#14213d",
    success="#1f9d6b",
    success_background="#eaf8f1",
    warning="#c47a14",
    warning_background="#fff5e5",
    danger="#dc4c4c",
    danger_background="#feeeee",
)

_DARK_COLORS = ThemeColors(
    window="#0f1115",
    panel="#191d24",
    input="#101319",
    alternate="#14171d",
    text="#f3f5f7",
    muted="#9ba4b0",
    disabled="#626b77",
    border="#2a3038",
    tab="#20252d",
    button="#242a33",
    button_hover="#2d3540",
    accent="#4c8dff",
    accent_hover="#6da3ff",
    selection="#203b64",
    selected_text="#ffffff",
    success="#32c48d",
    success_background="#173329",
    warning="#e7a23b",
    warning_background="#3d2e17",
    danger="#ef5b5b",
    danger_background="#402123",
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
    checkmark_url = (
        Path(__file__).resolve().parent / "assets" / "checkmark.svg"
    ).as_posix()
    return f"""
        QMainWindow, QDialog {{
            background-color: {colors.window};
            color: {colors.text};
        }}
        QWidget {{
            color: {colors.text};
            font-size: 13px;
        }}
        QWidget#launcherCentral {{ background-color: {colors.window}; }}
        QWidget#contentHost, QWidget#workspacePage {{
            background-color: {colors.window};
        }}
        QWidget#launchContent {{ background-color: transparent; }}
        QLabel {{ background-color: transparent; }}
        QLabel#secondaryText {{ color: {colors.muted}; }}
        QLabel#brandTitle {{
            color: {colors.text};
            font-size: 18px;
            font-weight: 700;
        }}
        QLabel#brandSubtitle, QLabel#cardDescription,
        QLabel#detectionQualityDetail, QLabel#pageDescription {{
            color: {colors.muted};
        }}
        QLabel#brandSubtitle {{ font-size: 12px; }}
        QLabel#currentConfigLabel {{
            color: {colors.muted};
            font-size: 11px;
            font-weight: 600;
        }}
        QLabel#pageTitle {{
            color: {colors.text};
            font-size: 20px;
            font-weight: 650;
        }}
        QLabel#pageDescription {{ font-size: 13px; }}
        QLabel#cardTitle {{
            color: {colors.text};
            font-size: 15px;
            font-weight: 650;
        }}
        QLabel#scopeBadge {{
            color: {colors.muted};
            background-color: transparent;
            padding: 1px 2px;
            font-size: 11px;
        }}
        QLabel#advancedSectionTitle {{
            color: {colors.text};
            font-size: 12px;
            font-weight: 650;
        }}
        QLabel#diagnosticText {{
            color: {colors.text};
            line-height: 1.5;
        }}
        QLabel#statusChip, QLabel#runStatusChip {{
            color: {colors.muted};
            background-color: transparent;
            border: 0;
            padding: 3px 2px;
            font-weight: 600;
        }}
        QLabel#statusChip[tone="success"], QLabel#runStatusChip[tone="success"] {{
            color: {colors.success};
        }}
        QLabel#statusChip[tone="warning"], QLabel#runStatusChip[tone="warning"] {{
            color: {colors.warning};
        }}
        QLabel#statusChip[tone="error"], QLabel#runStatusChip[tone="error"] {{
            color: {colors.danger};
        }}
        QFrame#topBar {{
            background-color: {colors.panel};
            border: 0;
            border-bottom: 1px solid {colors.border};
        }}
        QFrame#workspace {{
            background-color: {colors.window};
            border: 0;
        }}
        QFrame#sideBar {{
            background-color: {colors.alternate};
            border: 0;
            border-right: 1px solid {colors.border};
        }}
        QFrame#actionBar {{
            background-color: {colors.panel};
            border: 0;
            border-top: 1px solid {colors.border};
        }}
        QFrame#settingsCard {{
            background-color: {colors.panel};
            border: 0;
            border-radius: 10px;
        }}
        QFrame#inlinePanel, QFrame#segmentedControl,
        QFrame#appearanceControl {{
            background-color: {colors.alternate};
            border: 0;
            border-radius: 8px;
        }}
        QLabel#settingsIcon {{
            color: {colors.muted};
            font-size: 12px;
            font-weight: 600;
        }}
        QLabel#navSectionLabel {{
            color: {colors.muted};
            font-size: 11px;
            font-weight: 650;
            padding: 3px 10px 5px 10px;
        }}
        QToolButton[navItem="true"] {{
            color: {colors.muted};
            background-color: transparent;
            border: 0;
            border-left: 3px solid transparent;
            border-radius: 6px;
            padding: 10px 12px;
            text-align: left;
            font-size: 14px;
        }}
        QToolButton[navItem="true"]:hover {{
            color: {colors.text};
            background-color: {colors.button_hover};
        }}
        QToolButton[navItem="true"]:checked {{
            color: {colors.accent};
            background-color: {colors.selection};
            border-left-color: {colors.accent};
            font-weight: 650;
        }}
        QToolButton[navItem="true"]:disabled {{ color: {colors.disabled}; }}
        QScrollArea#launchScroll {{
            background-color: transparent;
            border: 0;
        }}
        QLineEdit, QComboBox, QSpinBox, QPlainTextEdit,
        QTableWidget, QAbstractItemView {{
            color: {colors.text};
            background-color: {colors.input};
            selection-background-color: {colors.selection};
            selection-color: {colors.selected_text};
            border: 1px solid {colors.border};
            border-radius: 6px;
        }}
        QLineEdit, QComboBox, QSpinBox {{
            padding: 5px 9px;
            min-height: 27px;
        }}
        QPlainTextEdit {{
            padding: 9px;
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
        QPlainTextEdit:focus, QTableWidget:focus {{
            border-color: {colors.accent};
        }}
        QLineEdit:read-only {{ color: {colors.muted}; }}
        QComboBox::drop-down {{ border: 0; width: 24px; }}
        QComboBox#themeCombo {{
            background-color: transparent;
            border: 0;
            padding-left: 4px;
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
            border: 0;
            border-radius: 6px;
            padding: 8px 14px;
        }}
        QPushButton:hover {{ background-color: {colors.button_hover}; }}
        QPushButton:pressed {{ background-color: {colors.selection}; }}
        QPushButton:disabled {{ color: {colors.disabled}; }}
        QPushButton#applyButton {{
            color: {colors.text};
            background-color: {colors.button};
            font-weight: 600;
            padding: 10px 18px;
        }}
        QPushButton#applyButton:hover {{ background-color: {colors.button_hover}; }}
        QPushButton#startButton {{
            background-color: {colors.accent};
            color: white;
            border: 0;
            border-radius: 6px;
            padding: 10px 22px;
            font-size: 15px;
            font-weight: 700;
        }}
        QPushButton#startButton:hover {{ background-color: {colors.accent_hover}; }}
        QPushButton#startButton[running="true"] {{
            background-color: {colors.danger};
        }}
        QPushButton#textActionButton {{
            color: {colors.accent};
            background-color: transparent;
            padding: 6px 8px;
            font-weight: 600;
        }}
        QPushButton#textActionButton:hover {{ background-color: {colors.selection}; }}
        QPushButton#backendOption {{
            color: {colors.muted};
            background-color: transparent;
            padding: 8px 18px;
        }}
        QPushButton#backendOption:hover {{
            color: {colors.text};
            background-color: {colors.button_hover};
        }}
        QPushButton#backendOption:checked {{
            color: {colors.accent};
            background-color: {colors.panel};
            font-weight: 650;
        }}
        QToolButton#profileAction {{
            color: {colors.text};
            background-color: {colors.button};
            border: 0;
            border-radius: 6px;
            padding: 8px 10px;
        }}
        QToolButton#profileAction:hover {{ background-color: {colors.button_hover}; }}
        QToolButton#iconButton {{
            color: {colors.muted};
            background-color: transparent;
            border: 0;
            border-radius: 6px;
            padding: 8px 10px;
            font-size: 12px;
        }}
        QToolButton#iconButton:hover {{
            color: {colors.text};
            background-color: {colors.button_hover};
        }}
        QToolButton#advancedToggle {{
            color: {colors.accent};
            background-color: transparent;
            border: 0;
            padding: 5px 0;
            font-weight: 600;
        }}
        QToolButton#advancedToggle:hover {{ color: {colors.accent_hover}; }}
        QSlider#qualitySlider {{ min-height: 24px; }}
        QSlider#qualitySlider::groove:horizontal {{
            height: 5px;
            background-color: {colors.border};
            border-radius: 2px;
        }}
        QSlider#qualitySlider::sub-page:horizontal {{
            background-color: {colors.accent};
            border-radius: 2px;
        }}
        QSlider#qualitySlider::handle:horizontal {{
            width: 16px;
            height: 16px;
            margin: -6px 0;
            background-color: {colors.panel};
            border: 3px solid {colors.accent};
            border-radius: 8px;
        }}
        QSlider#qualitySlider::handle:horizontal:hover {{
            background-color: {colors.selection};
            border-color: {colors.accent_hover};
        }}
        QRadioButton {{ spacing: 7px; background-color: transparent; }}
        QCheckBox {{ spacing: 7px; background-color: transparent; }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            background-color: {colors.input};
            border: 1px solid {colors.border};
            border-radius: 3px;
        }}
        QCheckBox::indicator:hover {{ border-color: {colors.accent}; }}
        QCheckBox::indicator:checked {{
            image: url("{checkmark_url}");
            background-color: {colors.accent};
            border-color: {colors.accent};
        }}
        QCheckBox::indicator:disabled {{
            background-color: {colors.alternate};
            border-color: {colors.disabled};
        }}
        QCheckBox::indicator:checked:disabled {{
            image: url("{checkmark_url}");
            background-color: {colors.disabled};
        }}
        QStatusBar {{
            color: {colors.muted};
            background-color: {colors.alternate};
            border: 0;
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

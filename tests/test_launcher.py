import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from game_screen_translator.branding import PRODUCT_NAME
from game_screen_translator.config import load_config
from game_screen_translator.domain import GlossaryEntry
from game_screen_translator.gui import launcher as launcher_module
from game_screen_translator.gui.launcher import LauncherWindow, PairTableEditor
from game_screen_translator.gui.theme import (
    THEME_DARK,
    THEME_LIGHT,
    gui_settings_path,
    load_gui_preferences,
    theme_stylesheet,
)
from game_screen_translator.profiles import (
    ProfileCaptureSettings,
    create_game_profile,
    load_game_profile,
    save_profile_capture_settings,
    save_profile_glossary,
)


def _write_config(path: Path) -> None:
    path.write_text(
        """
[translation]
provider = "openai_compatible"
base_url = "http://127.0.0.1:1234/v1"
model = "hy-mt1.5-7b"

[live]
left = 1
top = 2
width = 3
height = 4
""",
        encoding="utf-8",
    )


def test_launcher_loads_profile_tables_and_saved_region(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    config = load_config(config_path)
    profile = create_game_profile(
        config_path,
        config,
        "game",
        display_name="测试游戏",
    )
    save_profile_capture_settings(
        profile,
        ProfileCaptureSettings(monitor_index=0, region=(100, 200, 800, 300)),
    )
    save_profile_glossary(profile, (GlossaryEntry("仕事", "委托"),))
    profile.cache.set_manual_correction(
        "待て。",
        "等等。",
        source_language=config.ocr.language,
        target_language=config.translation.target_language,
    )

    window = LauncherWindow(config_path, probe_ocr_devices=False)

    assert window.windowTitle() == PRODUCT_NAME
    assert window.profile_combo.currentData() == "game"
    assert window.server_url_combo.currentText() == "http://127.0.0.1:1234/v1"
    assert window.model_combo.currentText() == "hy-mt1.5-7b"
    assert window.max_concurrency_spin.value() == 2
    assert window.ocr_device_combo.currentData() == "cpu"
    assert window.ocr_filter_checkbox.isChecked()
    assert not window.dynamic_roi_checkbox.isChecked()
    assert window.settle_rescan_spin.value() == 500
    assert window.idle_rescan_spin.value() == 2000
    assert window.ocr_cooldown_spin.value() == 0
    assert window._current_region() == (100, 200, 800, 300)
    assert window._glossary_editor.pairs() == (("仕事", "委托"),)
    assert window._correction_editor.pairs() == (("待て。", "等等。"),)
    assert "测试游戏 (game)" in window.info_label.text()

    for spin, value in zip(window.region_spins, (20, 30, 900, 240)):
        spin.setValue(value)
    assert window._save_capture_settings()
    loaded = load_game_profile(config_path, config, "game")
    assert loaded.capture_settings.region == (20, 30, 900, 240)
    window.close()
    app.processEvents()


def test_pair_editor_ignores_fully_blank_row_but_rejects_half_row() -> None:
    app = QApplication.instance() or QApplication([])
    editor = PairTableEditor(
        left_header="原文",
        right_header="译文",
        save_text="保存",
        save_callback=lambda: None,
    )
    editor.add_row()
    editor.add_row("原文", "译文")
    assert editor.pairs() == (("原文", "译文"),)
    editor.table.item(0, 0).setText("只有原文")

    import pytest

    with pytest.raises(ValueError, match="同时填写"):
        editor.pairs()
    editor.close()
    app.processEvents()


def test_launcher_starts_live_with_same_isolated_interpreter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    config = load_config(config_path)
    create_game_profile(config_path, config, "game")
    window = LauncherWindow(config_path, probe_ocr_devices=False)
    calls = []

    class FakeProcess:
        pid = 4321

        @staticmethod
        def poll():
            return None

    def fake_popen(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return FakeProcess()

    monkeypatch.setattr(launcher_module.subprocess, "Popen", fake_popen)
    window.server_url_combo.setCurrentText("http://203.0.113.10:9000/v1")
    window.model_combo.setCurrentText("alternate-model")
    window.max_concurrency_spin.setValue(6)
    window.settle_rescan_spin.setValue(800)
    window.idle_rescan_spin.setValue(4000)
    window.ocr_cooldown_spin.setValue(100)
    window.dynamic_roi_checkbox.setChecked(True)

    window._start_live()

    assert calls[0][0][0] == sys.executable
    assert calls[0][0][1:6] == [
        "-m",
        "game_screen_translator",
        "--config",
        str(config_path.resolve()),
        "live",
    ]
    assert calls[0][0][-2:] == ["--profile", "game"]
    assert calls[0][1]["cwd"] == tmp_path
    assert calls[0][1]["stderr"] is launcher_module.subprocess.STDOUT
    assert calls[0][1]["env"]["PYTHONUNBUFFERED"] == "1"
    assert window._live_log_path == tmp_path / "output" / "live.log"
    assert window._live_log_path.read_text(encoding="utf-8").startswith(
        "RefraTranslator live diagnostics"
    )
    saved = load_config(config_path)
    assert saved.translation.base_url == "http://203.0.113.10:9000/v1"
    assert saved.translation.model == "alternate-model"
    assert saved.translation.max_concurrency == 6
    assert saved.ocr.device == "cpu"
    assert saved.live.settle_rescan_ms == 800
    assert saved.live.idle_rescan_ms == 4000
    assert saved.live.ocr_cooldown_ms == 100
    assert saved.live.dynamic_roi_enabled is True
    window._live_monitor.stop()
    window.close()
    app.processEvents()


def test_launcher_restores_and_reports_live_process_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    window = LauncherWindow(config_path, probe_ocr_devices=False)
    window._live_log_path.parent.mkdir(parents=True)
    window._live_log_path.write_text("OCR ready\nactual capture error\n", encoding="utf-8")

    class FailedProcess:
        @staticmethod
        def poll():
            return 7

    errors = []
    monkeypatch.setattr(
        window,
        "_show_error",
        lambda title, error: errors.append((title, str(error))),
    )
    window._live_process = FailedProcess()
    window._live_monitor.start()

    window._check_live_process()

    assert window._live_process is None
    assert not window._live_monitor.isActive()
    assert errors[0][0] == "实时翻译进程异常退出"
    assert "退出码：7" in errors[0][1]
    assert "actual capture error" in errors[0][1]
    window.close()
    app.processEvents()


def test_launcher_theme_switch_has_contrast_and_persists_project_locally(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    window = LauncherWindow(config_path, probe_ocr_devices=False)

    settings_path = gui_settings_path(config_path)
    assert settings_path.parent == tmp_path
    assert not settings_path.exists()

    window.theme_combo.setCurrentIndex(window.theme_combo.findData(THEME_DARK))
    app.processEvents()

    assert window.property("effectiveTheme") == THEME_DARK
    assert window.palette().color(QPalette.ColorRole.Window).name() == "#171a21"
    assert window.palette().color(QPalette.ColorRole.WindowText).name() == "#f2f4f7"
    assert load_gui_preferences(config_path).theme == THEME_DARK
    assert settings_path.is_file()
    window.close()
    app.processEvents()

    restored = LauncherWindow(config_path, probe_ocr_devices=False)
    assert restored.theme_combo.currentData() == THEME_DARK
    assert restored.property("effectiveTheme") == THEME_DARK
    restored.theme_combo.setCurrentIndex(restored.theme_combo.findData(THEME_LIGHT))
    app.processEvents()
    assert restored.palette().color(QPalette.ColorRole.Window).name() == "#f4f6f8"
    assert restored.palette().color(QPalette.ColorRole.WindowText).name() == "#20242a"
    assert load_gui_preferences(config_path).theme == THEME_LIGHT
    restored.close()
    app.processEvents()


def test_launcher_model_choices_keep_manual_model_until_user_changes_it(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    window = LauncherWindow(config_path, probe_ocr_devices=False)
    window.model_combo.setCurrentText("manual-model")

    retained = window._set_model_choices(("server-a", "server-b", "server-a"))

    assert retained
    assert window.model_combo.currentText() == "manual-model"
    assert [window.model_combo.itemText(index) for index in range(3)] == [
        "manual-model",
        "server-a",
        "server-b",
    ]

    window.model_combo.setCurrentText("")
    assert not window._set_model_choices(("server-a", "server-b"))
    assert window.model_combo.currentText() == "server-a"
    window.close()
    app.processEvents()


def test_launcher_saves_selected_gpu_device(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    window = LauncherWindow(config_path, probe_ocr_devices=False)
    gpu_index = window.ocr_device_combo.findData("gpu:1")
    if gpu_index < 0:
        window.ocr_device_combo.addItem("GPU 1 · test", "gpu:1")
        gpu_index = window.ocr_device_combo.count() - 1
    window.ocr_device_combo.setCurrentIndex(gpu_index)

    assert window._save_translation_settings(announce=False)

    assert load_config(config_path).ocr.device == "gpu:1"
    window.close()
    app.processEvents()


def test_launcher_saves_and_restores_ocr_filter_switch(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    window = LauncherWindow(config_path, probe_ocr_devices=False)
    assert window.ocr_filter_checkbox.isChecked()
    window.ocr_filter_checkbox.setChecked(False)

    assert window._save_translation_settings(announce=False)
    assert load_config(config_path).ocr.text_filter_enabled is False
    assert "过滤关" in window.service_status_label.text()
    window.close()
    app.processEvents()

    restored = LauncherWindow(config_path, probe_ocr_devices=False)
    assert not restored.ocr_filter_checkbox.isChecked()
    restored.close()
    app.processEvents()


def test_launcher_saves_and_restores_live_ocr_timings(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    window = LauncherWindow(config_path, probe_ocr_devices=False)
    window.settle_rescan_spin.setValue(750)
    window.idle_rescan_spin.setValue(3500)
    window.ocr_cooldown_spin.setValue(125)

    assert window._save_translation_settings(announce=False)
    saved = load_config(config_path)
    assert saved.live.settle_rescan_ms == 750
    assert saved.live.idle_rescan_ms == 3500
    assert saved.live.ocr_cooldown_ms == 125
    assert "补扫 750 ms" in window.service_status_label.text()
    assert "兜底 3500 ms" in window.service_status_label.text()
    assert "冷却 125 ms" in window.service_status_label.text()
    window.close()
    app.processEvents()

    restored = LauncherWindow(config_path, probe_ocr_devices=False)
    assert restored.settle_rescan_spin.value() == 750
    assert restored.idle_rescan_spin.value() == 3500
    assert restored.ocr_cooldown_spin.value() == 125
    restored.close()
    app.processEvents()


def test_launcher_dynamic_roi_switch_disables_only_legacy_timing_controls(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    window = LauncherWindow(config_path, probe_ocr_devices=False)
    filter_enabled_before = window.ocr_filter_checkbox.isEnabled()

    window.dynamic_roi_checkbox.setChecked(True)

    force_disabled = Qt.WidgetAttribute.WA_ForceDisabled
    assert window.settle_rescan_spin.testAttribute(force_disabled)
    assert window.idle_rescan_spin.testAttribute(force_disabled)
    assert window.ocr_cooldown_spin.testAttribute(force_disabled)
    assert window.ocr_filter_checkbox.isEnabled() == filter_enabled_before
    assert window._save_translation_settings(announce=False)
    assert load_config(config_path).live.dynamic_roi_enabled is True
    assert "动态 ROI 开" in window.service_status_label.text()

    window.dynamic_roi_checkbox.setChecked(False)
    assert not window.settle_rescan_spin.testAttribute(force_disabled)
    assert not window.idle_rescan_spin.testAttribute(force_disabled)
    assert not window.ocr_cooldown_spin.testAttribute(force_disabled)
    window.close()
    app.processEvents()


def test_gpu_device_probe_runs_in_isolated_interpreter(monkeypatch) -> None:
    calls = []

    def fake_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout="gpu:1 · Paddle 3.3.1 · CUDA 12.9\n",
            stderr="",
        )

    monkeypatch.setattr(launcher_module.subprocess, "run", fake_run)

    description = launcher_module._validate_ocr_device_isolated("gpu:1")

    assert description == "gpu:1 · Paddle 3.3.1 · CUDA 12.9"
    assert calls[0][0][0] == sys.executable
    assert calls[0][0][-1] == "gpu:1"
    assert calls[0][1]["timeout"] == 20


def test_launcher_lists_only_gpu_devices_reported_by_paddle(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    config_path = tmp_path / "config.toml"
    _write_config(config_path)
    window = LauncherWindow(config_path, probe_ocr_devices=False)

    window._set_ocr_device_choices(
        (
            ("cpu", "CPU"),
            ("gpu:0", "GPU 0 · NVIDIA GeForce RTX 4070 Laptop GPU"),
        )
    )

    assert window.ocr_device_combo.currentData() == "cpu"
    assert window.ocr_device_combo.findData("gpu:0") >= 0
    assert window.ocr_device_combo.findData("gpu:1") < 0
    assert "RTX 4070 Laptop GPU" in window.ocr_device_combo.itemText(1)
    window.close()
    app.processEvents()


def test_ocr_device_probe_parser_ignores_paddle_diagnostics() -> None:
    output = """Paddle diagnostic line
REFRA_OCR_DEVICES=[[\"cpu\", \"CPU\"], [\"gpu:0\", \"GPU 0 · NVIDIA RTX\"]]
"""

    assert launcher_module._parse_ocr_device_probe_output(output) == (
        ("cpu", "CPU"),
        ("gpu:0", "GPU 0 · NVIDIA RTX"),
    )


def test_light_theme_checkbox_uses_a_contrasting_checked_indicator() -> None:
    stylesheet = theme_stylesheet(THEME_LIGHT)

    assert "QCheckBox::indicator:checked" in stylesheet
    assert "background-color: #1677ff" in stylesheet
    assert "checkmark.svg" in stylesheet

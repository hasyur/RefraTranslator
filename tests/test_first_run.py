import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QLabel

from game_screen_translator import first_run
from game_screen_translator.runtime_resources import OcrResource, OcrResourceInventory


def test_ready_first_run_cleans_successful_download_cache_without_opening_a_window(
    tmp_path: Path, monkeypatch,
) -> None:
    config = tmp_path / "installed-app" / "config.toml"
    inventory = OcrResourceInventory((OcrResource("ready resources", 0, True),))
    monkeypatch.setattr(first_run, "inspect_ocr_resources", lambda _config: inventory)
    cleaned = []
    monkeypatch.setattr(first_run, "cleanup_prepared_downloads", lambda path: cleaned.append(path))
    monkeypatch.setattr(first_run, "OcrResourcesWindow", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("ready resources must not open preparation window")))
    assert first_run.main(["--config", str(config)]) == 0
    assert cleaned == [config]


@pytest.fixture
def application():
    app = QApplication.instance() or QApplication([])
    yield app


def _inventory() -> OcrResourceInventory:
    return OcrResourceInventory((
        OcrResource("GPU OCR 运行依赖", 3 * 1024**3, False, downloaded_bytes=1024**3),
        OcrResource("文字检测模型", 1024**2, False),
        OcrResource("文字识别模型", 0, True),
    ))


@pytest.mark.parametrize("dark", [True, False])
def test_preparation_text_uses_readable_system_palette(application, tmp_path, dark):
    original = application.palette()
    palette = QPalette(original)
    background = QColor("#202020" if dark else "#ffffff")
    foreground = QColor("#f4f4f4" if dark else "#202020")
    palette.setColor(QPalette.ColorRole.Window, background)
    palette.setColor(QPalette.ColorRole.WindowText, foreground)
    application.setPalette(palette)
    window = first_run.OcrResourcesWindow(tmp_path / "config.toml", _inventory())
    try:
        window.show()
        application.processEvents()
        labels = [window.progress_label, window.overall_progress_label, window.total_label]
        labels.extend(
            label for label in window.findChildren(QLabel)
            if label.text() == "准备 OCR 资源" or "安装包已包含" in label.text()
        )
        for label in labels:
            assert label.palette().color(QPalette.ColorRole.WindowText) == foreground
        assert window.overall_progress_bar.height() >= 14
        assert window.progress_bar.height() >= 14
    finally:
        window.close()
        application.setPalette(original)


def test_overall_download_progress_survives_file_switch_install_and_cancel(application, tmp_path):
    window = first_run.OcrResourcesWindow(tmp_path / "config.toml", _inventory())
    try:
        assert window.overall_progress_bar.value() == 33
        assert "含缓存" in window.overall_progress_label.text()
        window._update_progress("overall", "", 2 * 1024**3, 4 * 1024**3)
        window._update_progress("download", "wheel-a 1.0", 900, 1000)
        assert window.overall_progress_bar.value() == 50
        assert window.progress_bar.value() == 90
        window._update_progress("download", "wheel-b 1.0", 10, 100)
        assert window.overall_progress_bar.value() == 50
        assert window.progress_bar.value() == 10
        window._update_progress("install", "Processing wheel-a", 0, 1)
        assert window.overall_progress_bar.value() == 50
        assert window.progress_bar.maximum() == 0
        assert window.progress_label.text() == "正在安装 OCR 运行依赖……"
        window._finish_failure("", True)
        assert window.overall_progress_bar.value() == 50
        assert "可续传" in window.overall_progress_label.text()
        window._show_inventory(_inventory())
        assert window.overall_progress_bar.value() == 33
        window._update_progress("overall", "", 4 * 1024**3, 4 * 1024**3)
        assert window.overall_progress_bar.value() == 100
        assert "等待安装和校验" in window.overall_progress_label.text()
        assert not window.preparation_complete
        window._finish_success(OcrResourceInventory((OcrResource("ready", 0, True),)))
        assert window.preparation_complete
        assert "资源已就绪" in window.overall_progress_label.text()
    finally:
        window.close()


def test_worker_delivers_multi_gibibyte_overall_progress_without_integer_overflow(
    application, tmp_path, monkeypatch,
):
    def prepare(_path, *, progress, cancel):
        progress("overall", "", 3 * 1024**3, 4 * 1024**3)
        return _inventory()

    monkeypatch.setattr(first_run, "prepare_ocr_resources", prepare)
    window = first_run.OcrResourcesWindow(tmp_path / "config.toml", _inventory())
    worker = first_run._PreparationWorker(tmp_path / "config.toml", first_run.threading.Event())
    worker.progress.connect(window._update_progress)
    try:
        worker.start()
        assert worker.wait(5000)
        application.processEvents()
        assert window.overall_progress_bar.value() == 75
        assert "3.00 GiB / 4.00 GiB" in window.overall_progress_label.text()
    finally:
        window.close()

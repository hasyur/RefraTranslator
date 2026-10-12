"""Qt first-run screen for preparing the bundled NVIDIA OCR runtime."""

from __future__ import annotations

import argparse
import threading
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from game_screen_translator.runtime_resources import (
    OcrPreparationCancelled,
    OcrPreparationError,
    OcrResourceInventory,
    inspect_ocr_resources,
    prepare_ocr_resources,
)


def _format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "未知"
    if size_bytes >= 1024**3:
        return f"{size_bytes / 1024**3:.2f} GiB"
    if size_bytes >= 1024**2:
        return f"{size_bytes / 1024**2:.1f} MiB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KiB"
    return f"{size_bytes} B"


class _PreparationWorker(QThread):
    progress = Signal(str, str, int, int)
    completed = Signal(object)
    failed = Signal(str, bool)

    def __init__(self, config_path: Path, cancel: threading.Event) -> None:
        super().__init__()
        self.config_path = config_path
        self.cancel = cancel

    def run(self) -> None:
        try:
            inventory = prepare_ocr_resources(
                self.config_path,
                progress=lambda phase, label, done, total: self.progress.emit(
                    phase,
                    label,
                    done,
                    total,
                ),
                cancel=self.cancel,
            )
        except OcrPreparationCancelled as exc:
            self.failed.emit(str(exc), True)
        except (OcrPreparationError, OSError, RuntimeError) as exc:
            self.failed.emit(str(exc), False)
        else:
            self.completed.emit(inventory)


class OcrResourcesWindow(QDialog):
    def __init__(
        self,
        config_path: Path,
        inventory: OcrResourceInventory,
        *,
        duration_seconds: float | None = None,
    ) -> None:
        super().__init__()
        self.config_path = config_path.resolve()
        self.inventory = inventory
        self.cancel_event: threading.Event | None = None
        self.worker: _PreparationWorker | None = None
        self._row_by_name: dict[str, int] = {}
        self.preparation_complete = False
        self._closing_after_cancel = False
        self.setWindowTitle("RefraTranslator · 首次运行准备")
        self.setMinimumSize(720, 500)
        self.resize(820, 590)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(14)

        title = QLabel("准备 OCR 资源")
        title.setStyleSheet("color: #1d2938; font-size: 24px; font-weight: 700;")
        layout.addWidget(title)

        description = QLabel(
            "安装包已包含应用和界面运行时。首次使用屏幕识别前，需要准备 "
            "NVIDIA GPU OCR 运行依赖，以及当前配置的检测和识别模型。"
        )
        description.setWordWrap(True)
        description.setStyleSheet("color: #596579; font-size: 14px;")
        layout.addWidget(description)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(("资源", "下载大小", "状态", "详情"))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        self.total_label = QLabel()
        self.total_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(self.total_label)

        self.progress_label = QLabel("资源通过固定版本、文件大小和 SHA-256 清单核对。")
        self.progress_label.setWordWrap(True)
        self.progress_label.setStyleSheet("color: #596579;")
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.error_label.setStyleSheet("color: #ff9d9d;")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.later_button = QPushButton("稍后准备")
        self.later_button.clicked.connect(self._defer)
        buttons.addWidget(self.later_button)
        self.prepare_button = QPushButton("下载并准备")
        self.prepare_button.setDefault(True)
        self.prepare_button.clicked.connect(self._start_preparation)
        buttons.addWidget(self.prepare_button)
        layout.addLayout(buttons)

        self._show_inventory(inventory)
        if duration_seconds is not None:
            QTimer.singleShot(max(0, int(duration_seconds * 1000)), self._defer)

    def _show_inventory(self, inventory: OcrResourceInventory) -> None:
        self.inventory = inventory
        self.table.setRowCount(0)
        self._row_by_name.clear()
        for resource in inventory.resources:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._row_by_name[resource.name] = row
            self.table.setItem(row, 0, QTableWidgetItem(resource.name))
            self.table.setItem(
                row,
                1,
                QTableWidgetItem(_format_size(resource.remaining_download_bytes)),
            )
            if resource.available:
                status = "已有"
            elif resource.size_bytes is None:
                status = "无法确认大小"
            elif resource.downloaded_bytes >= resource.size_bytes:
                status = "已缓存，待安装/校验"
            elif resource.downloaded_bytes:
                status = f"已缓存 {_format_size(resource.downloaded_bytes)}，可续传"
            else:
                status = "缺少"
            self.table.setItem(row, 2, QTableWidgetItem(status))
            self.table.setItem(row, 3, QTableWidgetItem(resource.detail))
        total = inventory.download_size_bytes
        self.total_label.setText(
            "全部资源已就绪"
            if inventory.ready
            else f"仍需下载：{_format_size(total)}（已安装和缓存内容已扣除）"
        )
        if inventory.errors:
            self.error_label.setText("\n".join(inventory.errors))
            self.error_label.show()
        else:
            self.error_label.clear()
            self.error_label.hide()
        self.prepare_button.setText("重新检查" if inventory.errors else "下载并准备")
        self.prepare_button.setEnabled(not inventory.ready)

    @Slot()
    def _start_preparation(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            if self.cancel_event is not None:
                self.cancel_event.set()
                self.progress_label.setText("正在停止；已下载的临时文件会保留以便续传。")
                self.prepare_button.setEnabled(False)
            return

        try:
            latest = inspect_ocr_resources(self.config_path)
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self._show_inventory(latest)
        if latest.ready:
            self._finish_success(latest)
            return
        if latest.download_size_bytes is None:
            self.progress_label.setText("资源清单不完整；检查安装包后重试。")
            return

        self.error_label.hide()
        self.later_button.setEnabled(False)
        self.prepare_button.setText("取消准备")
        self.prepare_button.setEnabled(True)
        self.progress_label.setText("正在下载和校验缺少的资源……")
        self.progress_bar.setRange(0, 0)
        self.cancel_event = threading.Event()
        self.worker = _PreparationWorker(self.config_path, self.cancel_event)
        self.worker.progress.connect(self._update_progress)
        self.worker.completed.connect(self._finish_success)
        self.worker.failed.connect(self._finish_failure)
        self.worker.start()

    @Slot(str, str, int, int)
    def _update_progress(self, phase: str, label: str, done: int, total: int) -> None:
        if phase == "download" and total > 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(min(100, int(done * 100 / total)))
            self.progress_label.setText(f"正在下载 {label} · {_format_size(done)} / {_format_size(total)}")
            row = self._row_for_label(label)
            if row is not None:
                self.table.item(row, 2).setText(f"下载中 {min(100, int(done * 100 / total))}%")
        elif phase == "install":
            self.progress_bar.setRange(0, 0)
            self.progress_label.setText(label or "正在安装 OCR 运行依赖……")
        elif phase == "ready":
            self.progress_label.setText(f"已就绪：{label}")
            row = self._row_for_label(label)
            if row is not None:
                self.table.item(row, 2).setText("已校验")

    def _row_for_label(self, label: str) -> int | None:
        if label.startswith("PP-OCRv6_small_det"):
            return self._row_by_name.get("文字检测模型")
        if label.startswith("PP-OCRv6_small_rec"):
            return self._row_by_name.get("文字识别模型")
        return self._row_by_name.get("GPU OCR 运行依赖")

    @Slot(object)
    def _finish_success(self, inventory: OcrResourceInventory) -> None:
        self.preparation_complete = inventory.ready
        self._show_inventory(inventory)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_label.setText("OCR 资源已准备并校验完成。正在打开工作台……")
        self.accept()

    @Slot(str, bool)
    def _finish_failure(self, message: str, cancelled: bool) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        if cancelled:
            self.progress_label.setText("已取消；已完成资源保留，未完成下载可续传。")
        else:
            self.progress_label.setText("准备失败；修复连接或磁盘问题后可以重试。")
            self.error_label.setText(message)
            self.error_label.show()
        self.prepare_button.setText("重试准备")
        self.prepare_button.setEnabled(True)
        self.later_button.setEnabled(True)
        if self._closing_after_cancel:
            self._closing_after_cancel = False
            self.reject()

    @Slot()
    def _defer(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self._closing_after_cancel = True
            if self.cancel_event is not None:
                self.cancel_event.set()
            self.progress_label.setText("正在停止并保留下载进度……")
            self.later_button.setEnabled(False)
            self.prepare_button.setEnabled(False)
            return
        self.reject()

    @Slot()
    def reject(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self._closing_after_cancel = True
            if self.cancel_event is not None:
                self.cancel_event.set()
            self.progress_label.setText("正在停止并保留下载进度……")
            self.later_button.setEnabled(False)
            self.prepare_button.setEnabled(False)
            return
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt callback name
        if self.worker is not None and self.worker.isRunning():
            self._closing_after_cancel = True
            if self.cancel_event is not None:
                self.cancel_event.set()
            event.ignore()
            return
        event.accept()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare RefraTranslator OCR resources")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--duration", type=float, default=None)
    args = parser.parse_args(argv)

    from PySide6.QtWidgets import QApplication

    inventory = inspect_ocr_resources(args.config)
    if inventory.ready:
        return 0
    app = QApplication.instance() or QApplication([])
    window = OcrResourcesWindow(
        args.config,
        inventory,
        duration_seconds=args.duration,
    )
    window.exec()
    return 0 if window.preparation_complete or not window.inventory.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())

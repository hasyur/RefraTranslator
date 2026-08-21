from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

from game_screen_translator.branding import GUI_PROCESS_NAME, PRODUCT_NAME
from game_screen_translator.config import (
    AppConfig,
    ConfigError,
    DEFAULT_DARK_OVERLAY_OPACITY,
    LiveConfig,
    load_config,
    save_runtime_selection,
)
from game_screen_translator.domain import GlossaryEntry
from game_screen_translator.profiles import (
    GameProfile,
    ProfileCaptureSettings,
    ProfileError,
    create_game_profile,
    list_game_profiles,
    load_game_profile,
    save_profile_capture_settings,
    save_profile_glossary,
)
from game_screen_translator.translation.transport import (
    TranslationTransportError,
    parse_model_ids,
)

from .region_selector import RegionSelector
from .theme import (
    GuiPreferences,
    GuiSettingsError,
    THEME_OPTIONS,
    effective_theme,
    load_gui_preferences,
    save_gui_preferences,
    theme_palette,
    theme_stylesheet,
)


def _startup_message(message: str) -> None:
    print(f"[{PRODUCT_NAME} GUI] {message}", flush=True)


_BLUR_MODE_DARK = "dark_blur"
_BLUR_MODE_ONLY = "blur_only"
_DETECTION_QUALITY_PRESETS = (
    ("性能", 0.375),
    ("质量", 0.5),
    ("超质量", 0.75),
)
_DETECTION_MIN_SIDE = 640
_DETECTION_MAX_SIDE = 4096
_DETECTION_ALIGNMENT = 32
_TEXT_MERGE_MIN_DETECTION_SCALE = 0.5


def _detection_max_side_for_display(display_long_side: int, scale: float) -> int:
    target = max(
        _DETECTION_MIN_SIDE,
        min(_DETECTION_MAX_SIDE, display_long_side * scale),
    )
    return int(
        (target + _DETECTION_ALIGNMENT / 2) // _DETECTION_ALIGNMENT
    ) * _DETECTION_ALIGNMENT


def _log_tail(path: Path, *, max_characters: int = 4000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        return f"无法读取日志：{exc}"
    if not text:
        return "日志尚无输出。"
    return text[-max_characters:]


try:
    from PySide6.QtCore import QTimer, Qt, QUrl
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSlider,
        QSpinBox,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - exercised only without GUI extra
    raise RuntimeError("尚未安装 GUI 依赖。请运行：.\\bootstrap.ps1 -WithGui") from exc


def _install_ui_font(app: QApplication, config: AppConfig, config_path: Path) -> None:
    candidates: list[Path] = []
    if config.preview.font_path:
        configured = Path(config.preview.font_path)
        candidates.append(
            configured if configured.is_absolute() else config_path.parent / configured
        )
    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates.extend(
        windows_dir / "Fonts" / name
        for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf")
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(candidate))
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))
            return


def _validate_ocr_device_isolated(device: str) -> str:
    """Probe Paddle in a short-lived process so the launcher keeps no GPU runtime."""
    if device == "cpu":
        return "CPU"
    probe = (
        "import sys; "
        "from game_screen_translator.ocr.paddle import validate_ocr_device; "
        "print(validate_ocr_device(sys.argv[1]))"
    )
    try:
        completed = subprocess.run(
            (sys.executable, "-c", probe, device),
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"无法检查 OCR 设备 {device}：{exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        if len(detail) > 1200:
            detail = detail[-1200:]
        raise RuntimeError(detail or f"OCR 设备检查退出码 {completed.returncode}")
    lines = tuple(line.strip() for line in completed.stdout.splitlines() if line.strip())
    if not lines:
        raise RuntimeError("OCR 设备检查没有返回结果")
    return lines[-1]


_OCR_DEVICE_PROBE_MARKER = "REFRA_OCR_DEVICES="
_OCR_DEVICE_PROBE_TIMEOUT_SECONDS = 20.0


def _parse_ocr_device_probe_output(output: str) -> tuple[tuple[str, str], ...]:
    payload = None
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped.startswith(_OCR_DEVICE_PROBE_MARKER):
            payload = json.loads(stripped[len(_OCR_DEVICE_PROBE_MARKER) :])
            break
    if not isinstance(payload, list):
        raise RuntimeError("OCR 硬件检测没有返回设备列表")

    devices: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, list) or len(item) != 2:
            raise RuntimeError("OCR 硬件检测返回了无效设备")
        device, label = item
        if not isinstance(device, str) or not isinstance(label, str):
            raise RuntimeError("OCR 硬件检测返回了无效设备")
        if device != "cpu" and not (
            device.startswith("gpu:") and device[4:].isdigit()
        ):
            raise RuntimeError(f"OCR 硬件检测返回了未知设备：{device}")
        if not label.strip() or device in seen:
            continue
        devices.append((device, label.strip()))
        seen.add(device)
    if "cpu" not in seen:
        devices.insert(0, ("cpu", "CPU"))
    return tuple(devices)


class NewProfileDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新建游戏 Profile")
        self.setMinimumWidth(430)
        self.profile_id_edit = QLineEdit()
        self.profile_id_edit.setPlaceholderText("例如 cyberpunk2077")
        self.display_name_edit = QLineEdit()
        self.display_name_edit.setPlaceholderText("例如 赛博朋克 2077")
        form = QFormLayout()
        form.addRow("Profile ID", self.profile_id_edit)
        form.addRow("显示名称", self.display_name_edit)
        note = QLabel("ID 创建后用于目录名，只能包含文字、数字、连字符和下划线。")
        note.setWordWrap(True)
        note.setObjectName("secondaryText")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    @property
    def profile_id(self) -> str:
        return self.profile_id_edit.text().strip()

    @property
    def display_name(self) -> str | None:
        value = self.display_name_edit.text().strip()
        return value or None


class PairTableEditor(QWidget):
    def __init__(
        self,
        *,
        left_header: str,
        right_header: str,
        save_text: str,
        save_callback,
    ) -> None:
        super().__init__()
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels((left_header, right_header))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        add_button = QPushButton("添加一行")
        remove_button = QPushButton("删除选中行")
        save_button = QPushButton(save_text)
        add_button.clicked.connect(lambda: self.add_row())
        remove_button.clicked.connect(self.remove_selected_rows)
        save_button.clicked.connect(save_callback)
        buttons = QHBoxLayout()
        buttons.addWidget(add_button)
        buttons.addWidget(remove_button)
        buttons.addStretch(1)
        buttons.addWidget(save_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(buttons)

    def add_row(self, left: str = "", right: str = "") -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(left))
        self.table.setItem(row, 1, QTableWidgetItem(right))
        if not left and not right:
            self.table.setCurrentCell(row, 0)
            self.table.editItem(self.table.item(row, 0))

    def remove_selected_rows(self) -> None:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        if not rows and self.table.currentRow() >= 0:
            rows.add(self.table.currentRow())
        for row in sorted(rows, reverse=True):
            self.table.removeRow(row)

    def set_pairs(self, pairs) -> None:
        self.table.setRowCount(0)
        for left, right in pairs:
            self.add_row(left, right)

    def pairs(self) -> tuple[tuple[str, str], ...]:
        values: list[tuple[str, str]] = []
        for row in range(self.table.rowCount()):
            left_item = self.table.item(row, 0)
            right_item = self.table.item(row, 1)
            left = left_item.text().strip() if left_item is not None else ""
            right = right_item.text().strip() if right_item is not None else ""
            if not left and not right:
                continue
            if not left or not right:
                raise ValueError(f"第 {row + 1} 行的原文和译文必须同时填写")
            values.append((left, right))
        return tuple(values)


class LauncherWindow(QMainWindow):
    def __init__(
        self,
        config_path: Path,
        *,
        probe_ocr_devices: bool = True,
    ) -> None:
        super().__init__()
        self._config_path = config_path.resolve()
        self._config: AppConfig = load_config(self._config_path)
        app = QApplication.instance()
        if app is not None:
            _install_ui_font(app, self._config, self._config_path)
        try:
            preferences = load_gui_preferences(self._config_path)
            self._preferences_warning: str | None = None
        except (GuiSettingsError, OSError) as exc:
            preferences = GuiPreferences()
            self._preferences_warning = str(exc)
        self._theme_preference = preferences.theme
        self._effective_theme = ""
        self._profile: GameProfile | None = None
        self._network_manager = QNetworkAccessManager(self)
        self._model_reply: QNetworkReply | None = None
        self._live_process: subprocess.Popen | None = None
        self._live_log_path = self._config_path.parent / "output" / "live.log"
        self._live_monitor = QTimer(self)
        self._live_monitor.setInterval(500)
        self._live_monitor.timeout.connect(self._check_live_process)
        self._ocr_device_probe_process: subprocess.Popen | None = None
        self._ocr_device_probe_started_at: float | None = None
        self._ocr_device_probe_monitor = QTimer(self)
        self._ocr_device_probe_monitor.setInterval(100)
        self._ocr_device_probe_monitor.timeout.connect(self._check_ocr_device_probe)
        self.setWindowTitle(PRODUCT_NAME)
        self.resize(960, 700)
        self.setMinimumSize(780, 580)
        self._apply_theme()
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._system_theme_changed)

        central = QWidget()
        central.setObjectName("launcherCentral")
        root = QVBoxLayout(central)
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("当前游戏"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(320)
        self.profile_combo.currentIndexChanged.connect(self._load_selected_profile)
        new_profile_button = QPushButton("新建 Profile")
        refresh_button = QPushButton("刷新")
        new_profile_button.clicked.connect(self._create_profile)
        refresh_button.clicked.connect(lambda: self.refresh_profiles())
        profile_row.addWidget(self.profile_combo, 1)
        profile_row.addWidget(new_profile_button)
        profile_row.addWidget(refresh_button)
        profile_row.addSpacing(10)
        profile_row.addWidget(QLabel("界面"))
        self.theme_combo = QComboBox()
        self.theme_combo.setMinimumWidth(105)
        for value, label in THEME_OPTIONS:
            self.theme_combo.addItem(label, value)
        theme_index = self.theme_combo.findData(self._theme_preference)
        self.theme_combo.setCurrentIndex(max(theme_index, 0))
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)
        profile_row.addWidget(self.theme_combo)
        root.addLayout(profile_row)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_launch_tab(), "启动与区域")
        self._glossary_editor = PairTableEditor(
            left_header="游戏原文",
            right_header="固定译名",
            save_text="保存术语表",
            save_callback=self._save_glossary,
        )
        self.tabs.addTab(self._glossary_editor, "术语表")
        self._correction_editor = PairTableEditor(
            left_header="OCR 原文",
            right_header="人工译文（最高优先级）",
            save_text="保存人工修订",
            save_callback=self._save_corrections,
        )
        self.tabs.addTab(self._correction_editor, "人工修订")
        self.tabs.addTab(self._build_info_tab(), "资料库状态")
        root.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("正在读取游戏 Profile……")
        self.refresh_profiles()
        self._restore_detection_quality_from_config()
        if probe_ocr_devices:
            self._start_ocr_device_probe()
        if self._preferences_warning:
            self.statusBar().showMessage(
                f"GUI 设置无效，已恢复为跟随系统：{self._preferences_warning}",
                10000,
            )

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        selected = effective_theme(self._theme_preference, app)
        self._effective_theme = selected
        self.setPalette(theme_palette(selected))
        self.setStyleSheet(theme_stylesheet(selected))
        self.setProperty("effectiveTheme", selected)

    def _theme_changed(self, index: int) -> None:
        value = self.theme_combo.itemData(index)
        if not isinstance(value, str):
            return
        previous = self._theme_preference
        self._theme_preference = value
        self._apply_theme()
        try:
            save_gui_preferences(
                self._config_path,
                GuiPreferences(theme=self._theme_preference),
            )
        except (GuiSettingsError, OSError) as exc:
            self._theme_preference = previous
            self._apply_theme()
            old_index = self.theme_combo.findData(previous)
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(max(old_index, 0))
            self.theme_combo.blockSignals(False)
            self._show_error("保存界面主题失败", exc)
            return
        label = self.theme_combo.currentText()
        self.statusBar().showMessage(f"界面已切换为“{label}”并保存", 4000)

    def _system_theme_changed(self, *args) -> None:
        if self._theme_preference == "system":
            self._apply_theme()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt callback name
        process = self._ocr_device_probe_process
        if process is not None and process.poll() is None:
            process.terminate()
        self._ocr_device_probe_monitor.stop()
        super().closeEvent(event)

    def _build_launch_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        service_form = QFormLayout()
        self._service_form = service_form
        self.server_url_combo = QComboBox()
        self.server_url_combo.setEditable(True)
        self.server_url_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.server_url_combo.addItem(self._config.translation.base_url)
        if self.server_url_combo.lineEdit() is not None:
            self.server_url_combo.lineEdit().setPlaceholderText(
                "例如 http://127.0.0.1:1234/v1"
            )
        service_form.addRow("API 服务器", self.server_url_combo)

        model_widget = QWidget()
        model_layout = QHBoxLayout(model_widget)
        model_layout.setContentsMargins(0, 0, 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.model_combo.addItem(self._config.translation.model)
        if self.model_combo.lineEdit() is not None:
            self.model_combo.lineEdit().setPlaceholderText("输入模型 ID 或读取服务器列表")
        self.refresh_models_button = QPushButton("读取模型列表")
        self.refresh_models_button.clicked.connect(self._refresh_models)
        model_layout.addWidget(self.model_combo, 1)
        model_layout.addWidget(self.refresh_models_button)
        service_form.addRow("API 模型", model_widget)

        self.max_concurrency_spin = QSpinBox()
        self.max_concurrency_spin.setRange(1, 32)
        self.max_concurrency_spin.setValue(self._config.translation.max_concurrency)
        self.max_concurrency_spin.setSuffix(" 路")
        self.max_concurrency_spin.setToolTip(
            "同时处理的翻译批次数。实际并发还受 LLM 后端限制；"
            "过高可能增加显存占用和单批延迟。"
        )
        service_form.addRow("LLM 并发", self.max_concurrency_spin)

        self.ocr_device_combo = QComboBox()
        self.ocr_device_combo.addItem("CPU", "cpu")
        configured_device = self._config.ocr.device
        device_index = self.ocr_device_combo.findData(configured_device)
        if device_index < 0:
            self.ocr_device_combo.addItem(
                f"{configured_device}（正在检测实际硬件……）",
                configured_device,
            )
            device_index = self.ocr_device_combo.count() - 1
        self.ocr_device_combo.setCurrentIndex(device_index)
        self.ocr_device_combo.setToolTip(
            "正在后台检测当前隔离环境中 Paddle 实际可用的 OCR 硬件；"
            "启动实时翻译时仍会再次隔离校验。"
        )
        service_form.addRow("OCR 设备", self.ocr_device_combo)

        detection_widget = QWidget()
        detection_layout = QHBoxLayout(detection_widget)
        detection_layout.setContentsMargins(0, 0, 0, 0)
        self.detection_quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.detection_quality_slider.setRange(
            0,
            len(_DETECTION_QUALITY_PRESETS) - 1,
        )
        self.detection_quality_slider.setSingleStep(1)
        self.detection_quality_slider.setPageStep(1)
        self.detection_quality_slider.setTickInterval(1)
        self.detection_quality_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.detection_quality_slider.setValue(1)
        self.detection_quality_slider.setToolTip(
            "按所选显示器物理长边提供 37.5%、50%、75% 三档。"
            "GUI 只保存最终 detection_max_side，不跟踪游戏窗口分辨率。"
        )
        self.detection_quality_label = QLabel()
        self.detection_quality_slider.valueChanged.connect(
            self._detection_quality_changed
        )
        detection_layout.addWidget(self.detection_quality_slider, 1)
        detection_layout.addWidget(self.detection_quality_label)
        service_form.addRow("OCR 检测质量", detection_widget)

        self.ocr_filter_checkbox = QCheckBox("启用文字过滤")
        self.ocr_filter_checkbox.setChecked(self._config.ocr.text_filter_enabled)
        self.ocr_filter_checkbox.setToolTip(
            "关闭后，图标、数字、中文和其他非源语言 OCR 文本也会进入跟踪与翻译；"
            "OCR 置信度阈值仍然有效。"
        )
        service_form.addRow("OCR 过滤", self.ocr_filter_checkbox)

        self.ocr_merge_checkbox = QCheckBox("合并文字")
        self.ocr_merge_checkbox.setChecked(self._config.ocr.text_merge_enabled)
        self.ocr_merge_checkbox.setToolTip(
            "开启后会在文字过滤和翻译前，将连续换行句子及日文竖排碎片"
            "整理成较完整的翻译块；关闭后保留 PaddleOCR 返回的原始文字框。"
            "仅在 OCR 检测质量不低于 50% 时可用，保存后从下一次实时翻译开始生效。"
        )
        service_form.addRow("OCR 排版", self.ocr_merge_checkbox)

        self.blur_mode_combo = QComboBox()
        self.blur_mode_combo.addItem("黑化模糊", _BLUR_MODE_DARK)
        self.blur_mode_combo.addItem("仅模糊（保留画面亮度）", _BLUR_MODE_ONLY)
        configured_blur_mode = (
            _BLUR_MODE_DARK
            if self._config.preview.overlay_opacity > 0
            else _BLUR_MODE_ONLY
        )
        self.blur_mode_combo.setCurrentIndex(
            max(self.blur_mode_combo.findData(configured_blur_mode), 0)
        )
        self.blur_mode_combo.setToolTip(
            "黑化模糊会在模糊后的原文字区域叠加暗层，提高白色译文对比度；"
            "仅模糊会根据文字框周边估算背景后再模糊，避免原文字颜色扩散成色块。"
            "保存后从下一次实时翻译开始生效。"
        )
        service_form.addRow("译文背景", self.blur_mode_combo)

        self.dynamic_roi_checkbox = QCheckBox("启用实验性动态 ROI")
        self.dynamic_roi_checkbox.setChecked(
            self._config.live.dynamic_roi_enabled
        )
        self.dynamic_roi_checkbox.setToolTip(
            "先用整帧 OCR 建立文字地图，再以低分辨率热图定位变化区域；"
            "Paddle 只识别合并后的最新 ROI。开启后显示 ROI 调度参数并隐藏"
            "不生效的旧全帧参数；关闭后反向切换。动态背景可能频繁触发"
            "整帧安全回退。"
        )
        service_form.addRow("OCR 调度", self.dynamic_roi_checkbox)

        self.change_poll_spin = QSpinBox()
        self.change_poll_spin.setRange(1, self._config.live.capture_fps)
        self.change_poll_spin.setValue(self._config.live.change_poll_fps)
        self.change_poll_spin.setSuffix(" Hz")
        self.change_poll_spin.setToolTip(
            "每秒取最新帧执行轻量变化检测的次数。旧全帧路径用它检查"
            "是否需要 OCR，动态 ROI 路径用它运行低分辨率热图；提高后"
            "能更早发现短暂变化，但不会直接让 Paddle 以相同频率运行。"
        )
        service_form.addRow("变化检测频率", self.change_poll_spin)

        self.clear_after_spin = QSpinBox()
        self.clear_after_spin.setRange(50, 1_000)
        self.clear_after_spin.setValue(self._config.live.clear_after_ms)
        self.clear_after_spin.setSingleStep(50)
        self.clear_after_spin.setAccelerated(True)
        self.clear_after_spin.setSuffix(" ms")
        self.clear_after_spin.setToolTip(
            "某轮有效 OCR 没有找到已显示的文字时，继续保留译文的时间；"
            "期间重新识别到同一文字便取消清除。增大可抵抗偶发漏识别和"
            "ROI 边缘波动，但真实字幕消失后也会多停留一段时间。"
        )
        service_form.addRow("译文消失宽限", self.clear_after_spin)

        self.settle_rescan_spin = QSpinBox()
        self.settle_rescan_spin.setRange(0, 60_000)
        self.settle_rescan_spin.setValue(self._config.live.settle_rescan_ms)
        self.settle_rescan_spin.setSingleStep(50)
        self.settle_rescan_spin.setAccelerated(True)
        self.settle_rescan_spin.setSuffix(" ms")
        self.settle_rescan_spin.setSpecialValueText("关闭")
        self.settle_rescan_spin.setToolTip(
            "最后一次检测到画面变化后，等待这段时间自动补扫一次；"
            "用于补全字幕绘制中途的首轮 OCR。若首轮仍在执行，只保留"
            "最新帧并在其结束及冷却后补扫；0 表示关闭。"
        )
        service_form.addRow("画面稳定补扫", self.settle_rescan_spin)

        self.idle_rescan_spin = QSpinBox()
        self.idle_rescan_spin.setRange(0, 60_000)
        self.idle_rescan_spin.setValue(self._config.live.idle_rescan_ms)
        self.idle_rescan_spin.setSingleStep(100)
        self.idle_rescan_spin.setAccelerated(True)
        self.idle_rescan_spin.setSuffix(" ms")
        self.idle_rescan_spin.setSpecialValueText("关闭")
        self.idle_rescan_spin.setToolTip(
            "从最近一次 OCR 完成开始计时；期间没有新扫描时，按此间隔"
            "兜底复查静止画面。任何 OCR 完成都会重新计时；"
            "增大可降低静止画面负载，0 表示关闭。"
        )
        service_form.addRow("静止画面兜底", self.idle_rescan_spin)

        self.ocr_cooldown_spin = QSpinBox()
        self.ocr_cooldown_spin.setRange(0, 10_000)
        self.ocr_cooldown_spin.setValue(self._config.live.ocr_cooldown_ms)
        self.ocr_cooldown_spin.setSingleStep(50)
        self.ocr_cooldown_spin.setAccelerated(True)
        self.ocr_cooldown_spin.setSuffix(" ms")
        self.ocr_cooldown_spin.setSpecialValueText("无冷却")
        self.ocr_cooldown_spin.setToolTip(
            "每次 OCR 完成后至少等待这段时间才启动下一轮；"
            "它同时约束画面变化、稳定补扫和静止兜底，但等待期间只保留"
            "最新待识别帧。增大可降低连续变化时的负载，但可能增加延迟"
            "或漏掉短字幕。"
        )
        service_form.addRow("OCR 冷却", self.ocr_cooldown_spin)

        self.roi_settle_spin = QSpinBox()
        self.roi_settle_spin.setRange(0, 10_000)
        self.roi_settle_spin.setValue(self._config.live.dynamic_roi_settle_ms)
        self.roi_settle_spin.setSingleStep(20)
        self.roi_settle_spin.setAccelerated(True)
        self.roi_settle_spin.setSuffix(" ms")
        self.roi_settle_spin.setSpecialValueText("立即")
        self.roi_settle_spin.setToolTip(
            "最后一次检测到局部变化后，画面持续稳定多久才允许提交最新 ROI；"
            "较大值更适合打字机效果，较小值响应更快。"
        )
        service_form.addRow("ROI 稳定等待", self.roi_settle_spin)

        self.roi_ocr_interval_spin = QSpinBox()
        self.roi_ocr_interval_spin.setRange(50, 10_000)
        self.roi_ocr_interval_spin.setValue(
            self._config.live.dynamic_roi_ocr_interval_ms
        )
        self.roi_ocr_interval_spin.setSingleStep(25)
        self.roi_ocr_interval_spin.setAccelerated(True)
        self.roi_ocr_interval_spin.setSuffix(" ms")
        self.roi_ocr_interval_spin.setToolTip(
            "两次 ROI OCR 提交之间的最短间隔。333 ms 约等于 3 Hz；"
            "减小会提高响应和 OCR 负载。"
        )
        service_form.addRow("ROI OCR 间隔", self.roi_ocr_interval_spin)

        self.roi_max_coalesce_spin = QSpinBox()
        self.roi_max_coalesce_spin.setRange(50, 10_000)
        self.roi_max_coalesce_spin.setValue(
            self._config.live.dynamic_roi_max_coalesce_ms
        )
        self.roi_max_coalesce_spin.setSingleStep(25)
        self.roi_max_coalesce_spin.setAccelerated(True)
        self.roi_max_coalesce_spin.setSuffix(" ms")
        self.roi_max_coalesce_spin.setToolTip(
            "连续变化最多合并多久。即使画面一直没有稳定，到达此时间也会"
            "尝试处理最新状态，避免打字机或持续运动无限等待。"
        )
        service_form.addRow("ROI 最大合并", self.roi_max_coalesce_spin)

        self.dynamic_roi_checkbox.toggled.connect(
            self._sync_ocr_scheduling_controls
        )
        self._sync_ocr_scheduling_controls(
            self.dynamic_roi_checkbox.isChecked()
        )
        layout.addLayout(service_form)

        service_actions = QHBoxLayout()
        self.service_status_label = QLabel(
            f"当前：{self._config.translation.model} · "
            f"{self._config.translation.normalized_base_url} · "
            f"并发 {self._config.translation.max_concurrency} · "
            f"OCR {self._config.ocr.device} · "
            f"过滤{'开' if self._config.ocr.text_filter_enabled else '关'} · "
            f"合并{'开' if self._config.ocr.text_merge_enabled else '关'} · "
            f"背景 {self._background_summary(self._config.preview.overlay_opacity)} · "
            f"{self._scheduling_summary(self._config.live)}；"
            "可手动填写，读取列表不会自动保存。"
        )
        self.service_status_label.setObjectName("secondaryText")
        self.service_status_label.setWordWrap(True)
        save_service_button = QPushButton("保存运行设置")
        save_service_button.clicked.connect(
            lambda: self._save_translation_settings()
        )
        service_actions.addWidget(self.service_status_label, 1)
        service_actions.addWidget(save_service_button)
        layout.addLayout(service_actions)

        form = QFormLayout()
        self.monitor_combo = QComboBox()
        app = QApplication.instance()
        for index, screen in enumerate(app.screens() if app is not None else ()):  # type: ignore[union-attr]
            geometry = screen.geometry()
            self.monitor_combo.addItem(
                f"{index}: {screen.name()} · {geometry.width()}×{geometry.height()} "
                f"· {screen.devicePixelRatio():g}x",
                index,
            )
        self.monitor_combo.currentIndexChanged.connect(
            self._refresh_detection_quality_label
        )
        form.addRow("显示器", self.monitor_combo)
        self._refresh_detection_quality_label()

        region_widget = QWidget()
        region_layout = QHBoxLayout(region_widget)
        region_layout.setContentsMargins(0, 0, 0, 0)
        self.region_spins: list[QSpinBox] = []
        for label in ("左", "上", "宽", "高"):
            region_layout.addWidget(QLabel(label))
            spin = QSpinBox()
            spin.setRange(0, 100_000)
            spin.setAccelerated(True)
            self.region_spins.append(spin)
            region_layout.addWidget(spin, 1)
        form.addRow("字幕区域", region_widget)
        layout.addLayout(form)

        note = QLabel(
            "性能提示：宽和高都为 0 会对整个屏幕执行 OCR；GPU 通常明显快于 CPU。"
            "区域坐标相对于所选显示器，限制字幕区域仍能减少无关文字和翻译请求。"
        )
        note.setWordWrap(True)
        note.setObjectName("secondaryText")
        layout.addWidget(note)

        region_buttons = QHBoxLayout()
        select_button = QPushButton("框选字幕区域")
        full_button = QPushButton("使用整个显示器")
        save_button = QPushButton("保存区域")
        select_button.clicked.connect(self._select_region)
        full_button.clicked.connect(self._use_full_screen)
        save_button.clicked.connect(self._save_capture_settings)
        region_buttons.addWidget(select_button)
        region_buttons.addWidget(full_button)
        region_buttons.addStretch(1)
        region_buttons.addWidget(save_button)
        layout.addLayout(region_buttons)

        self.debug_checkbox = QCheckBox("显示 OCR/翻译区域调试边框")
        layout.addWidget(self.debug_checkbox)
        layout.addStretch(1)
        self.start_button = QPushButton("启动实时翻译")
        self.start_button.setObjectName("startButton")
        self.start_button.setMinimumHeight(48)
        self.start_button.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.start_button.clicked.connect(self._start_live)
        layout.addWidget(self.start_button)
        return widget

    def _start_ocr_device_probe(self) -> None:
        process = self._ocr_device_probe_process
        if process is not None and process.poll() is None:
            return
        probe = (
            "import json; "
            "from game_screen_translator.ocr.paddle import available_ocr_devices; "
            f"print({_OCR_DEVICE_PROBE_MARKER!r} + "
            "json.dumps(available_ocr_devices(), ensure_ascii=False))"
        )
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONUTF8"] = "1"
        try:
            self._ocr_device_probe_process = subprocess.Popen(
                (sys.executable, "-P", "-c", probe),
                cwd=self._config_path.parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            self._set_ocr_device_choices(
                (("cpu", "CPU"),),
                error=f"无法启动硬件检测：{exc}",
            )
            return
        self._ocr_device_probe_started_at = time.monotonic()
        self._ocr_device_probe_monitor.start()

    def _check_ocr_device_probe(self) -> None:
        process = self._ocr_device_probe_process
        if process is None:
            self._ocr_device_probe_monitor.stop()
            return
        started_at = self._ocr_device_probe_started_at
        if process.poll() is None:
            if (
                started_at is None
                or time.monotonic() - started_at < _OCR_DEVICE_PROBE_TIMEOUT_SECONDS
            ):
                return
            process.terminate()
            self._ocr_device_probe_process = None
            self._ocr_device_probe_started_at = None
            self._ocr_device_probe_monitor.stop()
            self._set_ocr_device_choices(
                (("cpu", "CPU"),),
                error="硬件检测超过 20 秒，已停止",
            )
            return

        output, _stderr = process.communicate()
        return_code = process.returncode
        self._ocr_device_probe_process = None
        self._ocr_device_probe_started_at = None
        self._ocr_device_probe_monitor.stop()
        try:
            if return_code:
                detail = output.strip()
                raise RuntimeError(detail[-1200:] or f"硬件检测退出码 {return_code}")
            devices = _parse_ocr_device_probe_output(output)
        except (json.JSONDecodeError, RuntimeError, ValueError) as exc:
            self._set_ocr_device_choices(
                (("cpu", "CPU"),),
                error=str(exc),
            )
            return
        self._set_ocr_device_choices(devices)

    def _set_ocr_device_choices(
        self,
        devices: tuple[tuple[str, str], ...],
        *,
        error: str | None = None,
    ) -> None:
        current = self.ocr_device_combo.currentData()
        if not isinstance(current, str):
            current = self._config.ocr.device
        self.ocr_device_combo.blockSignals(True)
        self.ocr_device_combo.clear()
        for device, label in devices:
            self.ocr_device_combo.addItem(label, device)

        selected_index = self.ocr_device_combo.findData(current)
        unavailable = selected_index < 0
        if unavailable:
            self.ocr_device_combo.addItem(f"{current}（当前不可用）", current)
            selected_index = self.ocr_device_combo.count() - 1
            item_getter = getattr(self.ocr_device_combo.model(), "item", None)
            if callable(item_getter):
                item = item_getter(selected_index)
                if item is not None:
                    item.setEnabled(False)
        self.ocr_device_combo.setCurrentIndex(selected_index)
        self.ocr_device_combo.blockSignals(False)

        if error:
            self.ocr_device_combo.setToolTip(
                f"OCR 硬件检测失败：{error}\n"
                "当前保留 CPU 与原配置；启动实时翻译时会再次隔离校验。"
            )
        else:
            self.ocr_device_combo.setToolTip(
                "仅列出当前隔离环境中 Paddle 实际可用的 CPU 与 NVIDIA GPU；"
                "启动实时翻译时仍会再次隔离校验。"
            )
        if unavailable:
            self.statusBar().showMessage(
                f"当前配置的 OCR 设备 {current} 未被 Paddle 检测到，请选择可用硬件",
                10000,
            )

    def _translation_candidate(self, *, require_model: bool = True):
        base_url = self.server_url_combo.currentText().strip()
        model = self.model_combo.currentText().strip()
        if not model and not require_model:
            model = self._config.translation.model
        return replace(
            self._config.translation,
            base_url=base_url,
            model=model,
            max_concurrency=self.max_concurrency_spin.value(),
        )

    def _ocr_candidate(self):
        device = self.ocr_device_combo.currentData()
        if not isinstance(device, str):
            raise ConfigError("当前没有可用的 OCR 设备")
        return replace(
            self._config.ocr,
            device=device,
            detection_max_side=self._selected_detection_max_side(),
            text_filter_enabled=self.ocr_filter_checkbox.isChecked(),
            text_merge_enabled=(
                self._text_merge_allowed()
                and self.ocr_merge_checkbox.isChecked()
            ),
        )

    def _selected_display_long_side(self) -> int:
        app = QApplication.instance()
        screens = app.screens() if app is not None else []
        monitor_index = self.monitor_combo.currentData()
        if isinstance(monitor_index, int) and 0 <= monitor_index < len(screens):
            screen = screens[monitor_index]
            geometry = screen.geometry()
            pixel_ratio = max(1.0, float(screen.devicePixelRatio()))
            return max(
                1,
                round(max(geometry.width(), geometry.height()) * pixel_ratio),
            )
        return max(_DETECTION_MIN_SIDE, self._config.ocr.detection_max_side * 2)

    def _selected_detection_max_side(self) -> int:
        scale = self._selected_detection_quality_scale()
        return _detection_max_side_for_display(
            self._selected_display_long_side(),
            scale,
        )

    def _selected_detection_quality_scale(self) -> float:
        _label, scale = _DETECTION_QUALITY_PRESETS[
            self.detection_quality_slider.value()
        ]
        return scale

    def _text_merge_allowed(self) -> bool:
        return (
            self._selected_detection_quality_scale()
            >= _TEXT_MERGE_MIN_DETECTION_SCALE
        )

    def _detection_quality_summary(self) -> str:
        label, scale = _DETECTION_QUALITY_PRESETS[
            self.detection_quality_slider.value()
        ]
        return (
            f"{label} {scale * 100:g}% · "
            f"{self._selected_detection_max_side()}px"
        )

    def _refresh_detection_quality_label(self, *args) -> None:
        self.detection_quality_label.setText(self._detection_quality_summary())

    def _detection_quality_changed(self, *args) -> None:
        self._refresh_detection_quality_label()
        self._sync_ocr_merge_availability()

    def _sync_ocr_merge_availability(self) -> None:
        allowed = self._text_merge_allowed()
        if not allowed:
            self.ocr_merge_checkbox.setChecked(False)
        self.ocr_merge_checkbox.setEnabled(allowed)

    def _restore_detection_quality_from_config(self) -> None:
        configured = self._config.ocr.detection_max_side
        long_side = self._selected_display_long_side()
        position = min(
            range(len(_DETECTION_QUALITY_PRESETS)),
            key=lambda index: (
                abs(
                    _detection_max_side_for_display(
                        long_side,
                        _DETECTION_QUALITY_PRESETS[index][1],
                    )
                    - configured
                ),
                -index,
            ),
        )
        self.detection_quality_slider.setValue(position)
        self._detection_quality_changed()

    def _live_candidate(self):
        return replace(
            self._config.live,
            settle_rescan_ms=self.settle_rescan_spin.value(),
            idle_rescan_ms=self.idle_rescan_spin.value(),
            ocr_cooldown_ms=self.ocr_cooldown_spin.value(),
            clear_after_ms=self.clear_after_spin.value(),
            dynamic_roi_enabled=self.dynamic_roi_checkbox.isChecked(),
            change_poll_fps=self.change_poll_spin.value(),
            dynamic_roi_settle_ms=self.roi_settle_spin.value(),
            dynamic_roi_ocr_interval_ms=self.roi_ocr_interval_spin.value(),
            dynamic_roi_max_coalesce_ms=self.roi_max_coalesce_spin.value(),
        )

    def _preview_overlay_opacity_candidate(self) -> float:
        mode = self.blur_mode_combo.currentData()
        if mode == _BLUR_MODE_DARK:
            return DEFAULT_DARK_OVERLAY_OPACITY
        if mode == _BLUR_MODE_ONLY:
            return 0.0
        raise ConfigError("当前译文背景模式无效")

    def _sync_ocr_scheduling_controls(self, dynamic_roi_enabled: bool) -> None:
        for control in (
            self.settle_rescan_spin,
            self.idle_rescan_spin,
            self.ocr_cooldown_spin,
        ):
            self._service_form.setRowVisible(control, not dynamic_roi_enabled)
        for control in (
            self.roi_settle_spin,
            self.roi_ocr_interval_spin,
            self.roi_max_coalesce_spin,
        ):
            self._service_form.setRowVisible(control, dynamic_roi_enabled)

    @staticmethod
    def _scheduling_summary(live: LiveConfig) -> str:
        if live.dynamic_roi_enabled:
            return (
                f"动态 ROI 开 · 热图 {live.change_poll_fps} Hz · "
                f"稳定 {live.dynamic_roi_settle_ms} ms · "
                f"OCR 间隔 {live.dynamic_roi_ocr_interval_ms} ms · "
                f"合并 {live.dynamic_roi_max_coalesce_ms} ms · "
                f"消失宽限 {live.clear_after_ms} ms"
            )
        return (
            f"动态 ROI 关 · 检测 {live.change_poll_fps} Hz · "
            f"补扫 {live.settle_rescan_ms} ms · "
            f"兜底 {live.idle_rescan_ms} ms · "
            f"冷却 {live.ocr_cooldown_ms} ms · "
            f"消失宽限 {live.clear_after_ms} ms"
        )

    @staticmethod
    def _background_summary(overlay_opacity: float) -> str:
        return "黑化模糊" if overlay_opacity > 0 else "仅模糊"

    def _refresh_models(self) -> None:
        if self._model_reply is not None:
            return
        try:
            translation = self._translation_candidate(require_model=False)
            url = QUrl(translation.normalized_base_url + "models")
            if not url.isValid() or not url.host():
                raise ValueError("API 服务器地址无效")
        except (ConfigError, ValueError) as exc:
            self._show_error("无法读取模型列表", exc)
            return

        request = QNetworkRequest(url)
        request.setRawHeader(b"Accept", b"application/json")
        request.setTransferTimeout(max(1000, round(translation.timeout_seconds * 1000)))
        if translation.api_key:
            request.setRawHeader(
                b"Authorization",
                f"Bearer {translation.api_key}".encode("utf-8"),
            )
        reply = self._network_manager.get(request)
        self._model_reply = reply
        self.refresh_models_button.setEnabled(False)
        self.refresh_models_button.setText("正在读取……")
        self.service_status_label.setText(f"正在连接 {url.toString()}……")
        reply.finished.connect(
            lambda current_reply=reply, requested=url.toString(): self._models_loaded(
                current_reply,
                requested,
            )
        )

    def _models_loaded(self, reply: QNetworkReply, requested_url: str) -> None:
        if reply is not self._model_reply:
            reply.deleteLater()
            return
        self._model_reply = None
        self.refresh_models_button.setEnabled(True)
        self.refresh_models_button.setText("读取模型列表")
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                status = reply.attribute(
                    QNetworkRequest.Attribute.HttpStatusCodeAttribute
                )
                prefix = f"HTTP {status}：" if status is not None else ""
                raise TranslationTransportError(prefix + reply.errorString())
            raw = bytes(reply.readAll())
            try:
                payload = json.loads(raw.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise TranslationTransportError(
                    "/v1/models 返回的不是有效 UTF-8 JSON"
                ) from exc
            models = parse_model_ids(payload)
        except TranslationTransportError as exc:
            self.service_status_label.setText(f"读取失败：{exc}")
            self.statusBar().showMessage(f"读取模型列表失败：{exc}", 10000)
            QMessageBox.warning(self, "读取模型列表失败", str(exc))
        else:
            retained = self._set_model_choices(models)
            suffix = "；当前手填模型已保留" if retained else ""
            self.service_status_label.setText(
                f"已从 {requested_url} 读取 {len(models)} 个模型{suffix}。"
            )
            self.statusBar().showMessage(f"已读取 {len(models)} 个 API 模型", 5000)
        finally:
            reply.deleteLater()

    def _set_model_choices(self, models) -> bool:
        current = self.model_combo.currentText().strip()
        unique_models = tuple(
            dict.fromkeys(
                str(model).strip()
                for model in models
                if str(model).strip()
            )
        )
        retained = bool(current and current not in unique_models)
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(unique_models)
        if retained:
            self.model_combo.insertItem(0, current)
        if current:
            self.model_combo.setCurrentText(current)
        elif unique_models:
            self.model_combo.setCurrentIndex(0)
        self.model_combo.blockSignals(False)
        return retained

    def _save_translation_settings(self, *, announce: bool = True) -> bool:
        try:
            translation = self._translation_candidate()
            ocr = self._ocr_candidate()
            live = self._live_candidate()
            preview_overlay_opacity = self._preview_overlay_opacity_candidate()
            self._config = save_runtime_selection(
                self._config_path,
                base_url=translation.base_url,
                model=translation.model,
                ocr_device=ocr.device,
                max_concurrency=translation.max_concurrency,
                ocr_detection_max_side=ocr.detection_max_side,
                ocr_text_filter_enabled=ocr.text_filter_enabled,
                ocr_text_merge_enabled=ocr.text_merge_enabled,
                preview_overlay_opacity=preview_overlay_opacity,
                settle_rescan_ms=live.settle_rescan_ms,
                idle_rescan_ms=live.idle_rescan_ms,
                ocr_cooldown_ms=live.ocr_cooldown_ms,
                clear_after_ms=live.clear_after_ms,
                dynamic_roi_enabled=live.dynamic_roi_enabled,
                change_poll_fps=live.change_poll_fps,
                dynamic_roi_settle_ms=live.dynamic_roi_settle_ms,
                dynamic_roi_ocr_interval_ms=live.dynamic_roi_ocr_interval_ms,
                dynamic_roi_max_coalesce_ms=(
                    live.dynamic_roi_max_coalesce_ms
                ),
            )
        except (ConfigError, OSError, RuntimeError, ValueError) as exc:
            self._show_error("保存运行设置失败", exc)
            return False
        self.server_url_combo.setCurrentText(self._config.translation.base_url)
        self.model_combo.setCurrentText(self._config.translation.model)
        self.max_concurrency_spin.setValue(
            self._config.translation.max_concurrency
        )
        device_index = self.ocr_device_combo.findData(self._config.ocr.device)
        if device_index >= 0:
            self.ocr_device_combo.setCurrentIndex(device_index)
        self.ocr_filter_checkbox.setChecked(self._config.ocr.text_filter_enabled)
        self.ocr_merge_checkbox.setChecked(self._config.ocr.text_merge_enabled)
        blur_mode = (
            _BLUR_MODE_DARK
            if self._config.preview.overlay_opacity > 0
            else _BLUR_MODE_ONLY
        )
        blur_mode_index = self.blur_mode_combo.findData(blur_mode)
        if blur_mode_index >= 0:
            self.blur_mode_combo.setCurrentIndex(blur_mode_index)
        self.dynamic_roi_checkbox.setChecked(
            self._config.live.dynamic_roi_enabled
        )
        self.settle_rescan_spin.setValue(self._config.live.settle_rescan_ms)
        self.idle_rescan_spin.setValue(self._config.live.idle_rescan_ms)
        self.ocr_cooldown_spin.setValue(self._config.live.ocr_cooldown_ms)
        self.clear_after_spin.setValue(self._config.live.clear_after_ms)
        self.change_poll_spin.setValue(self._config.live.change_poll_fps)
        self.roi_settle_spin.setValue(
            self._config.live.dynamic_roi_settle_ms
        )
        self.roi_ocr_interval_spin.setValue(
            self._config.live.dynamic_roi_ocr_interval_ms
        )
        self.roi_max_coalesce_spin.setValue(
            self._config.live.dynamic_roi_max_coalesce_ms
        )
        self.service_status_label.setText(
            f"当前：{self._config.translation.model} · "
            f"{self._config.translation.normalized_base_url} · "
            f"并发 {self._config.translation.max_concurrency} · "
            f"OCR {self._config.ocr.device} · "
            f"过滤{'开' if self._config.ocr.text_filter_enabled else '关'} · "
            f"合并{'开' if self._config.ocr.text_merge_enabled else '关'} · "
            f"背景 {self._background_summary(self._config.preview.overlay_opacity)} · "
            f"{self._scheduling_summary(self._config.live)}"
        )
        if announce:
            self.statusBar().showMessage(
                "运行设置已保存；新启动的实时翻译将使用该设置",
                6000,
            )
        return True

    def _build_info_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        refresh_button = QPushButton("刷新统计")
        refresh_button.clicked.connect(self._reload_current_profile)
        layout.addWidget(self.info_label)
        layout.addStretch(1)
        layout.addWidget(refresh_button)
        return widget

    def refresh_profiles(self, select_profile_id: str | None = None) -> None:
        current_id = select_profile_id
        if current_id is None and self.profile_combo.currentIndex() >= 0:
            current_id = self.profile_combo.currentData()
        try:
            profiles = list_game_profiles(self._config_path, self._config)
        except (ProfileError, RuntimeError, ValueError) as exc:
            self._show_error("无法读取 Profile", exc)
            return

        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        selected_index = 0
        for index, profile in enumerate(profiles):
            self.profile_combo.addItem(
                f"{profile.display_name} ({profile.profile_id})",
                profile.profile_id,
            )
            if profile.profile_id == current_id:
                selected_index = index
        if profiles:
            self.profile_combo.setCurrentIndex(selected_index)
            self.profile_combo.blockSignals(False)
            self._load_selected_profile()
        else:
            self.profile_combo.blockSignals(False)
            self._profile = None
            self._set_profile_enabled(False)
            self._glossary_editor.set_pairs(())
            self._correction_editor.set_pairs(())
            self.info_label.setText(
                "尚未创建游戏 Profile。点击窗口上方的“新建 Profile”开始。"
            )
            self.statusBar().showMessage("请先新建一个游戏 Profile")

    def _set_profile_enabled(self, enabled: bool) -> None:
        for index in range(self.tabs.count()):
            self.tabs.setTabEnabled(index, enabled)

    def _create_profile(self) -> None:
        dialog = NewProfileDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            profile = create_game_profile(
                self._config_path,
                self._config,
                dialog.profile_id,
                display_name=dialog.display_name,
            )
        except (ProfileError, OSError, RuntimeError, ValueError) as exc:
            self._show_error("新建 Profile 失败", exc)
            return
        self.refresh_profiles(profile.profile_id)
        self.statusBar().showMessage(f"已创建 {profile.display_name}", 5000)

    def _load_selected_profile(self, *args) -> None:
        profile_id = self.profile_combo.currentData()
        if not isinstance(profile_id, str):
            return
        try:
            profile = load_game_profile(self._config_path, self._config, profile_id)
            corrections = profile.cache.list_manual_corrections(
                source_language=self._config.ocr.language,
                target_language=self._config.translation.target_language,
            )
        except (ProfileError, RuntimeError, ValueError) as exc:
            self._show_error("加载 Profile 失败", exc)
            return
        self._profile = profile
        self._set_profile_enabled(True)
        capture = profile.capture_settings
        monitor_index = (
            capture.monitor_index
            if capture.monitor_index is not None
            else self._config.live.monitor_index
        )
        if 0 <= monitor_index < self.monitor_combo.count():
            self.monitor_combo.setCurrentIndex(monitor_index)
        else:
            self.monitor_combo.setCurrentIndex(0)
            self.statusBar().showMessage(
                f"Profile 中的显示器 {monitor_index} 当前不存在，已临时选择显示器 0",
                8000,
            )
        region = capture.region or (
            self._config.live.left,
            self._config.live.top,
            self._config.live.width,
            self._config.live.height,
        )
        for spin, value in zip(self.region_spins, region):
            spin.setValue(value)
        self._glossary_editor.set_pairs(
            (entry.source, entry.target) for entry in profile.glossary
        )
        self._correction_editor.set_pairs(
            (entry.source_text, entry.translated_text) for entry in corrections
        )
        self._update_info()
        self.statusBar().showMessage(f"已加载 {profile.display_name}", 3000)

    def _reload_current_profile(self) -> None:
        if self._profile is not None:
            self.refresh_profiles(self._profile.profile_id)

    def _save_glossary(self) -> None:
        profile = self._require_profile()
        if profile is None:
            return
        try:
            entries = tuple(
                GlossaryEntry(source, target)
                for source, target in self._glossary_editor.pairs()
            )
            save_profile_glossary(profile, entries)
        except (ProfileError, OSError, RuntimeError, ValueError) as exc:
            self._show_error("保存术语表失败", exc)
            return
        self.refresh_profiles(profile.profile_id)
        self.statusBar().showMessage(
            f"术语表已保存，共 {len(entries)} 条；下次启动实时翻译时使用新版本",
            6000,
        )

    def _save_corrections(self) -> None:
        profile = self._require_profile()
        if profile is None:
            return
        try:
            corrections = self._correction_editor.pairs()
            profile.cache.replace_manual_corrections(
                corrections,
                source_language=self._config.ocr.language,
                target_language=self._config.translation.target_language,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_error("保存人工修订失败", exc)
            return
        self.refresh_profiles(profile.profile_id)
        self.statusBar().showMessage(
            f"人工修订已保存，共 {len(corrections)} 条",
            6000,
        )

    def _current_region(self) -> tuple[int, int, int, int]:
        return tuple(spin.value() for spin in self.region_spins)  # type: ignore[return-value]

    def _save_capture_settings(self) -> bool:
        profile = self._require_profile()
        if profile is None:
            return False
        monitor_index = self.monitor_combo.currentData()
        if not isinstance(monitor_index, int):
            self._show_error("保存区域失败", ValueError("当前没有可用显示器"))
            return False
        try:
            settings = ProfileCaptureSettings(
                monitor_index=monitor_index,
                region=self._current_region(),
            )
            save_profile_capture_settings(profile, settings)
            self._profile = load_game_profile(
                self._config_path,
                self._config,
                profile.profile_id,
            )
        except (ProfileError, OSError, RuntimeError, ValueError) as exc:
            self._show_error("保存区域失败", exc)
            return False
        self._update_info()
        self.statusBar().showMessage(
            f"区域已保存到 {profile.display_name}：{','.join(map(str, settings.region or ())) }",
            6000,
        )
        return True

    def _select_region(self) -> None:
        profile = self._require_profile()
        if profile is None:
            return
        monitor_index = self.monitor_combo.currentData()
        app = QApplication.instance()
        screens = app.screens() if app is not None else []
        if not isinstance(monitor_index, int) or monitor_index >= len(screens):
            self._show_error("无法框选区域", ValueError("当前显示器不可用"))
            return

        self.hide()
        QApplication.processEvents()
        selector = RegionSelector(screens[monitor_index])
        accepted = selector.exec() == QDialog.DialogCode.Accepted
        self.show()
        self.raise_()
        self.activateWindow()
        if not accepted or selector.selected_region is None:
            self.statusBar().showMessage("已取消框选", 3000)
            return
        for spin, value in zip(self.region_spins, selector.selected_region):
            spin.setValue(value)
        self._save_capture_settings()

    def _use_full_screen(self) -> None:
        for spin in self.region_spins:
            spin.setValue(0)
        self._save_capture_settings()

    def _start_live(self) -> None:
        profile = self._require_profile()
        if profile is None:
            return
        if self._live_process is not None and self._live_process.poll() is None:
            self._show_error("实时翻译已在运行", RuntimeError("请先关闭现有翻译进程"))
            return
        try:
            selected_device = self._ocr_candidate().device
            self.statusBar().showMessage(f"正在检查 OCR 设备 {selected_device}……")
            QApplication.processEvents()
            runtime_description = _validate_ocr_device_isolated(selected_device)
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_error("OCR 设备不可用", exc)
            return
        if not self._save_translation_settings(announce=False):
            return
        if not self._save_capture_settings():
            return
        arguments = [
            "-m",
            "game_screen_translator",
            "--config",
            str(self._config_path),
            "live",
            "--profile",
            profile.profile_id,
        ]
        if self.debug_checkbox.isChecked():
            arguments.append("--debug-border")
        try:
            self._live_log_path.parent.mkdir(parents=True, exist_ok=True)
            environment = os.environ.copy()
            environment.update(
                PYTHONFAULTHANDLER="1",
                PYTHONUNBUFFERED="1",
                PYTHONUTF8="1",
            )
            creation_flags = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            with self._live_log_path.open("w", encoding="utf-8") as log_file:
                log_file.write(f"{PRODUCT_NAME} live diagnostics\n")
                log_file.flush()
                process = subprocess.Popen(
                    [sys.executable, *arguments],
                    cwd=self._config_path.parent,
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    env=environment,
                    creationflags=creation_flags,
                    close_fds=True,
                )
        except OSError as exc:
            self._show_error("启动失败", exc)
            return
        self._live_process = process
        self._live_monitor.start()
        # The launcher itself does not use SetWindowDisplayAffinity: that API
        # can block in some Windows graphics/remote-session configurations.
        # Minimize after the child is created so it does not enter OCR.
        self.showMinimized()
        self.statusBar().showMessage(
            f"实时翻译正在启动（进程 {process.pid}，{runtime_description}）；"
            f"诊断日志：{self._live_log_path}",
            10000,
        )

    def _check_live_process(self) -> None:
        process = self._live_process
        if process is None:
            self._live_monitor.stop()
            return
        exit_code = process.poll()
        if exit_code is None:
            return
        self._live_monitor.stop()
        self._live_process = None
        if exit_code == 0:
            self.statusBar().showMessage("实时翻译已关闭", 5000)
            return
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._show_error(
            "实时翻译进程异常退出",
            RuntimeError(
                f"退出码：{exit_code}\n"
                f"日志：{self._live_log_path}\n\n"
                f"{_log_tail(self._live_log_path)}"
            ),
        )

    def _update_info(self) -> None:
        profile = self._profile
        if profile is None:
            return
        stats = profile.cache.stats()
        capture = profile.capture_settings
        region = (
            ",".join(str(value) for value in capture.region)
            if capture.region is not None
            else "未单独设置（使用 config.toml）"
        )
        monitor = (
            str(capture.monitor_index)
            if capture.monitor_index is not None
            else "未单独设置（使用 config.toml）"
        )
        self.info_label.setText(
            f"Profile：{profile.display_name} ({profile.profile_id})\n\n"
            f"目录：{profile.directory}\n"
            f"显示器：{monitor}\n"
            f"字幕区域：{region}\n\n"
            f"术语：{len(profile.glossary)} 条\n"
            f"模型缓存：{stats.automatic_entries} 条，命中 {stats.automatic_hits} 次\n"
            f"人工修订：{stats.manual_corrections} 条，命中 {stats.manual_hits} 次"
        )

    def _require_profile(self) -> GameProfile | None:
        if self._profile is None:
            self._show_error("尚未选择游戏", ValueError("请先新建或选择一个 Profile"))
        return self._profile

    def _show_error(self, title: str, error: Exception) -> None:
        self.statusBar().showMessage(f"{title}：{error}", 10000)
        QMessageBox.critical(self, title, str(error))


def run_launcher(
    config_path: Path,
    *,
    duration_seconds: float | None = None,
) -> int:
    if duration_seconds is not None and duration_seconds <= 0:
        raise ValueError("--duration 必须大于 0")
    _startup_message("creating QApplication")
    app = QApplication.instance() or QApplication([GUI_PROCESS_NAME])
    app.setApplicationName(PRODUCT_NAME)
    app.setApplicationDisplayName(PRODUCT_NAME)
    _startup_message(f"Qt platform: {app.platformName()}")
    _startup_message("building launcher window")
    window = LauncherWindow(config_path)
    screen = app.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        window.move(
            max(available.left(), available.left() + (available.width() - window.width()) // 2),
            max(available.top(), available.top() + (available.height() - window.height()) // 2),
        )
    _startup_message("showing launcher window")
    window.show()

    def announce_ready() -> None:
        if app.platformName() == "windows":
            window.raise_()
            window.activateWindow()
        geometry = window.geometry()
        _startup_message(
            "event loop ready; "
            f"visible={window.isVisible()} geometry="
            f"{geometry.x()},{geometry.y()},{geometry.width()},{geometry.height()}"
        )

    QTimer.singleShot(0, announce_ready)
    if duration_seconds is not None:
        QTimer.singleShot(round(duration_seconds * 1000), app.quit)
    exit_code = app.exec()
    _startup_message(f"event loop exited with code {exit_code}")
    return exit_code

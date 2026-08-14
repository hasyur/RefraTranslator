from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from game_screen_translator.branding import GUI_PROCESS_NAME, PRODUCT_NAME
from game_screen_translator.config import (
    AppConfig,
    ConfigError,
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


try:
    from PySide6.QtCore import QProcess, QTimer, Qt, QUrl
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
    def __init__(self, config_path: Path) -> None:
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

    def _build_launch_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        service_form = QFormLayout()
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
        for index in range(8):
            self.ocr_device_combo.addItem(f"GPU {index}", f"gpu:{index}")
        configured_device = self._config.ocr.device
        device_index = self.ocr_device_combo.findData(configured_device)
        if device_index < 0:
            self.ocr_device_combo.addItem(
                f"{configured_device}（当前未检测到）",
                configured_device,
            )
            device_index = self.ocr_device_combo.count() - 1
        self.ocr_device_combo.setCurrentIndex(device_index)
        self.ocr_device_combo.setToolTip(
            "GPU 编号会在启动实时翻译时通过 Paddle 隔离校验；"
            "GPU OCR 需要通过 bootstrap.ps1 -WithGpuOcr 安装项目内运行库"
        )
        service_form.addRow("OCR 设备", self.ocr_device_combo)

        self.ocr_filter_checkbox = QCheckBox("启用文字过滤")
        self.ocr_filter_checkbox.setChecked(self._config.ocr.text_filter_enabled)
        self.ocr_filter_checkbox.setToolTip(
            "关闭后，图标、数字、中文和其他非源语言 OCR 文本也会进入跟踪与翻译；"
            "OCR 置信度阈值仍然有效。"
        )
        service_form.addRow("OCR 过滤", self.ocr_filter_checkbox)

        self.settle_rescan_spin = QSpinBox()
        self.settle_rescan_spin.setRange(0, 60_000)
        self.settle_rescan_spin.setValue(self._config.live.settle_rescan_ms)
        self.settle_rescan_spin.setSingleStep(50)
        self.settle_rescan_spin.setAccelerated(True)
        self.settle_rescan_spin.setSuffix(" ms")
        self.settle_rescan_spin.setSpecialValueText("关闭")
        self.settle_rescan_spin.setToolTip(
            "最后一次检测到画面变化后，等待这段时间自动补扫一次；"
            "用于补全字幕绘制中途的首轮 OCR，0 表示关闭。"
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
            "画面没有再次触发变化检测时，按此间隔兜底执行 OCR；"
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
            "增大可降低连续变化时的负载，但可能增加延迟或漏掉短字幕。"
        )
        service_form.addRow("OCR 冷却", self.ocr_cooldown_spin)
        layout.addLayout(service_form)

        service_actions = QHBoxLayout()
        self.service_status_label = QLabel(
            f"当前：{self._config.translation.model} · "
            f"{self._config.translation.normalized_base_url} · "
            f"并发 {self._config.translation.max_concurrency} · "
            f"OCR {self._config.ocr.device} · "
            f"过滤{'开' if self._config.ocr.text_filter_enabled else '关'} · "
            f"补扫 {self._config.live.settle_rescan_ms} ms · "
            f"兜底 {self._config.live.idle_rescan_ms} ms · "
            f"冷却 {self._config.live.ocr_cooldown_ms} ms；"
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
        form.addRow("显示器", self.monitor_combo)

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
            text_filter_enabled=self.ocr_filter_checkbox.isChecked(),
        )

    def _live_candidate(self):
        return replace(
            self._config.live,
            settle_rescan_ms=self.settle_rescan_spin.value(),
            idle_rescan_ms=self.idle_rescan_spin.value(),
            ocr_cooldown_ms=self.ocr_cooldown_spin.value(),
        )

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
            self._config = save_runtime_selection(
                self._config_path,
                base_url=translation.base_url,
                model=translation.model,
                ocr_device=ocr.device,
                max_concurrency=translation.max_concurrency,
                ocr_text_filter_enabled=ocr.text_filter_enabled,
                settle_rescan_ms=live.settle_rescan_ms,
                idle_rescan_ms=live.idle_rescan_ms,
                ocr_cooldown_ms=live.ocr_cooldown_ms,
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
        self.settle_rescan_spin.setValue(self._config.live.settle_rescan_ms)
        self.idle_rescan_spin.setValue(self._config.live.idle_rescan_ms)
        self.ocr_cooldown_spin.setValue(self._config.live.ocr_cooldown_ms)
        self.service_status_label.setText(
            f"当前：{self._config.translation.model} · "
            f"{self._config.translation.normalized_base_url} · "
            f"并发 {self._config.translation.max_concurrency} · "
            f"OCR {self._config.ocr.device} · "
            f"过滤{'开' if self._config.ocr.text_filter_enabled else '关'} · "
            f"补扫 {self._config.live.settle_rescan_ms} ms · "
            f"兜底 {self._config.live.idle_rescan_ms} ms · "
            f"冷却 {self._config.live.ocr_cooldown_ms} ms"
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
        # The launcher itself does not use SetWindowDisplayAffinity: that API
        # can block in some Windows graphics/remote-session configurations.
        # Minimize before the live process starts so it does not enter OCR.
        self.showMinimized()
        QApplication.processEvents()
        started, process_id = QProcess.startDetached(
            sys.executable,
            arguments,
            str(self._config_path.parent),
        )
        if not started:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self._show_error("启动失败", RuntimeError("无法创建实时翻译进程"))
            return
        self.statusBar().showMessage(
            f"实时翻译已启动（进程 {process_id}，{runtime_description}）；"
            "可在右上角控制窗停止",
            10000,
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
    return app.exec()

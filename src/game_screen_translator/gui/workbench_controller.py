from __future__ import annotations

import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    Property,
    QTimer,
    QUrl,
    QObject,
    Signal,
    Slot,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QApplication

from game_screen_translator.branding import (
    API_KEY_ENV,
    LEGACY_API_KEY_ENV,
    PRODUCT_NAME,
)
from game_screen_translator.config import (
    AppConfig,
    BUILTIN_CONTEXT_PER_SLOT,
    BUILTIN_CUDA_DEVICE_FOLLOW_OCR,
    BUILTIN_KV_CACHE_TYPES,
    BUILTIN_MAX_OUTPUT_TOKENS,
    BUILTIN_PARALLEL_MAX,
    CAPTURE_FPS_PER_CHANGE_POLL,
    ConfigError,
    DEFAULT_DARK_OVERLAY_OPACITY,
    MAX_CHANGE_POLL_FPS,
    load_config,
    save_runtime_selection,
)
from game_screen_translator.domain import GlossaryEntry
from game_screen_translator.profiles import (
    GameProfile,
    ProfileCaptureSettings,
    ProfileError,
    create_named_game_profile,
    list_game_profiles,
    load_game_profile,
    save_profile_capture_settings,
    save_profile_custom_prompt,
    save_profile_glossary,
)
from game_screen_translator.translation.local_backend import (
    BUILTIN_MODELS,
    LLAMA_CPP_STABLE_VERSION,
    LLAMA_CPP_VERSION,
    LocalBackendDownloadCancelled,
    LocalBackendError,
    get_builtin_model,
    install_local_backend,
    local_backend_is_ready,
    local_backend_root,
    model_is_ready,
    model_path,
    remove_builtin_model,
    runtime_is_ready,
)
from game_screen_translator.translation.transport import (
    TranslationTransportError,
    parse_model_ids,
)
from game_screen_translator.live.snapshot import LastRunSnapshot, load_snapshot

from .theme import (
    GuiPreferences,
    GuiSettingsError,
    THEME_DARK,
    THEME_OPTIONS,
    effective_theme,
    load_gui_preferences,
    save_gui_preferences,
)


_BLUR_MODE_DARK = "dark_blur"
_BLUR_MODE_ONLY = "blur_only"
_DETECTION_QUALITY_PRESETS = (
    ("性能", 0.375),
    ("平衡", 0.5),
    ("质量", 0.75),
)
_DETECTION_MIN_SIDE = 640
_DETECTION_MAX_SIDE = 4096
_DETECTION_ALIGNMENT = 32
_TEXT_MERGE_MIN_DETECTION_SCALE = 0.5
_OCR_DEVICE_PROBE_MARKER = "REFRA_OCR_DEVICES="
_OCR_DEVICE_PROBE_TIMEOUT_SECONDS = 20.0
_LIVE_STOP_GRACE_SECONDS = 5.0
_WM_CLOSE = 0x0010


def _request_live_graceful_shutdown(process: subprocess.Popen) -> bool:
    """Ask the native live control window to close, without an IPC channel."""

    if os.name != "nt":
        return False
    try:
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        enum_windows = user32.EnumWindows
        enum_windows.argtypes = (
            ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM),
            wintypes.LPARAM,
        )
        enum_windows.restype = wintypes.BOOL
        get_window_pid = user32.GetWindowThreadProcessId
        get_window_pid.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        get_window_pid.restype = wintypes.DWORD
        get_window_text_length = user32.GetWindowTextLengthW
        get_window_text_length.argtypes = (wintypes.HWND,)
        get_window_text_length.restype = ctypes.c_int
        get_window_text = user32.GetWindowTextW
        get_window_text.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        get_window_text.restype = ctypes.c_int
        post_message = user32.PostMessageW
        post_message.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        post_message.restype = wintypes.BOOL
        target_pid = int(process.pid)
        found = False

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _lparam):
            nonlocal found
            owner_pid = wintypes.DWORD()
            get_window_pid(hwnd, ctypes.byref(owner_pid))
            if int(owner_pid.value) != target_pid:
                return True
            title_length = get_window_text_length(hwnd)
            if title_length <= 0:
                return True
            title_buffer = ctypes.create_unicode_buffer(title_length + 1)
            get_window_text(hwnd, title_buffer, title_length + 1)
            # The live process can own overlay/test-source windows as well.
            # Only the exact native control-window title is a valid target.
            if title_buffer.value != PRODUCT_NAME:
                return True
            if post_message(hwnd, _WM_CLOSE, 0, 0):
                found = True
                return False
            return True

        enum_windows(visit, 0)
        return found
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _detection_max_side_for_display(display_long_side: int, scale: float) -> int:
    target = max(
        _DETECTION_MIN_SIDE,
        min(_DETECTION_MAX_SIDE, display_long_side * scale),
    )
    return int((target + _DETECTION_ALIGNMENT / 2) // _DETECTION_ALIGNMENT) * _DETECTION_ALIGNMENT


def _log_tail(path: Path, *, max_characters: int = 4000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        return f"无法读取日志：{exc}"
    return text[-max_characters:] if text else "日志尚无输出。"


def _validate_ocr_device_isolated(device: str) -> str:
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
        if not (device.startswith("gpu:") and device[4:].isdigit()):
            raise RuntimeError(f"OCR 硬件检测返回了未知设备：{device}")
        if label.strip() and device not in seen:
            devices.append((device, label.strip()))
            seen.add(device)
    return tuple(devices)


class WorkbenchController(QObject):
    """Native workbench controller for the existing launcher services and state.

    The controller owns no replacement OCR, translation, cache, or live state
    machine. It only keeps the same editable GUI draft values that the former
    QWidget launcher kept before saving them through the existing services.
    """

    stateChanged = Signal()
    profilesChanged = Signal()
    errorRaised = Signal(str, str)
    noticeRaised = Signal(str)
    regionSelectionRequested = Signal(int)
    liveReady = Signal()
    liveFinished = Signal()
    liveFailed = Signal()

    def __init__(self, config_path: Path, *, probe_ocr_devices: bool = True) -> None:
        super().__init__()
        self._config_path = config_path.resolve()
        self._config: AppConfig = load_config(self._config_path)
        self._current_page = "HOME"
        try:
            preferences = load_gui_preferences(self._config_path)
            self._preferences_warning: str | None = None
        except (GuiSettingsError, OSError) as exc:
            preferences = GuiPreferences()
            self._preferences_warning = str(exc)

        self._theme_preference = preferences.theme
        app = QApplication.instance()
        self._effective_theme = effective_theme(self._theme_preference, app) if app else THEME_DARK
        self._reduced_motion = os.environ.get("REFRA_TRANSLATOR_REDUCED_MOTION") == "1"
        self._profile: GameProfile | None = None
        self._profiles: tuple[GameProfile, ...] = ()
        self._current_profile_index = -1
        self._profile_revision = 0
        self._last_run_snapshot: LastRunSnapshot | None = None
        self._status_text = "正在读取配置……"
        self._status_tone = "neutral"
        self._run_state = "待启动"
        self._run_tone = "neutral"
        self._live_process: subprocess.Popen | None = None
        self._live_waiting_for_ready = False
        self._live_stop_requested = False
        self._live_stop_started_at: float | None = None
        self._live_force_stop_available = False
        self._live_force_stop_requested = False
        self._live_log_path = self._config_path.parent / "output" / "live.log"
        self._debug_enabled = False
        self._runtime_dirty = False
        self._prompt_dirty = False
        self._capture_dirty = False

        self._network_manager = QNetworkAccessManager(self)
        self._model_reply: QNetworkReply | None = None
        self._model_ids = [self._config.translation.model]
        self._connection_state = "未测试"

        self._local_install_thread: threading.Thread | None = None
        self._local_install_cancel = threading.Event()
        self._local_install_events: queue.SimpleQueue[tuple[Any, ...]] = queue.SimpleQueue()
        self._download_progress = 0
        self._download_label = ""

        self._ocr_device_probe_process: subprocess.Popen | None = None
        self._ocr_device_probe_started_at: float | None = None
        self._ocr_device_values: list[str] = []
        self._ocr_device_names: list[str] = []
        self._available_ocr_device_values: set[str] = set()
        self._builtin_device_values: list[str] = [BUILTIN_CUDA_DEVICE_FOLLOW_OCR]
        self._builtin_device_names: list[str] = ["跟随 OCR 设备（推荐）"]
        self._available_builtin_device_values: set[str] = {
            BUILTIN_CUDA_DEVICE_FOLLOW_OCR
        }

        self._monitor_values: list[int] = []
        self._monitor_names: list[str] = []
        self._monitor_index = self._config.live.monitor_index

        self._capture_left = self._config.live.left
        self._capture_top = self._config.live.top
        self._capture_width = self._config.live.width
        self._capture_height = self._config.live.height
        self._custom_region = self._capture_width > 0 and self._capture_height > 0
        self._detection_quality_index = 1

        self._ocr_device = self._config.ocr.device
        self._ocr_filter_enabled = self._config.ocr.text_filter_enabled
        self._ocr_merge_enabled = self._config.ocr.text_merge_enabled

        self._backend = self._config.translation.backend
        self._builtin_model = self._config.translation.builtin_model
        self._builtin_cuda_device = self._config.translation.builtin_cuda_device
        self._builtin_parallel = self._config.translation.builtin_parallel
        self._builtin_kv_cache_type = self._config.translation.builtin_kv_cache_type
        self._base_url = self._config.translation.base_url
        self._api_key = self._config.translation.api_key
        self._model = self._config.translation.model
        self._max_concurrency = self._config.translation.max_concurrency
        self._custom_prompt = ""

        self._overlay_opacity = self._config.preview.overlay_opacity
        self._browser_overlay_enabled = self._config.recording.browser_overlay_enabled
        self._dynamic_roi_enabled = self._config.live.dynamic_roi_enabled
        self._change_poll_fps = self._config.live.change_poll_fps
        self._roi_response_target_ms = self._config.live.dynamic_roi_response_target_ms
        self._clear_after_ms = self._config.live.clear_after_ms
        self._settle_rescan_ms = self._config.live.settle_rescan_ms
        self._idle_rescan_ms = self._config.live.idle_rescan_ms
        self._ocr_cooldown_ms = self._config.live.ocr_cooldown_ms

        self._glossary: list[dict[str, str]] = []
        self._corrections: list[dict[str, str]] = []
        self._glossary_dirty = False
        self._corrections_dirty = False
        self._automatic_entries = 0
        self._automatic_hits = 0
        self._manual_corrections = 0
        self._manual_hits = 0

        self._live_monitor = QTimer(self)
        self._live_monitor.setInterval(500)
        self._live_monitor.timeout.connect(self._check_live_process)
        self._ocr_probe_monitor = QTimer(self)
        self._ocr_probe_monitor.setInterval(100)
        self._ocr_probe_monitor.timeout.connect(self._check_ocr_device_probe)
        self._local_install_monitor = QTimer(self)
        self._local_install_monitor.setInterval(100)
        self._local_install_monitor.timeout.connect(self._check_local_install_events)

        self._refresh_monitors()
        self._restore_detection_quality_from_config()
        self.refreshProfiles()
        if probe_ocr_devices:
            self.probeOcrDevices()
        if self._preferences_warning:
            self._set_status(
                f"GUI 设置无效，已恢复为跟随系统：{self._preferences_warning}",
                "warning",
            )

        if app is not None:
            try:
                app.styleHints().colorSchemeChanged.connect(self._system_theme_changed)
            except AttributeError:
                pass

    def _emit_state(self) -> None:
        self.stateChanged.emit()

    def _mark_runtime_dirty(self) -> None:
        self._runtime_dirty = True
        self._emit_state()

    def _mark_prompt_dirty(self) -> None:
        self._prompt_dirty = True
        self._emit_state()

    def _mark_capture_dirty(self) -> None:
        self._capture_dirty = True
        self._emit_state()

    def _set_status(self, text: str, tone: str = "neutral") -> None:
        self._status_text = text
        self._status_tone = tone
        self._emit_state()

    def _show_error(self, title: str, error: Exception | str) -> None:
        message = str(error)
        self._set_status(f"{title}：{message}", "error")
        self.errorRaised.emit(title, message)

    @Slot(str, str)
    def reportHostError(self, title: str, message: str) -> None:
        """Project a native-host failure through the same QML error boundary."""

        self._show_error(title, message)

    def _notice(self, message: str, tone: str = "success") -> None:
        self._status_text = message
        self._status_tone = tone
        self.noticeRaised.emit(message)
        self._emit_state()

    # ----- basic state exposed to QML ---------------------------------

    @Property(str, notify=stateChanged)
    def currentPage(self) -> str:
        return self._current_page

    @Property(str, notify=stateChanged)
    def statusText(self) -> str:
        return self._status_text

    @Property(str, notify=stateChanged)
    def statusTone(self) -> str:
        return self._status_tone

    @Property(str, notify=stateChanged)
    def effectiveTheme(self) -> str:
        return self._effective_theme

    @Property(str, notify=stateChanged)
    def themePreference(self) -> str:
        return self._theme_preference

    @Property(list, notify=stateChanged)
    def themeOptions(self) -> list[str]:
        return [value for value, _label in THEME_OPTIONS]

    @Property(bool, notify=stateChanged)
    def reducedMotion(self) -> bool:
        return self._reduced_motion

    @Property(str, notify=stateChanged)
    def runState(self) -> str:
        return self._run_state

    @Property(str, notify=stateChanged)
    def runTone(self) -> str:
        return self._run_tone

    @Property(bool, notify=stateChanged)
    def running(self) -> bool:
        return self._live_process is not None and self._live_process.poll() is None

    @Property(str, notify=stateChanged)
    def startButtonText(self) -> str:
        if self._live_stop_requested:
            if self._live_force_stop_requested:
                return "正在强制停止…"
            if self._live_force_stop_available:
                return "强制停止"
            return "正在保存并停止…"
        return "停止翻译" if self.running else "开始翻译"

    @Property(bool, notify=stateChanged)
    def canStart(self) -> bool:
        return self._profile is not None and not self._live_stop_requested

    @Property(str, notify=stateChanged)
    def runPhase(self) -> str:
        if self._live_stop_requested:
            return "stopping"
        if self.running:
            return "starting" if self._live_waiting_for_ready else "running"
        if self._run_tone == "error":
            return "failed"
        return "stopped"

    @Property(bool, notify=stateChanged)
    def settingsDirty(self) -> bool:
        return self._runtime_dirty or self._prompt_dirty or self._capture_dirty

    @Property(bool, constant=True)
    def telemetryAvailable(self) -> bool:
        return False

    @Property(str, constant=True)
    def telemetryUnavailableText(self) -> str:
        return "当前实时进程未向设置工作台提供结构化遥测。"

    @Property(list, notify=profilesChanged)
    def profileNames(self) -> list[str]:
        return [profile.display_name for profile in self._profiles]

    @Property(list, notify=profilesChanged)
    def profileIds(self) -> list[str]:
        return [profile.profile_id for profile in self._profiles]

    @Property(int, notify=profilesChanged)
    def currentProfileIndex(self) -> int:
        return self._current_profile_index

    @Property(str, notify=stateChanged)
    def currentProfileName(self) -> str:
        return self._profile.display_name if self._profile else "尚未创建配置"

    @Property(str, notify=stateChanged)
    def currentProfileId(self) -> str:
        return self._profile.profile_id if self._profile else ""

    @Property(bool, notify=stateChanged)
    def hasProfile(self) -> bool:
        return self._profile is not None

    @Property(bool, notify=stateChanged)
    def lastRunAvailable(self) -> bool:
        return self._last_run_snapshot is not None

    @Property(str, notify=stateChanged)
    def lastRunStatus(self) -> str:
        if self._profile is None:
            return "请先选择一个 Profile"
        if self._last_run_snapshot is None:
            return "尚无上次正常且有效运行结果"
        return f"上次运行：{self._last_run_snapshot.created_at}"

    @Property(list, notify=stateChanged)
    def lastRunOcrResults(self) -> list[dict[str, object]]:
        return self._snapshot_entries()

    @Property(list, notify=stateChanged)
    def lastRunTranslationResults(self) -> list[dict[str, object]]:
        return self._snapshot_entries()

    @Property(list, notify=stateChanged)
    def lastRunOverlayResults(self) -> list[dict[str, object]]:
        return self._snapshot_entries()

    @Property(list, notify=stateChanged)
    def lastRunCacheHits(self) -> list[dict[str, object]]:
        snapshot = self._last_run_snapshot
        if snapshot is None:
            return []
        return [
            {"sourceText": item.source_text, "hits": item.hits}
            for item in snapshot.cache_hits
        ]

    @Property(str, notify=stateChanged)
    def lastRunOcrPeakText(self) -> str:
        return self._peak_text(
            self._last_run_snapshot.ocr_peak_seconds
            if self._last_run_snapshot is not None
            else None
        )

    @Property(str, notify=stateChanged)
    def lastRunLlmPeakText(self) -> str:
        return self._peak_text(
            self._last_run_snapshot.llm_peak_seconds
            if self._last_run_snapshot is not None
            else None
        )

    @Property(int, notify=stateChanged)
    def lastRunCanvasWidth(self) -> int:
        return self._last_run_snapshot.canvas_size[0] if self._last_run_snapshot and self._last_run_snapshot.canvas_size else 0

    @Property(int, notify=stateChanged)
    def lastRunCanvasHeight(self) -> int:
        return self._last_run_snapshot.canvas_size[1] if self._last_run_snapshot and self._last_run_snapshot.canvas_size else 0

    def _snapshot_entries(self) -> list[dict[str, object]]:
        snapshot = self._last_run_snapshot
        if snapshot is None:
            return []
        return [
            {
                "trackId": entry.track_id,
                "revision": entry.revision,
                "sourceText": entry.source_text,
                "translatedText": entry.translated_text,
                "confidence": entry.confidence,
                "left": entry.bounds[0],
                "top": entry.bounds[1],
                "right": entry.bounds[2],
                "bottom": entry.bounds[3],
            }
            for entry in snapshot.entries
        ]

    @staticmethod
    def _peak_text(seconds: float | None) -> str:
        if seconds is None:
            return "未产生"
        if seconds < 1:
            return f"{round(seconds * 1000)} ms"
        return f"{seconds:.2f} s"

    @Property(int, notify=stateChanged)
    def profileRevision(self) -> int:
        return self._profile_revision

    # ----- monitor and capture ----------------------------------------

    @Property(list, notify=stateChanged)
    def monitorNames(self) -> list[str]:
        return list(self._monitor_names)

    @Property(int, notify=stateChanged)
    def monitorIndex(self) -> int:
        return self._monitor_index

    @Property(bool, notify=stateChanged)
    def customRegion(self) -> bool:
        return self._custom_region

    @Property(int, notify=stateChanged)
    def captureLeft(self) -> int:
        return self._capture_left

    @Property(int, notify=stateChanged)
    def captureTop(self) -> int:
        return self._capture_top

    @Property(int, notify=stateChanged)
    def captureWidth(self) -> int:
        return self._capture_width

    @Property(int, notify=stateChanged)
    def captureHeight(self) -> int:
        return self._capture_height

    @Property(int, notify=stateChanged)
    def captureDisplayWidth(self) -> int:
        return self._selected_display_size()[0]

    @Property(int, notify=stateChanged)
    def captureDisplayHeight(self) -> int:
        return self._selected_display_size()[1]

    @Property(str, notify=stateChanged)
    def captureSummary(self) -> str:
        if not self._custom_region:
            return f"显示器 {self._monitor_index} · 整个显示器"
        return (
            f"显示器 {self._monitor_index} · "
            f"{self._capture_width}×{self._capture_height} · "
            f"左 {self._capture_left} · 上 {self._capture_top}"
        )

    @Property(list, notify=stateChanged)
    def detectionQualityNames(self) -> list[str]:
        return [label for label, _scale in _DETECTION_QUALITY_PRESETS]

    @Property(int, notify=stateChanged)
    def detectionQualityIndex(self) -> int:
        return self._detection_quality_index

    @Property(str, notify=stateChanged)
    def detectionQualitySummary(self) -> str:
        label, scale = _DETECTION_QUALITY_PRESETS[self._detection_quality_index]
        return f"{label} · {_detection_max_side_for_display(self._selected_display_long_side(), scale)} px"

    @Property(bool, notify=stateChanged)
    def textMergeAllowed(self) -> bool:
        return self._text_merge_allowed()

    @Property(list, notify=stateChanged)
    def ocrDeviceNames(self) -> list[str]:
        return list(self._ocr_device_names)

    @Property(list, notify=stateChanged)
    def ocrDeviceValues(self) -> list[str]:
        return list(self._ocr_device_values)

    @Property(list, notify=stateChanged)
    def ocrDeviceAvailability(self) -> list[bool]:
        return [
            value in self._available_ocr_device_values
            for value in self._ocr_device_values
        ]

    @Property(str, notify=stateChanged)
    def ocrDevice(self) -> str:
        return self._ocr_device

    @Property(str, notify=stateChanged)
    def ocrStatus(self) -> str:
        if self._ocr_device and self._ocr_device not in self._available_ocr_device_values:
            return f"{self._ocr_device}（当前不可用）"
        return self._ocr_device or "检测中"

    @Property(bool, notify=stateChanged)
    def ocrFilterEnabled(self) -> bool:
        return self._ocr_filter_enabled

    @Property(bool, notify=stateChanged)
    def ocrMergeEnabled(self) -> bool:
        return self._ocr_merge_enabled

    # ----- translation and overlay -----------------------------------

    @Property(str, notify=stateChanged)
    def backend(self) -> str:
        return self._backend

    @Property(list, notify=stateChanged)
    def builtinModelNames(self) -> list[str]:
        return [model.display_name for model in BUILTIN_MODELS]

    @Property(list, notify=stateChanged)
    def builtinModelIds(self) -> list[str]:
        return [model.model_id for model in BUILTIN_MODELS]

    @Property(str, notify=stateChanged)
    def builtinModel(self) -> str:
        return self._builtin_model

    @Property(list, notify=stateChanged)
    def builtinDeviceNames(self) -> list[str]:
        return list(self._builtin_device_names)

    @Property(list, notify=stateChanged)
    def builtinDeviceValues(self) -> list[str]:
        return list(self._builtin_device_values)

    @Property(list, notify=stateChanged)
    def builtinDeviceAvailability(self) -> list[bool]:
        return [
            value in self._available_builtin_device_values
            for value in self._builtin_device_values
        ]

    @Property(str, notify=stateChanged)
    def builtinCudaDevice(self) -> str:
        return self._builtin_cuda_device

    @Property(int, notify=stateChanged)
    def builtinParallel(self) -> int:
        return self._builtin_parallel

    @Property(list, notify=stateChanged)
    def builtinKvCacheOptions(self) -> list[str]:
        return ["f16", "q8_0"]

    @Property(str, notify=stateChanged)
    def builtinKvCacheType(self) -> str:
        return self._builtin_kv_cache_type

    @Property(str, notify=stateChanged)
    def builtinContextSummary(self) -> str:
        total = self._builtin_parallel * BUILTIN_CONTEXT_PER_SLOT
        return (
            f"每槽固定 {BUILTIN_CONTEXT_PER_SLOT} tokens · "
            f"总 ctx-size {total} · 最大输出固定 {BUILTIN_MAX_OUTPUT_TOKENS} tokens"
        )

    def _environment_api_key_name(self) -> str | None:
        environment_name = self._config.translation.api_key_env
        if os.environ.get(environment_name, "").strip():
            return environment_name
        if (
            environment_name == API_KEY_ENV
            and os.environ.get(LEGACY_API_KEY_ENV, "").strip()
        ):
            return LEGACY_API_KEY_ENV
        return None

    @Property(str, notify=stateChanged)
    def baseUrl(self) -> str:
        return self._base_url

    @Property(bool, notify=stateChanged)
    def apiKeyConfigured(self) -> bool:
        return (
            bool(self._api_key.strip())
            or self._environment_api_key_name() is not None
        )

    @Property(bool, notify=stateChanged)
    def apiKeyOverrideConfigured(self) -> bool:
        return bool(self._api_key.strip())

    @Property(str, notify=stateChanged)
    def apiKeyStatusText(self) -> str:
        if self._api_key.strip():
            return "已在本地配置中设置 · 输入将替换"
        environment_name = self._environment_api_key_name()
        if environment_name is not None:
            return f"已通过环境变量 {environment_name} 设置"
        return f"未配置 · 也可使用环境变量 {self._config.translation.api_key_env}"

    @Property(str, notify=stateChanged)
    def model(self) -> str:
        return self._model

    @Property(list, notify=stateChanged)
    def modelNames(self) -> list[str]:
        return list(self._model_ids)

    @Property(int, notify=stateChanged)
    def maxConcurrency(self) -> int:
        return self._max_concurrency

    @Property(str, notify=stateChanged)
    def customPrompt(self) -> str:
        return self._custom_prompt

    @Property(str, notify=stateChanged)
    def connectionState(self) -> str:
        return self._connection_state

    @Property(str, notify=stateChanged)
    def localModelStatus(self) -> str:
        try:
            model = get_builtin_model(self._builtin_model)
        except LocalBackendError as exc:
            return str(exc)
        root = local_backend_root(self._config_path)
        if self._local_install_thread is not None and self._local_install_thread.is_alive():
            return self._download_label or f"正在准备 {model.display_name}……"
        if model_is_ready(root, model) and runtime_is_ready(root):
            return f"已校验并可用；llama.cpp {LLAMA_CPP_VERSION}（{LLAMA_CPP_STABLE_VERSION}）CUDA 12.4。"
        if model_is_ready(root, model):
            return "模型已校验；仍需下载并安装 CUDA 本地运行时。"
        if runtime_is_ready(root):
            return f"需下载 {model.size_gib:.2f} GiB 模型；支持断点续传。"
        return f"需下载 {model.size_gib:.2f} GiB 模型及 CUDA 本地运行时；支持断点续传。"

    def _local_model_capabilities(self) -> tuple[bool, bool]:
        try:
            model = get_builtin_model(self._builtin_model)
        except LocalBackendError:
            return False, False
        root = local_backend_root(self._config_path)
        ready = model_is_ready(root, model) and runtime_is_ready(root)
        path = model_path(root, model)
        files_exist = path.is_file() or path.with_name(f"{path.name}.part").is_file()
        return ready, files_exist

    @Property(bool, notify=stateChanged)
    def localModelReady(self) -> bool:
        ready, _files_exist = self._local_model_capabilities()
        return ready

    @Property(bool, notify=stateChanged)
    def modelFilesExist(self) -> bool:
        _ready, files_exist = self._local_model_capabilities()
        return files_exist

    @Property(bool, notify=stateChanged)
    def canDownloadBuiltinModel(self) -> bool:
        return self.downloading or not self.localModelReady

    @Property(bool, notify=stateChanged)
    def canDeleteBuiltinModel(self) -> bool:
        return self.modelFilesExist and not self.downloading

    @Property(str, notify=stateChanged)
    def modelInstallActionText(self) -> str:
        if self.downloading:
            return "取消下载"
        if self.localModelReady:
            return "已下载"
        return "下载并使用"

    @Property(int, notify=stateChanged)
    def downloadProgress(self) -> int:
        return self._download_progress

    @Property(bool, notify=stateChanged)
    def downloading(self) -> bool:
        return self._local_install_thread is not None and self._local_install_thread.is_alive()

    @Property(str, notify=stateChanged)
    def blurMode(self) -> str:
        return (
            _BLUR_MODE_DARK
            if self._overlay_opacity > 0
            else _BLUR_MODE_ONLY
        )

    @Property(float, notify=stateChanged)
    def overlayOpacity(self) -> float:
        return self._overlay_opacity

    @Property(bool, notify=stateChanged)
    def browserOverlayEnabled(self) -> bool:
        return self._browser_overlay_enabled

    @Property(str, notify=stateChanged)
    def browserOverlayUrl(self) -> str:
        return self._config.recording.browser_overlay_url

    @Property(str, notify=stateChanged)
    def overlayStatus(self) -> str:
        percentage = int(self._overlay_opacity * 100 + 0.5)
        background = (
            f"模糊 + {percentage}% 黑色遮罩"
            if self._overlay_opacity > 0
            else "仅模糊"
        )
        return (
            f"背景：{background} · "
            f"OBS 译文源：{'开启' if self._browser_overlay_enabled else '关闭'}"
        )

    # ----- scheduling, cache and diagnostics -------------------------

    @Property(bool, notify=stateChanged)
    def dynamicRoiEnabled(self) -> bool:
        return self._dynamic_roi_enabled

    @Property(int, notify=stateChanged)
    def changePollFps(self) -> int:
        return self._change_poll_fps

    @Property(int, notify=stateChanged)
    def roiResponseTargetMs(self) -> int:
        return self._roi_response_target_ms

    @Property(int, notify=stateChanged)
    def clearAfterMs(self) -> int:
        return self._clear_after_ms

    @Property(int, notify=stateChanged)
    def settleRescanMs(self) -> int:
        return self._settle_rescan_ms

    @Property(int, notify=stateChanged)
    def idleRescanMs(self) -> int:
        return self._idle_rescan_ms

    @Property(int, notify=stateChanged)
    def ocrCooldownMs(self) -> int:
        return self._ocr_cooldown_ms

    @Property(bool, notify=stateChanged)
    def debugEnabled(self) -> bool:
        return self._debug_enabled

    @Property(str, notify=stateChanged)
    def profileDirectory(self) -> str:
        return str(self._profile.directory) if self._profile else "暂无 Profile"

    @Property(int, notify=stateChanged)
    def automaticEntries(self) -> int:
        return self._automatic_entries

    @Property(int, notify=stateChanged)
    def automaticHits(self) -> int:
        return self._automatic_hits

    @Property(int, notify=stateChanged)
    def manualCorrections(self) -> int:
        return self._manual_corrections

    @Property(int, notify=stateChanged)
    def manualHits(self) -> int:
        return self._manual_hits

    @Property(str, notify=stateChanged)
    def infoText(self) -> str:
        if self._profile is None:
            return "暂无真实 Profile 数据。请从 HOME 新建或选择一个配置。"
        capture = self._profile.capture_settings
        region = ",".join(map(str, capture.region)) if capture.region is not None else "使用 config.toml"
        monitor = str(capture.monitor_index) if capture.monitor_index is not None else "使用 config.toml"
        return (
            f"配置：{self._profile.display_name}\n"
            f"内部 ID：{self._profile.profile_id}\n"
            f"目录：{self._profile.directory}\n"
            f"显示器：{monitor}\n"
            f"字幕区域：{region}\n"
            f"配置提示词：{'已设置' if self._profile.custom_prompt else '未设置'}\n"
            f"术语：{len(self._profile.glossary)} 条\n"
            f"模型缓存：{self.automaticEntries} 条，命中 {self.automaticHits} 次\n"
            f"人工修订：{self.manualCorrections} 条，命中 {self.manualHits} 次"
        )

    @Property(list, notify=stateChanged)
    def glossaryEntries(self) -> list[dict[str, str]]:
        return list(self._glossary)

    @Property(bool, notify=stateChanged)
    def glossaryDirty(self) -> bool:
        return self._glossary_dirty

    @Property(list, notify=stateChanged)
    def correctionEntries(self) -> list[dict[str, str]]:
        return list(self._corrections)

    @Property(bool, notify=stateChanged)
    def correctionsDirty(self) -> bool:
        return self._corrections_dirty

    @Property(str, notify=stateChanged)
    def logTail(self) -> str:
        return _log_tail(self._live_log_path)

    # ----- navigation, profiles and theme ----------------------------

    @Slot(str)
    def setPage(self, page: str) -> None:
        if page not in {"HOME", "CAPTURE", "OCR", "TRANSLATION", "OVERLAY", "CACHE", "SETTINGS"}:
            return
        if page == self._current_page:
            return
        self._current_page = page
        self._emit_state()

    @Slot(int)
    def selectProfile(self, index: int) -> None:
        if not 0 <= index < len(self._profiles):
            return
        self._load_profile(self._profiles[index].profile_id, index)

    @Slot()
    def refreshProfiles(self) -> None:
        self._refresh_profiles()

    def _refresh_profiles(self, preferred_id: str | None = None) -> None:
        current_id = preferred_id or (
            self._profile.profile_id if self._profile else None
        )
        try:
            profiles = list_game_profiles(self._config_path, self._config)
        except (ProfileError, RuntimeError, ValueError) as exc:
            self._show_error("无法读取配置", exc)
            return
        self._profiles = profiles
        self._current_profile_index = next(
            (index for index, profile in enumerate(profiles) if profile.profile_id == current_id),
            0 if profiles else -1,
        )
        self.profilesChanged.emit()
        if profiles:
            selected_id = profiles[self._current_profile_index].profile_id
            preserve_drafts = (
                self._profile is not None
                and self._profile.profile_id == selected_id
                and (
                    self._prompt_dirty
                    or self._capture_dirty
                    or self._glossary_dirty
                    or self._corrections_dirty
                )
            )
            if preserve_drafts:
                self._notice("配置列表已刷新；未保存的当前配置草稿已保留", "neutral")
            else:
                self._load_profile(selected_id, self._current_profile_index)
        else:
            self._profile = None
            self._last_run_snapshot = None
            self._profile_revision += 1
            self._glossary = []
            self._corrections = []
            self._glossary_dirty = False
            self._corrections_dirty = False
            self._custom_prompt = ""
            self._monitor_index = (
                self._config.live.monitor_index
                if self._config.live.monitor_index in self._monitor_values
                else (0 if self._monitor_values else self._config.live.monitor_index)
            )
            self._capture_left = 0
            self._capture_top = 0
            self._capture_width = 0
            self._capture_height = 0
            self._custom_region = False
            self._automatic_entries = 0
            self._automatic_hits = 0
            self._manual_corrections = 0
            self._manual_hits = 0
            self._prompt_dirty = False
            self._capture_dirty = False
            self._set_status("请先在 HOME 创建一个 Profile", "warning")
            self._emit_state()

    @Slot(str)
    def createProfile(self, display_name: str) -> None:
        try:
            profile = create_named_game_profile(self._config_path, self._config, display_name)
        except (ProfileError, OSError, RuntimeError, ValueError) as exc:
            self._show_error("新建配置失败", exc)
            return
        self._profile = None
        self._refresh_profiles(profile.profile_id)
        self._notice(f"已创建 {profile.display_name}")

    def _load_profile(self, profile_id: str, index: int) -> None:
        try:
            profile = load_game_profile(self._config_path, self._config, profile_id)
            corrections = profile.cache.list_manual_corrections(
                source_language=self._config.ocr.language,
                target_language=self._config.translation.target_language,
            )
            stats = profile.cache.stats()
        except (ProfileError, RuntimeError, ValueError) as exc:
            self._show_error("加载配置失败", exc)
            return
        self._profile = profile
        self._last_run_snapshot = load_snapshot(profile.directory)
        self._profile_revision += 1
        self._current_profile_index = index
        self._custom_prompt = profile.custom_prompt
        capture = profile.capture_settings
        configured_monitor = (
            capture.monitor_index
            if capture.monitor_index is not None
            else self._config.live.monitor_index
        )
        monitor_warning = configured_monitor not in self._monitor_values
        self._monitor_index = 0 if monitor_warning and self._monitor_values else configured_monitor
        region = capture.region or (
            self._config.live.left,
            self._config.live.top,
            self._config.live.width,
            self._config.live.height,
        )
        self._capture_left, self._capture_top, self._capture_width, self._capture_height = region
        self._custom_region = self._capture_width > 0 and self._capture_height > 0
        self._glossary = [{"source": entry.source, "target": entry.target} for entry in profile.glossary]
        self._corrections = [
            {"source": entry.source_text, "target": entry.translated_text}
            for entry in corrections
        ]
        self._glossary_dirty = False
        self._corrections_dirty = False
        self._automatic_entries = stats.automatic_entries
        self._automatic_hits = stats.automatic_hits
        self._manual_corrections = stats.manual_corrections
        self._manual_hits = stats.manual_hits
        self._prompt_dirty = False
        self._capture_dirty = False
        self.profilesChanged.emit()
        self._emit_state()
        if monitor_warning:
            self._notice(
                f"已加载 {profile.display_name}；配置中的显示器 "
                f"{configured_monitor} 当前不存在，已临时选择显示器 0",
                "warning",
            )
        else:
            self._notice(f"已加载 {profile.display_name}", "neutral")

    def _reload_last_run_snapshot(self) -> None:
        if self._profile is None:
            self._last_run_snapshot = None
        else:
            self._last_run_snapshot = load_snapshot(self._profile.directory)
        self._emit_state()

    @Slot(str)
    def setTheme(self, value: str) -> None:
        if value not in {option[0] for option in THEME_OPTIONS}:
            return
        if value == self._theme_preference:
            return
        try:
            save_gui_preferences(self._config_path, GuiPreferences(theme=value))
        except (GuiSettingsError, OSError) as exc:
            self._show_error("保存界面主题失败", exc)
            return
        self._theme_preference = value
        app = QApplication.instance()
        self._effective_theme = effective_theme(value, app) if app else value
        self._notice(
            f"界面已切换为“{dict(THEME_OPTIONS).get(value, value)}”并保存",
            "success",
        )

    @Slot(bool)
    def setReducedMotion(self, value: bool) -> None:
        value = bool(value)
        if value == self._reduced_motion:
            return
        self._reduced_motion = value
        self._emit_state()

    def _system_theme_changed(self, *_args: object) -> None:
        if self._theme_preference != "system":
            return
        app = QApplication.instance()
        if app is not None:
            self._effective_theme = effective_theme(self._theme_preference, app)
            self._emit_state()

    # ----- capture and OCR --------------------------------------------

    def _refresh_monitors(self) -> None:
        app = QApplication.instance()
        screens = app.screens() if app is not None else []
        self._monitor_values = list(range(len(screens)))
        self._monitor_names = []
        for index, screen in enumerate(screens):
            geometry = screen.geometry()
            self._monitor_names.append(
                f"{index}: {screen.name()} · {geometry.width()}×{geometry.height()} · {screen.devicePixelRatio():g}x"
            )
        if self._monitor_values and self._monitor_index not in self._monitor_values:
            self._monitor_index = 0

    @Slot(int)
    def setMonitorIndex(self, index: int) -> None:
        if 0 <= index < len(self._monitor_values) and index != self._monitor_index:
            self._monitor_index = index
            self._mark_capture_dirty()

    @Slot(bool)
    def setCustomRegion(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._custom_region:
            return
        self._custom_region = enabled
        if not self._custom_region:
            self._capture_left = self._capture_top = self._capture_width = self._capture_height = 0
        self._mark_capture_dirty()

    @Slot(int, int, int, int)
    def setCaptureRegion(self, left: int, top: int, width: int, height: int) -> None:
        region = (
            max(0, int(left)),
            max(0, int(top)),
            max(0, int(width)),
            max(0, int(height)),
        )
        custom = region[2] > 0 and region[3] > 0
        if region == (self._capture_left, self._capture_top, self._capture_width, self._capture_height) and custom == self._custom_region:
            return
        self._capture_left, self._capture_top, self._capture_width, self._capture_height = region
        self._custom_region = custom
        self._mark_capture_dirty()

    @Slot()
    def selectRegion(self) -> None:
        if self._profile is None:
            self._show_error("无法框选区域", "请先选择一个 Profile")
            return
        if not 0 <= self._monitor_index < len(self._monitor_values):
            self._show_error("无法框选区域", "当前显示器不可用")
            return
        self.regionSelectionRequested.emit(self._monitor_index)

    @Slot(int, int, int, int)
    def acceptRegionSelection(
        self,
        left: int,
        top: int,
        width: int,
        height: int,
    ) -> None:
        self.setCaptureRegion(left, top, width, height)
        self.saveCapture()

    @Slot()
    def cancelRegionSelection(self) -> None:
        self._notice("已取消框选", "neutral")

    @Slot()
    def useFullScreen(self) -> None:
        self.setCustomRegion(False)
        self.saveCapture()

    def _save_capture(self, *, announce: bool) -> bool:
        if self._profile is None:
            self._show_error("保存区域失败", "请先选择一个 Profile")
            return False
        try:
            settings = ProfileCaptureSettings(
                monitor_index=self._monitor_index,
                region=(
                    self._capture_left,
                    self._capture_top,
                    self._capture_width,
                    self._capture_height,
                ),
            )
            save_profile_capture_settings(self._profile, settings)
            self._profile = load_game_profile(self._config_path, self._config, self._profile.profile_id)
        except (ProfileError, OSError, RuntimeError, ValueError) as exc:
            self._show_error("保存区域失败", exc)
            return False
        self._capture_dirty = False
        if announce:
            self._notice(f"区域已保存到 {self._profile.display_name}")
        else:
            self._emit_state()
        return True

    @Slot(result=bool)
    def saveCapture(self) -> bool:
        return self._save_capture(announce=True)

    @Slot()
    def probeOcrDevices(self) -> None:
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
            self._set_ocr_device_choices((), str(exc))
            return
        self._ocr_device_probe_started_at = time.monotonic()
        self._ocr_probe_monitor.start()
        self._set_status("正在检测 NVIDIA OCR 设备……", "neutral")

    def _check_ocr_device_probe(self) -> None:
        process = self._ocr_device_probe_process
        if process is None:
            self._ocr_probe_monitor.stop()
            return
        started_at = self._ocr_device_probe_started_at
        if process.poll() is None:
            if started_at is None or time.monotonic() - started_at < _OCR_DEVICE_PROBE_TIMEOUT_SECONDS:
                return
            process.terminate()
            self._ocr_device_probe_process = None
            self._ocr_probe_monitor.stop()
            self._set_ocr_device_choices((), "硬件检测超过 20 秒，已停止")
            return
        output, _stderr = process.communicate()
        self._ocr_device_probe_process = None
        self._ocr_probe_monitor.stop()
        try:
            if process.returncode:
                raise RuntimeError(output.strip()[-1200:] or f"硬件检测退出码 {process.returncode}")
            devices = _parse_ocr_device_probe_output(output)
        except (json.JSONDecodeError, RuntimeError, ValueError) as exc:
            self._set_ocr_device_choices((), str(exc))
            return
        self._set_ocr_device_choices(devices, None)

    def _set_ocr_device_choices(self, devices: tuple[tuple[str, str], ...], error: str | None) -> None:
        available_values = [device for device, _label in devices]
        available_names = [label for _device, label in devices]
        self._available_ocr_device_values = set(available_values)
        self._available_builtin_device_values = {
            BUILTIN_CUDA_DEVICE_FOLLOW_OCR,
            *available_values,
        }
        self._ocr_device_values = list(available_values)
        self._ocr_device_names = list(available_names)
        if self._ocr_device not in self._ocr_device_values:
            self._ocr_device_values.append(self._ocr_device)
            self._ocr_device_names.append(f"{self._ocr_device}（当前不可用）")
        self._builtin_device_values = [
            BUILTIN_CUDA_DEVICE_FOLLOW_OCR,
            *available_values,
        ]
        self._builtin_device_names = [
            "跟随 OCR 设备（推荐）",
            *available_names,
        ]
        if self._builtin_cuda_device not in self._builtin_device_values:
            self._builtin_device_values.append(self._builtin_cuda_device)
            self._builtin_device_names.append(
                f"{self._builtin_cuda_device}（当前不可用）"
            )
        if error:
            self._set_status(f"OCR 硬件检测失败：{error}", "warning")
        elif devices:
            self._set_status(f"已发现 {len(devices)} 张 NVIDIA GPU", "success")
        else:
            self._set_status("未检测到可用的 NVIDIA GPU；启动时仍会再次校验", "warning")
        self._emit_state()

    @Slot(str)
    def setOcrDevice(self, value: str) -> None:
        if value in self._available_ocr_device_values and value != self._ocr_device:
            self._ocr_device = value
            self._mark_runtime_dirty()

    @Slot(bool)
    def setOcrFilterEnabled(self, value: bool) -> None:
        value = bool(value)
        if value == self._ocr_filter_enabled:
            return
        self._ocr_filter_enabled = value
        self._mark_runtime_dirty()

    @Slot(bool)
    def setOcrMergeEnabled(self, value: bool) -> None:
        value = bool(value) and self._text_merge_allowed()
        if value == self._ocr_merge_enabled:
            return
        self._ocr_merge_enabled = value
        self._mark_runtime_dirty()

    @Slot(int)
    def setDetectionQualityIndex(self, value: int) -> None:
        value = max(0, min(len(_DETECTION_QUALITY_PRESETS) - 1, int(value)))
        merge_enabled = self._ocr_merge_enabled and _DETECTION_QUALITY_PRESETS[value][1] >= _TEXT_MERGE_MIN_DETECTION_SCALE
        if value == self._detection_quality_index and merge_enabled == self._ocr_merge_enabled:
            return
        self._detection_quality_index = value
        self._ocr_merge_enabled = merge_enabled
        self._mark_runtime_dirty()

    def _selected_display_size(self) -> tuple[int, int]:
        app = QApplication.instance()
        screens = app.screens() if app is not None else []
        if 0 <= self._monitor_index < len(screens):
            screen = screens[self._monitor_index]
            geometry = screen.geometry()
            scale = max(1.0, float(screen.devicePixelRatio()))
            return (
                max(1, round(geometry.width() * scale)),
                max(1, round(geometry.height() * scale)),
            )
        return 0, 0

    def _selected_display_long_side(self) -> int:
        width, height = self._selected_display_size()
        if width > 0 and height > 0:
            return max(width, height)
        return max(_DETECTION_MIN_SIDE, self._config.ocr.detection_max_side * 2)

    def _text_merge_allowed(self) -> bool:
        return _DETECTION_QUALITY_PRESETS[self._detection_quality_index][1] >= _TEXT_MERGE_MIN_DETECTION_SCALE

    def _restore_detection_quality_from_config(self) -> None:
        configured = self._config.ocr.detection_max_side
        long_side = self._selected_display_long_side()
        self._detection_quality_index = min(
            range(len(_DETECTION_QUALITY_PRESETS)),
            key=lambda index: abs(_detection_max_side_for_display(long_side, _DETECTION_QUALITY_PRESETS[index][1]) - configured),
        )

    # ----- translation, overlay and settings drafts ------------------

    @Slot(str)
    def setBackend(self, value: str) -> None:
        if self.downloading:
            return
        if value in {"external", "builtin"} and value != self._backend:
            self._backend = value
            self._mark_runtime_dirty()

    @Slot(str)
    def setBuiltinModel(self, value: str) -> None:
        if self.downloading:
            return
        if value in [model.model_id for model in BUILTIN_MODELS] and value != self._builtin_model:
            self._builtin_model = value
            self._mark_runtime_dirty()

    @Slot(str)
    def setBuiltinCudaDevice(self, value: str) -> None:
        if (
            value in self._available_builtin_device_values
            and value != self._builtin_cuda_device
        ):
            self._builtin_cuda_device = value
            self._mark_runtime_dirty()

    @Slot(int)
    def setBuiltinParallel(self, value: int) -> None:
        value = max(1, min(BUILTIN_PARALLEL_MAX, int(value)))
        if value == self._builtin_parallel:
            return
        self._builtin_parallel = value
        self._mark_runtime_dirty()

    @Slot(str)
    def setBuiltinKvCacheType(self, value: str) -> None:
        if value in BUILTIN_KV_CACHE_TYPES and value != self._builtin_kv_cache_type:
            self._builtin_kv_cache_type = value
            self._mark_runtime_dirty()

    @Slot(str)
    def setBaseUrl(self, value: str) -> None:
        if value == self._base_url:
            return
        self._base_url = value
        self._mark_runtime_dirty()

    @Slot(str)
    def setApiKey(self, value: str) -> None:
        if value == self._api_key:
            return
        self._api_key = value
        self._mark_runtime_dirty()

    @Slot()
    def clearApiKey(self) -> None:
        self.setApiKey("")

    @Slot(str)
    def setModel(self, value: str) -> None:
        if value == self._model:
            return
        self._model = value
        self._mark_runtime_dirty()

    @Slot(int)
    def setMaxConcurrency(self, value: int) -> None:
        value = max(1, min(32, int(value)))
        if value == self._max_concurrency:
            return
        self._max_concurrency = value
        self._mark_runtime_dirty()

    @Slot(str)
    def setCustomPrompt(self, value: str) -> None:
        if value == self._custom_prompt:
            return
        self._custom_prompt = value
        self._mark_prompt_dirty()

    @Slot(str)
    def setBlurMode(self, value: str) -> None:
        if value == _BLUR_MODE_DARK:
            self.setOverlayOpacity(DEFAULT_DARK_OVERLAY_OPACITY)
        elif value == _BLUR_MODE_ONLY:
            self.setOverlayOpacity(0.0)

    @Slot(float)
    def setOverlayOpacity(self, value: float) -> None:
        value = round(max(0.0, min(1.0, float(value))), 2)
        if value == self._overlay_opacity:
            return
        self._overlay_opacity = value
        self._mark_runtime_dirty()

    @Slot(bool)
    def setBrowserOverlayEnabled(self, value: bool) -> None:
        value = bool(value)
        if value == self._browser_overlay_enabled:
            return
        self._browser_overlay_enabled = value
        self._mark_runtime_dirty()

    @Slot(bool)
    def setDynamicRoiEnabled(self, value: bool) -> None:
        value = bool(value)
        if value == self._dynamic_roi_enabled:
            return
        self._dynamic_roi_enabled = value
        self._mark_runtime_dirty()

    @Slot(int)
    def setChangePollFps(self, value: int) -> None:
        value = max(1, min(MAX_CHANGE_POLL_FPS, int(value)))
        if value == self._change_poll_fps:
            return
        self._change_poll_fps = value
        self._mark_runtime_dirty()

    @Slot(int)
    def setRoiResponseTargetMs(self, value: int) -> None:
        value = max(100, min(5000, int(value)))
        if value == self._roi_response_target_ms:
            return
        self._roi_response_target_ms = value
        self._mark_runtime_dirty()

    @Slot(int)
    def setClearAfterMs(self, value: int) -> None:
        value = max(50, min(1000, int(value)))
        if value == self._clear_after_ms:
            return
        self._clear_after_ms = value
        self._mark_runtime_dirty()

    @Slot(int)
    def setSettleRescanMs(self, value: int) -> None:
        value = max(0, min(60000, int(value)))
        if value == self._settle_rescan_ms:
            return
        self._settle_rescan_ms = value
        self._mark_runtime_dirty()

    @Slot(int)
    def setIdleRescanMs(self, value: int) -> None:
        value = max(0, min(60000, int(value)))
        if value == self._idle_rescan_ms:
            return
        self._idle_rescan_ms = value
        self._mark_runtime_dirty()

    @Slot(int)
    def setOcrCooldownMs(self, value: int) -> None:
        value = max(0, min(10000, int(value)))
        if value == self._ocr_cooldown_ms:
            return
        self._ocr_cooldown_ms = value
        self._mark_runtime_dirty()

    @Slot(bool)
    def setDebugEnabled(self, value: bool) -> None:
        value = bool(value)
        if value == self._debug_enabled:
            return
        self._debug_enabled = value
        self._emit_state()

    def _translation_candidate(self, *, require_model: bool = True):
        model = self._model.strip()
        if not model and not require_model:
            model = self._config.translation.model
        return replace(
            self._config.translation,
            backend=self._backend,
            builtin_model=self._builtin_model,
            builtin_cuda_device=self._builtin_cuda_device,
            builtin_parallel=self._builtin_parallel,
            builtin_kv_cache_type=self._builtin_kv_cache_type,
            base_url=self._base_url.strip(),
            model=model,
            api_key=self._api_key,
            max_concurrency=self._max_concurrency,
        )

    def _ocr_candidate(self):
        if not self._ocr_device:
            raise ConfigError("当前没有可用的 OCR 设备")
        scale = _DETECTION_QUALITY_PRESETS[self._detection_quality_index][1]
        return replace(
            self._config.ocr,
            device=self._ocr_device,
            detection_max_side=_detection_max_side_for_display(self._selected_display_long_side(), scale),
            text_filter_enabled=self._ocr_filter_enabled,
            text_merge_enabled=self._ocr_merge_enabled and self._text_merge_allowed(),
        )

    def _live_candidate(self):
        return replace(
            self._config.live,
            settle_rescan_ms=self._settle_rescan_ms,
            idle_rescan_ms=self._idle_rescan_ms,
            ocr_cooldown_ms=self._ocr_cooldown_ms,
            clear_after_ms=self._clear_after_ms,
            dynamic_roi_enabled=self._dynamic_roi_enabled,
            change_poll_fps=self._change_poll_fps,
            dynamic_roi_response_target_ms=self._roi_response_target_ms,
            monitor_index=self._monitor_index,
            left=self._capture_left if self._custom_region else 0,
            top=self._capture_top if self._custom_region else 0,
            width=self._capture_width if self._custom_region else 0,
            height=self._capture_height if self._custom_region else 0,
        )

    def _save_runtime_settings(self, *, announce: bool) -> bool:
        try:
            translation = self._translation_candidate()
            ocr = self._ocr_candidate()
            live = self._live_candidate()
            self._config = save_runtime_selection(
                self._config_path,
                base_url=translation.base_url,
                model=translation.model,
                backend=translation.backend,
                builtin_model=translation.builtin_model,
                builtin_cuda_device=translation.builtin_cuda_device,
                builtin_parallel=translation.builtin_parallel,
                builtin_kv_cache_type=translation.builtin_kv_cache_type,
                api_key=translation.api_key,
                ocr_device=ocr.device,
                max_concurrency=translation.max_concurrency,
                ocr_detection_max_side=ocr.detection_max_side,
                ocr_text_filter_enabled=ocr.text_filter_enabled,
                ocr_text_merge_enabled=ocr.text_merge_enabled,
                preview_overlay_opacity=self._overlay_opacity,
                recording_browser_overlay_enabled=self._browser_overlay_enabled,
                recording_browser_overlay_port=self._config.recording.browser_overlay_port,
                settle_rescan_ms=live.settle_rescan_ms,
                idle_rescan_ms=live.idle_rescan_ms,
                ocr_cooldown_ms=live.ocr_cooldown_ms,
                clear_after_ms=live.clear_after_ms,
                dynamic_roi_enabled=live.dynamic_roi_enabled,
                change_poll_fps=live.change_poll_fps,
                dynamic_roi_response_target_ms=live.dynamic_roi_response_target_ms,
            )
        except (ConfigError, OSError, RuntimeError, ValueError) as exc:
            self._show_error("保存运行设置失败", exc)
            return False
        translation = self._config.translation
        ocr = self._config.ocr
        live = self._config.live
        self._backend = translation.backend
        self._builtin_model = translation.builtin_model
        self._builtin_cuda_device = translation.builtin_cuda_device
        self._builtin_parallel = translation.builtin_parallel
        self._builtin_kv_cache_type = translation.builtin_kv_cache_type
        self._base_url = translation.base_url
        self._api_key = translation.api_key
        self._model = translation.model
        self._model_ids = [
            self._model,
            *[model for model in self._model_ids if model != self._model],
        ]
        self._max_concurrency = translation.max_concurrency
        self._ocr_device = ocr.device
        self._ocr_filter_enabled = ocr.text_filter_enabled
        self._ocr_merge_enabled = ocr.text_merge_enabled
        self._overlay_opacity = self._config.preview.overlay_opacity
        self._browser_overlay_enabled = (
            self._config.recording.browser_overlay_enabled
        )
        self._dynamic_roi_enabled = live.dynamic_roi_enabled
        self._change_poll_fps = live.change_poll_fps
        self._roi_response_target_ms = live.dynamic_roi_response_target_ms
        self._clear_after_ms = live.clear_after_ms
        self._settle_rescan_ms = live.settle_rescan_ms
        self._idle_rescan_ms = live.idle_rescan_ms
        self._ocr_cooldown_ms = live.ocr_cooldown_ms
        self._restore_detection_quality_from_config()
        self._runtime_dirty = False
        if announce:
            self._notice("运行设置已保存")
        else:
            self._emit_state()
        return True

    @Slot(result=bool)
    def saveRuntimeSettings(self) -> bool:
        return self._save_runtime_settings(announce=True)

    def _save_custom_prompt(self, *, announce: bool) -> bool:
        if self._profile is None:
            self._show_error("保存配置提示词失败", "请先选择一个 Profile")
            return False
        try:
            save_profile_custom_prompt(self._profile, self._custom_prompt)
            self._profile = load_game_profile(
                self._config_path,
                self._config,
                self._profile.profile_id,
            )
            self._custom_prompt = self._profile.custom_prompt
        except (ProfileError, OSError, RuntimeError, ValueError) as exc:
            self._show_error("保存配置提示词失败", exc)
            return False
        self._prompt_dirty = False
        if announce:
            self._notice(f"{self._profile.display_name} 的配置提示词已保存")
        else:
            self._emit_state()
        return True

    @Slot(result=bool)
    def saveCustomPrompt(self) -> bool:
        return self._save_custom_prompt(announce=True)

    @Slot(result=bool)
    def saveAll(self) -> bool:
        if self._profile is None:
            self._show_error("保存失败", "请先选择一个 Profile")
            return False
        if not self._save_runtime_settings(announce=False):
            return False
        if not self._save_custom_prompt(announce=False):
            return False
        if not self._save_capture(announce=False):
            return False
        self._notice("已应用运行设置、配置提示词和捕获区域")
        return True

    @Slot()
    def resetCustomPrompt(self) -> None:
        self._custom_prompt = ""
        self._prompt_dirty = True
        self._notice("已恢复内置默认提示词；保存更改后生效", "neutral")

    @Slot()
    def testConnection(self) -> None:
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
        if translation.resolved_api_key:
            request.setRawHeader(b"Authorization", f"Bearer {translation.resolved_api_key}".encode("utf-8"))
        reply = self._network_manager.get(request)
        self._model_reply = reply
        self._connection_state = f"正在连接 {url.toString()}……"
        self._emit_state()
        reply.finished.connect(lambda current=reply, requested=url.toString(): self._models_loaded(current, requested))

    def _models_loaded(self, reply: QNetworkReply, requested_url: str) -> None:
        if reply is not self._model_reply:
            reply.deleteLater()
            return
        self._model_reply = None
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                prefix = f"HTTP {status}：" if status is not None else ""
                raise TranslationTransportError(prefix + reply.errorString())
            raw = bytes(reply.readAll())
            payload = json.loads(raw.decode("utf-8-sig"))
            models = parse_model_ids(payload)
        except (TranslationTransportError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._connection_state = f"读取失败：{exc}"
            self._show_error("读取模型列表失败", exc)
        else:
            current = self._model.strip()
            available = list(dict.fromkeys(models))
            if current:
                self._model_ids = [current, *[model for model in available if model != current]]
            else:
                self._model_ids = available
                if available:
                    self._model = available[0]
            self._connection_state = f"已从 {requested_url} 读取 {len(models)} 个模型"
            self._notice(self._connection_state)
        finally:
            reply.deleteLater()
            self._emit_state()

    # ----- local model installation ----------------------------------

    @Slot()
    def downloadBuiltinModel(self) -> None:
        thread = self._local_install_thread
        if thread is not None and thread.is_alive():
            self._local_install_cancel.set()
            self._notice("正在取消下载……", "warning")
            return
        try:
            model = get_builtin_model(self._builtin_model)
            if self.localModelReady:
                self._notice(
                    f"{model.display_name} 已经下载并校验完成",
                    "neutral",
                )
                return
            if not self._save_runtime_settings(announce=False):
                return
        except (ConfigError, LocalBackendError) as exc:
            self._show_error("无法下载内置模型", exc)
            return
        self._local_install_cancel = threading.Event()
        self._local_install_events = queue.SimpleQueue()
        root = local_backend_root(self._config_path)

        def progress(phase: str, label: str, completed: int, total: int) -> None:
            self._local_install_events.put(("progress", phase, label, completed, total))

        def install() -> None:
            try:
                install_local_backend(root, model.model_id, progress=progress, cancel=self._local_install_cancel)
            except LocalBackendDownloadCancelled:
                self._local_install_events.put(("cancelled",))
            except Exception as exc:  # pragma: no cover - defensive worker boundary
                self._local_install_events.put(("error", str(exc)))
            else:
                self._local_install_events.put(("done",))

        self._local_install_thread = threading.Thread(target=install, name="local-llm-installer", daemon=True)
        self._local_install_thread.start()
        self._download_progress = 0
        self._download_label = f"正在准备 {model.display_name}；可随时取消并保留断点。"
        self._local_install_monitor.start()
        self._emit_state()

    @Slot(bool)
    def deleteBuiltinModel(self, confirmed: bool) -> None:
        if not confirmed:
            self._show_error("删除内置模型失败", "未确认删除操作")
            return
        thread = self._local_install_thread
        if thread is not None and thread.is_alive():
            self._show_error("删除内置模型失败", "模型正在下载，请先取消并等待任务停止")
            return
        if not self.modelFilesExist:
            self._show_error(
                "删除内置模型失败",
                "当前模型没有可删除的本地文件",
            )
            return
        try:
            model = get_builtin_model(self._builtin_model)
            root = local_backend_root(self._config_path)
            released = remove_builtin_model(root, model.model_id)
        except (OSError, LocalBackendError) as exc:
            self._show_error("删除内置模型失败", exc)
            return
        self._notice(f"已删除 {model.display_name}，释放 {released / (1024**3):.2f} GiB", "neutral")

    def _check_local_install_events(self) -> None:
        terminal = False
        while True:
            try:
                event = self._local_install_events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "progress":
                _kind, phase, label, completed, total = event
                self._download_progress = 0 if total <= 0 else max(0, min(100, round(completed / total * 100)))
                self._download_label = f"{label} · {phase}"
            elif event[0] == "cancelled":
                self._notice("已取消下载，已保留可续传文件。", "warning")
                terminal = True
            elif event[0] == "error":
                self._show_error("内置模型下载失败", str(event[1]))
                terminal = True
            elif event[0] == "done":
                self._download_progress = 100
                self._notice("内置模型已下载并校验完成。")
                terminal = True
        if terminal:
            self._local_install_monitor.stop()
            self._local_install_thread = None
        self._emit_state()

    # ----- glossary, corrections and cache ----------------------------

    @staticmethod
    def _draft_rows_from_variant(value: object) -> list[dict[str, str]]:
        if value is None:
            return []
        if not isinstance(value, (list, tuple)):
            raise ValueError("编辑器数据不是列表")
        rows: list[dict[str, str]] = []
        for row in value:
            if not isinstance(row, dict):
                raise ValueError("编辑器行不是对象")
            source = row.get("source", row.get("sourceText", ""))
            target = row.get("target", row.get("translatedText", ""))
            if not isinstance(source, str) or not isinstance(target, str):
                raise ValueError("编辑器行必须包含文本")
            rows.append({"source": source, "target": target})
        return rows

    @Slot("QVariantList")
    def setGlossaryDraft(self, value: object) -> None:
        if self._profile is None:
            return
        try:
            rows = self._draft_rows_from_variant(value)
        except ValueError as exc:
            self._show_error("更新术语表草稿失败", exc)
            return
        self._glossary = rows
        self._glossary_dirty = True
        self._emit_state()

    @Slot("QVariantList")
    def setCorrectionsDraft(self, value: object) -> None:
        if self._profile is None:
            return
        try:
            rows = self._draft_rows_from_variant(value)
        except ValueError as exc:
            self._show_error("更新人工修订草稿失败", exc)
            return
        self._corrections = rows
        self._corrections_dirty = True
        self._emit_state()

    @staticmethod
    def _pairs_from_variant(value: object, *, correction: bool = False) -> tuple[tuple[str, str], ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("编辑器数据不是列表")
        pairs: list[tuple[str, str]] = []
        for row in value:
            if not isinstance(row, dict):
                raise ValueError("编辑器行不是对象")
            source = row.get("source", row.get("sourceText", ""))
            target = row.get("target", row.get("translatedText", ""))
            if not isinstance(source, str) or not isinstance(target, str):
                raise ValueError("编辑器行必须包含文本")
            if bool(source.strip()) != bool(target.strip()):
                pair_name = "人工修订" if correction else "术语"
                raise ValueError(f"{pair_name}的原文和译文必须同时填写")
            if source.strip() or target.strip():
                pairs.append((source, target))
        return tuple(pairs)

    @Slot("QVariantList")
    def saveGlossary(self, value: object) -> None:
        if self._profile is None:
            self._show_error("保存术语表失败", "请先选择一个 Profile")
            return
        try:
            entries = tuple(GlossaryEntry(source, target) for source, target in self._pairs_from_variant(value))
            save_profile_glossary(self._profile, entries)
            self._profile = load_game_profile(self._config_path, self._config, self._profile.profile_id)
            self._profile_revision += 1
            self._glossary = [{"source": entry.source, "target": entry.target} for entry in self._profile.glossary]
            self._glossary_dirty = False
        except (ProfileError, OSError, RuntimeError, ValueError) as exc:
            self._show_error("保存术语表失败", exc)
            return
        self._notice(f"术语表已保存，共 {len(self._glossary)} 条")
        self._emit_state()

    @Slot("QVariantList")
    def saveCorrections(self, value: object) -> None:
        if self._profile is None:
            self._show_error("保存人工修订失败", "请先选择一个 Profile")
            return
        try:
            corrections = self._pairs_from_variant(value, correction=True)
            self._profile.cache.replace_manual_corrections(
                corrections,
                source_language=self._config.ocr.language,
                target_language=self._config.translation.target_language,
            )
            stats = self._profile.cache.stats()
            self._profile_revision += 1
            self._corrections = [{"source": source, "target": target} for source, target in corrections]
            self._corrections_dirty = False
            self._automatic_entries = stats.automatic_entries
            self._automatic_hits = stats.automatic_hits
            self._manual_corrections = stats.manual_corrections
            self._manual_hits = stats.manual_hits
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_error("保存人工修订失败", exc)
            return
        self._notice(f"人工修订已保存，共 {len(self._corrections)} 条")
        self._emit_state()

    @Slot()
    def refreshStats(self) -> None:
        if self._profile is None:
            self._set_status("暂无可刷新的 Profile 数据", "warning")
            return
        try:
            stats = self._profile.cache.stats()
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_error("刷新统计失败", exc)
            return
        self._automatic_entries = stats.automatic_entries
        self._automatic_hits = stats.automatic_hits
        self._manual_corrections = stats.manual_corrections
        self._manual_hits = stats.manual_hits
        self._notice("已刷新当前 Profile 的真实缓存统计", "neutral")

    # ----- live process ------------------------------------------------

    def _set_run_state(self, text: str, tone: str, running: bool) -> None:
        self._run_state = text
        self._run_tone = tone
        self._live_stop_requested = text in {"正在停止", "正在保存并停止", "正在强制停止"}
        self._emit_state()

    @Slot()
    def toggleLive(self) -> None:
        if self.running:
            self.stopLive()
        else:
            self.startLive()

    @Slot()
    def stopLive(self) -> None:
        process = self._live_process
        if process is None or process.poll() is not None:
            self._live_process = None
            self._set_run_state("已停止", "neutral", False)
            return
        if self._live_stop_requested:
            if not self._live_force_stop_available or self._live_force_stop_requested:
                return
            try:
                process.terminate()
            except OSError as exc:
                self._show_error("强制停止实时翻译失败", exc)
                return
            self._live_force_stop_requested = True
            self._set_run_state("正在强制停止", "warning", True)
            self._set_status("正在强制停止实时翻译；未完成的新快照不会覆盖旧快照。", "warning")
            return
        if not _request_live_graceful_shutdown(process):
            self._set_status(
                "无法请求实时翻译正常关闭；实时进程仍在运行，可再次尝试。",
                "error",
            )
            return
        self._live_stop_requested = True
        self._live_stop_started_at = time.monotonic()
        self._live_force_stop_available = False
        self._live_force_stop_requested = False
        self._set_run_state("正在保存并停止", "warning", True)
        self._set_status("正在保存并停止", "warning")

    @Slot()
    def startLive(self) -> None:
        if self._profile is None:
            self._show_error("无法开始翻译", "请先选择一个 Profile")
            return
        if self.running:
            self._show_error("实时翻译已在运行", "请先停止现有翻译进程")
            return
        try:
            model = get_builtin_model(self._builtin_model)
            if self._backend == "builtin" and not local_backend_is_ready(local_backend_root(self._config_path), model.model_id):
                raise LocalBackendError("请先下载并校验内置模型")
            selected_device = self._ocr_candidate().device
            self._set_status(f"正在检查 OCR 设备 {selected_device}……", "neutral")
            QApplication.processEvents()
            runtime_description = _validate_ocr_device_isolated(selected_device)
            if not self.saveAll():
                return
        except (ConfigError, LocalBackendError, OSError, RuntimeError, ValueError) as exc:
            self._show_error("启动实时翻译失败", exc)
            return
        arguments = ["-m", "game_screen_translator", "--config", str(self._config_path), "live", "--profile", self._profile.profile_id]
        if self._debug_enabled:
            arguments.append("--debug-border")
        try:
            self._live_log_path.parent.mkdir(parents=True, exist_ok=True)
            environment = os.environ.copy()
            environment.update(PYTHONFAULTHANDLER="1", PYTHONUNBUFFERED="1", PYTHONUTF8="1")
            creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
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
        self._live_waiting_for_ready = self._backend == "builtin"
        self._live_stop_requested = False
        self._live_stop_started_at = None
        self._live_force_stop_available = False
        self._live_force_stop_requested = False
        self._live_monitor.start()
        self._set_run_state("正在启动" if self._live_waiting_for_ready else "正在翻译", "warning" if self._live_waiting_for_ready else "success", True)
        self._set_status(f"实时翻译正在启动（进程 {process.pid}，{runtime_description}）", "neutral")
        if not self._live_waiting_for_ready:
            self.liveReady.emit()

    def _check_live_process(self) -> None:
        process = self._live_process
        if process is None:
            self._live_monitor.stop()
            return
        exit_code = process.poll()
        if exit_code is None:
            if (
                self._live_stop_requested
                and not self._live_force_stop_requested
                and not self._live_force_stop_available
                and self._live_stop_started_at is not None
                and time.monotonic() - self._live_stop_started_at >= _LIVE_STOP_GRACE_SECONDS
            ):
                self._live_force_stop_available = True
                self._emit_state()
            if self._live_waiting_for_ready:
                log = _log_tail(self._live_log_path)
                if f"[{PRODUCT_NAME} Live] ready" in log:
                    self._live_waiting_for_ready = False
                    self._set_run_state("正在翻译", "success", True)
                    self.liveReady.emit()
            return
        self._live_monitor.stop()
        self._live_process = None
        was_force_stop_requested = self._live_force_stop_requested
        self._live_stop_requested = False
        self._live_stop_started_at = None
        self._live_force_stop_available = False
        self._live_force_stop_requested = False
        if exit_code == 0:
            self._set_run_state("已停止", "neutral", False)
            self._set_status("实时翻译已关闭", "neutral")
            self._reload_last_run_snapshot()
            self.liveFinished.emit()
        elif was_force_stop_requested:
            self._set_run_state("已强制停止", "warning", False)
            self._set_status("已强制停止，保留上次快照。", "warning")
            # Restore an interactive workbench, without claiming a normal
            # saved finish or reloading an incomplete snapshot.
            self.liveFinished.emit()
        else:
            self._set_run_state("异常退出", "error", False)
            self.liveFailed.emit()
            self._show_error(
                "实时翻译进程异常退出",
                f"退出码：{exit_code}\n日志：{self._live_log_path}\n\n"
                f"{_log_tail(self._live_log_path)}",
            )

    @Slot()
    def shutdown(self) -> None:
        self._local_install_cancel.set()
        self._local_install_monitor.stop()
        self._ocr_probe_monitor.stop()
        self._live_monitor.stop()
        process = self._ocr_device_probe_process
        if process is not None and process.poll() is None:
            process.terminate()

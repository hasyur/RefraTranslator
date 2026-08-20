from __future__ import annotations

import asyncio
import ctypes
import os
import sys
import time
from collections import Counter, deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

import numpy as np

from game_screen_translator.branding import LIVE_PROCESS_NAME, PRODUCT_NAME
from game_screen_translator.capture.dxcam_capture import DxcamCapture
from game_screen_translator.config import AppConfig
from game_screen_translator.domain import (
    ContextPair,
    RevisionRegistry,
    SourceText,
    TranslationBatch,
    TranslationResult,
)
from game_screen_translator.live.change_detector import FrameChangeDetector
from game_screen_translator.live.latency import LiveLatencyStats
from game_screen_translator.live.tracker import (
    Bounds,
    StableTextTracker,
    TrackedText,
    normalize_text,
)
from game_screen_translator.ocr.contextual_roi import (
    ContextualRoiPlan,
    ContextualRoiPlanner,
    build_contextual_ocr_update,
)
from game_screen_translator.ocr.dynamic_roi import FullScreenRoiDetector
from game_screen_translator.ocr.layout import merge_ocr_text_blocks
from game_screen_translator.ocr.paddle import PaddleOcrEngine
from game_screen_translator.ocr.roi import OcrRoi, recognize_ocr_rois
from game_screen_translator.ocr.roi_scheduler import (
    LatestFrameRoiScheduler,
    ScheduledRoiScan,
)
from game_screen_translator.ocr.text_filter import OcrTextFilter, RejectedOcrText
from game_screen_translator.ocr.types import OcrText
from game_screen_translator.overlay.window import (
    OverlayStyle,
    TranslationOverlay,
    exclude_window_from_capture,
)
from game_screen_translator.profiles import GameProfile
from game_screen_translator.translation.cached import (
    CachedTranslationOutcome,
    CachedTranslationService,
)
from game_screen_translator.translation.hy_mt import (
    HyMtPromptBuilder,
    TranslationProtocolError,
)
from game_screen_translator.translation.service import TranslationService
from game_screen_translator.translation.transport import (
    OpenAICompatibleTransport,
    TranslationTransportError,
)

try:
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - exercised only without GUI extra
    raise RuntimeError("尚未安装 GUI 依赖。请运行：.\\bootstrap.ps1 -WithGui") from exc


BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
_MAX_TRANSLATION_ATTEMPTS = 3
_TRANSLATION_RETRY_BASE_SECONDS = 0.35
_PENDING_TRANSLATION_BATCHES_PER_WORKER = 2
_ROI_INITIAL_RETRY_SECONDS = 1.0
_ROI_INTERNAL_EDGE_MARGIN = 12


def _live_message(message: str) -> None:
    print(f"[{PRODUCT_NAME} Live] {message}", flush=True)


def _bounds_distance_squared(first: Bounds | None, second: Bounds) -> float:
    if first is None:
        return 0.0
    first_x = (first[0] + first[2]) / 2
    first_y = (first[1] + first[3]) / 2
    second_x = (second[0] + second[2]) / 2
    second_y = (second[1] + second[3]) / 2
    return (first_x - second_x) ** 2 + (first_y - second_y) ** 2


@dataclass(frozen=True, slots=True)
class _OcrTaskResult:
    observations: tuple[OcrText, ...]
    rejected: tuple[RejectedOcrText, ...]
    raw_count: int
    layout_count: int
    triggered_at: float
    started_at: float
    completed_at: float


@dataclass(frozen=True, slots=True)
class _SourceLatencyOrigin:
    pipeline_started_at: float
    first_recognized_at: float


@dataclass(frozen=True, slots=True)
class _TranslationSubmission:
    batch: TranslationBatch
    context: tuple[ContextPair, ...]
    order_group: int
    order_path: tuple[int, ...]
    queued_at: float
    pipeline_started_at: float
    first_recognized_at: float
    source_bounds: tuple[Bounds | None, ...]
    attempt: int = 1


@dataclass(frozen=True, slots=True)
class _PendingTranslationRetry:
    batch: TranslationBatch
    context: tuple[ContextPair, ...]
    order_group: int
    order_path: tuple[int, ...]
    ready_at: float
    pipeline_started_at: float
    first_recognized_at: float
    source_bounds: tuple[Bounds | None, ...]
    attempt: int


@dataclass(frozen=True, slots=True)
class _TranslationWorkerResult:
    cached_outcome: CachedTranslationOutcome
    started_at: float
    completed_at: float
    llm_seconds: float | None


@dataclass(frozen=True, slots=True)
class _CompletedTranslation:
    submission: _TranslationSubmission
    cached_outcome: CachedTranslationOutcome


def prefer_game_process_priority() -> bool:
    """Lower only this translator process so the game wins CPU contention."""
    if os.name != "nt":
        return False
    try:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.argtypes = ()
        get_current_process.restype = wintypes.HANDLE
        set_priority_class = kernel32.SetPriorityClass
        set_priority_class.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        set_priority_class.restype = wintypes.BOOL
        return bool(
            set_priority_class(get_current_process(), BELOW_NORMAL_PRIORITY_CLASS)
        )
    except (AttributeError, OSError, ValueError):
        return False


class LiveControlWindow(QWidget):
    def __init__(self, stop_callback) -> None:
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setWindowTitle(PRODUCT_NAME)
        self.setFixedWidth(520)
        self._status = QLabel("正在初始化……")
        self._status.setWordWrap(True)
        self._detail = QLabel("")
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet("color: #777;")
        self._latency = QLabel("延迟统计：等待首个 OCR 样本……")
        self._latency.setWordWrap(True)
        self._latency.setToolTip(
            "OCR 是单轮识别；稳定是首轮识别后等待入队；"
            "排队是等待翻译线程；总计从画面变化触发 OCR 到译文可显示。"
        )
        self._filter = QLabel("文字过滤：等待首个 OCR 样本……")
        self._filter.setWordWrap(True)
        self._filter.setStyleSheet("color: #777;")
        self._shrink_button = QPushButton("缩小")
        self._shrink_button.setToolTip("隐藏运行信息，只保留恢复和关闭按钮")
        self._shrink_button.clicked.connect(self.collapse)
        self._restore_button = QPushButton("恢复")
        self._restore_button.setToolTip("恢复显示运行状态、过滤和延迟信息")
        self._restore_button.clicked.connect(self.restore)
        self._restore_button.hide()
        self._stop_button = QPushButton("关闭翻译")
        self._stop_button.clicked.connect(stop_callback)
        self._diagnostic_widgets = (
            self._status,
            self._detail,
            self._filter,
            self._latency,
        )
        self._layout = QVBoxLayout(self)
        for widget in self._diagnostic_widgets:
            self._layout.addWidget(widget)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self._shrink_button)
        actions.addWidget(self._restore_button)
        actions.addWidget(self._stop_button)
        self._layout.addLayout(actions)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt callback name
        super().showEvent(event)
        if not exclude_window_from_capture(int(self.winId())):
            print("警告：Windows 未能将控制窗口排除出屏幕采集。")

    def set_status(self, status: str, detail: str = "") -> None:
        self._status.setText(status)
        self._detail.setText(detail)

    def set_latency(self, summary: str) -> None:
        self._latency.setText(summary)

    def set_filter_status(self, summary: str) -> None:
        self._filter.setText(summary)

    def collapse(self) -> None:
        """Compact the control window while keeping restore and stop actions."""
        if self._shrink_button.isHidden():
            return
        right = self.geometry().right()
        top = self.geometry().top()
        for widget in self._diagnostic_widgets:
            widget.hide()
        self._shrink_button.hide()
        self._restore_button.show()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16_777_215, 16_777_215)
        self._layout.invalidate()
        self._layout.activate()
        self.setFixedSize(self.sizeHint())
        self.move(right - self.width() + 1, top)

    def restore(self) -> None:
        """Restore the complete runtime information without moving the right edge."""
        if self._restore_button.isHidden():
            return
        right = self.geometry().right()
        top = self.geometry().top()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16_777_215, 16_777_215)
        self.setFixedWidth(520)
        for widget in self._diagnostic_widgets:
            widget.show()
        self._restore_button.hide()
        self._shrink_button.show()
        self._layout.invalidate()
        self._layout.activate()
        self.adjustSize()
        self.move(right - self.width() + 1, top)


class LiveController:
    def __init__(
        self,
        config: AppConfig,
        *,
        capture: DxcamCapture,
        ocr: PaddleOcrEngine,
        overlay: TranslationOverlay,
        control: LiveControlWindow,
        app: QApplication,
        profile: GameProfile | None = None,
        debug: bool = False,
    ) -> None:
        self._config = config
        self._capture = capture
        self._ocr = ocr
        self._overlay = overlay
        self._control = control
        self._app = app
        self._profile = profile
        self._debug = debug
        self._detector = FrameChangeDetector(config.live.change_threshold)
        self._roi_scheduler = (
            LatestFrameRoiScheduler(
                FullScreenRoiDetector(),
                min_ocr_interval_s=(
                    config.live.dynamic_roi_ocr_interval_ms / 1000
                ),
                settle_interval_s=config.live.dynamic_roi_settle_ms / 1000,
                max_coalesce_s=(
                    config.live.dynamic_roi_max_coalesce_ms / 1000
                ),
            )
            if config.live.dynamic_roi_enabled
            else None
        )
        self._roi_planner = (
            ContextualRoiPlanner() if self._roi_scheduler is not None else None
        )
        self._tracker = StableTextTracker(
            "live-zone-1",
            stable_observations=config.live.stable_observations,
            stable_seconds=config.live.stable_ms / 1000,
            clear_after_seconds=config.live.clear_after_ms / 1000,
        )
        self._text_filter = OcrTextFilter(
            config.ocr.language,
            enabled=config.ocr.text_filter_enabled,
            translate_latin=config.ocr.translate_latin,
            translate_han_only=config.ocr.translate_han_only,
        )
        self._context: deque[ContextPair] = deque(maxlen=config.live.context_pairs)
        self._revisions = RevisionRegistry()
        self._ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")
        self._translation_executor = ThreadPoolExecutor(
            max_workers=config.translation.max_concurrency,
            thread_name_prefix="translation",
        )
        self._ocr_future: Future[_OcrTaskResult] | None = None
        self._active_ocr_frame: np.ndarray | None = None
        self._active_roi_job: ScheduledRoiScan | None = None
        self._active_roi_plan: ContextualRoiPlan | None = None
        self._active_roi_anchors: tuple[TrackedText, ...] = ()
        self._translation_futures: dict[
            Future[_TranslationWorkerResult], _TranslationSubmission
        ] = {}
        self._pending_translations: list[_TranslationSubmission] = []
        self._max_pending_translation_batches = max(
            1,
            config.translation.max_concurrency
            * _PENDING_TRANSLATION_BATCHES_PER_WORKER,
        )
        self._translation_retries: list[_PendingTranslationRetry] = []
        self._completed_translations: dict[
            tuple[int, tuple[int, ...]], _CompletedTranslation
        ] = {}
        self._early_context: dict[
            tuple[int, tuple[int, ...]], tuple[ContextPair, ...]
        ] = {}
        self._next_translation_order_group = 0
        self._latest_context_order_group = -1
        self._pending_ocr_frame: np.ndarray | None = None
        self._pending_ocr_triggered_at: float | None = None
        self._latest_frame: np.ndarray | None = None
        self._source_latency_origins: dict[
            tuple[str, int], _SourceLatencyOrigin
        ] = {}
        self._latency_stats = LiveLatencyStats()
        self._last_ocr_completed = 0.0
        self._next_ocr_allowed = 0.0
        self._settle_rescan_due: float | None = None
        self._settle_rescan_triggered_at: float | None = None
        self._shutting_down = False
        self._translated_count = 0
        self._manual_hit_count = 0
        self._cache_hit_count = 0
        self._model_result_count = 0
        self._ocr_scan_count = 0
        self._roi_scan_count = 0
        self._roi_full_fallback_count = 0
        self._roi_fallback_reasons: Counter[str] = Counter()
        self._roi_fallback_peak_changed_fraction = 0.0
        self._roi_fallback_peak_candidate_coverage = 0.0
        self._roi_fallback_peak_candidate_regions = 0
        self._ocr_text_count = 0
        self._filtered_text_count = 0
        self._stale_result_count = 0
        self._translation_retry_count = 0
        self._translation_failure_count = 0
        self._translation_coalesced_count = 0
        self._translation_queue_peak = 0
        self._translation_exhausted_keys: set[tuple[str, int]] = set()
        self._cancelled_stale_count = 0
        self._reattached_result_count = 0
        self._timer = QTimer()
        self._timer.setInterval(max(10, round(1000 / config.live.change_poll_fps)))
        self._timer.timeout.connect(self._tick)
        self._control.set_latency(self._latency_stats.render())

    def start(self) -> None:
        region = self._capture.region
        profile_label = (
            f"Profile：{self._profile.display_name}"
            if self._profile is not None
            else "会话模式（不持久化）"
        )
        output_size = self._capture.output_size
        full_screen = (
            output_size is not None
            and region == (0, 0, output_size[0], output_size[1])
        )
        if full_screen and self._roi_scheduler is not None:
            region_hint = " · 整屏热图按变化区域调用 OCR"
        elif full_screen:
            region_hint = " · 当前为整屏 OCR，框选字幕区域可继续降载"
        else:
            region_hint = ""
        ocr_runtime = (
            f"{self._config.ocr.device} / {self._config.ocr.cpu_threads} 线程"
            if self._config.ocr.device == "cpu"
            else self._config.ocr.device
        )
        scheduling = (
            "实验性动态 ROI：热图 "
            f"{self._config.live.change_poll_fps} Hz / 稳定 "
            f"{self._config.live.dynamic_roi_settle_ms} ms / OCR 间隔 "
            f"{self._config.live.dynamic_roi_ocr_interval_ms} ms / 最长合并 "
            f"{self._config.live.dynamic_roi_max_coalesce_ms} ms"
            if self._roi_scheduler is not None
            else f"{self._config.live.change_poll_fps} 次/秒检测变化 · "
            f"静态复查 {self._config.live.idle_rescan_ms / 1000:g} 秒"
        )
        self._control.set_status(
            "实时翻译运行中",
            f"捕获：{self._capture.active_backend} {region} · "
            f"{scheduling} · "
            f"LLM 并发 {self._config.translation.max_concurrency} · "
            f"OCR {ocr_runtime} / 过滤"
            f"{'开' if self._config.ocr.text_filter_enabled else '关'} / 最长边 "
            f"{self._config.ocr.detection_max_side} · {profile_label}{region_hint}",
        )
        self._timer.start()

    def close(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._timer.stop()
        self._capture.close()
        self._ocr_executor.shutdown(wait=True, cancel_futures=True)
        self._translation_executor.shutdown(wait=True, cancel_futures=True)
        print(
            f"实时统计：OCR {self._ocr_scan_count} 次/识别 {self._ocr_text_count} 条，"
            f"过滤 {self._filtered_text_count} 条，覆盖 {self._translated_count} 条，"
            f"人工修订 {self._manual_hit_count} 条，缓存 {self._cache_hit_count} 条，"
            f"模型 {self._model_result_count} 条，重试 {self._translation_retry_count} 次，"
            f"最终失败 {self._translation_failure_count} 条，"
            f"合并过期排队 {self._translation_coalesced_count} 条，"
            f"排队峰值 {self._translation_queue_peak} 批，"
            f"丢弃过期译文 {self._stale_result_count} 条，"
            f"取消过期排队 {self._cancelled_stale_count} 条，"
            f"接回晚到译文 {self._reattached_result_count} 条"
        )
        if self._roi_scheduler is not None:
            print(
                f"动态 ROI：局部/回退扫描 {self._roi_scan_count} 次/"
                f"整帧回退 {self._roi_full_fallback_count} 次"
            )
            if self._roi_fallback_reasons:
                reasons = "、".join(
                    f"{reason} {count} 次"
                    for reason, count in self._roi_fallback_reasons.most_common()
                )
                print(
                    f"动态 ROI 回退诊断：{reasons}；峰值变化 "
                    f"{self._roi_fallback_peak_changed_fraction:.1%} / "
                    f"候选覆盖 {self._roi_fallback_peak_candidate_coverage:.1%} / "
                    f"候选区域 {self._roi_fallback_peak_candidate_regions} 个"
                )
        if self._ocr_scan_count:
            print("延迟统计：" + self._latency_stats.render().replace("\n", "；"))

    def _tick(self) -> None:
        if self._shutting_down:
            return
        self._collect_ocr()
        self._expire_missing_tracks(time.monotonic())
        self._collect_translations()
        self._queue_untranslated_visible_sources()
        self._dispatch_translation_work()

        try:
            frame = self._capture.latest_frame()
        except Exception as exc:
            self._fatal(f"屏幕采集失败：{exc}")
            return
        if frame is None:
            return

        self._latest_frame = frame
        now = time.monotonic()
        if self._roi_scheduler is not None:
            self._tick_dynamic_roi(frame, now)
        else:
            self._tick_legacy_ocr(frame, now)

        self._overlay.set_scene(frame, self._tracker.visible_tracks)

    def _tick_dynamic_roi(self, frame: np.ndarray, now: float) -> None:
        scheduler = self._roi_scheduler
        assert scheduler is not None
        if not scheduler.primed:
            if self._ocr_future is None and now >= self._next_ocr_allowed:
                self._submit_ocr(frame, triggered_at=now)
            return

        job = scheduler.observe(frame, now)
        if job is not None:
            self._submit_roi_ocr(job)

    def _tick_legacy_ocr(self, frame: np.ndarray, now: float) -> None:
        changed = self._detector.changed(frame)
        if changed and self._config.live.settle_rescan_ms > 0:
            self._settle_rescan_due = (
                now + self._config.live.settle_rescan_ms / 1000
            )
            self._settle_rescan_triggered_at = now
        settle_rescan_due = (
            self._settle_rescan_due is not None
            and now >= self._settle_rescan_due
        )
        idle_rescan_due = (
            self._config.live.idle_rescan_ms > 0
            and self._ocr_future is None
            and self._last_ocr_completed > 0
            and now - self._last_ocr_completed
            >= self._config.live.idle_rescan_ms / 1000
        )
        needs_stability_scan = any(
            not track.stable_emitted or track.missing_since is not None
            for track in self._tracker.visible_tracks
        ) and now - self._last_ocr_completed >= self._config.live.stable_ms / 1000

        if changed or needs_stability_scan or settle_rescan_due or idle_rescan_due:
            self._pending_ocr_frame = frame
            if changed:
                self._pending_ocr_triggered_at = now
            elif self._pending_ocr_triggered_at is None:
                self._pending_ocr_triggered_at = (
                    self._settle_rescan_triggered_at
                    if settle_rescan_due
                    else now
                )
        if settle_rescan_due:
            self._settle_rescan_due = None
            self._settle_rescan_triggered_at = None
        if (
            self._ocr_future is None
            and self._pending_ocr_frame is not None
            and now >= self._next_ocr_allowed
        ):
            pending = self._pending_ocr_frame
            triggered_at = self._pending_ocr_triggered_at
            self._pending_ocr_frame = None
            self._pending_ocr_triggered_at = None
            self._submit_ocr(pending, triggered_at=triggered_at)

    def _submit_ocr(
        self,
        frame: np.ndarray,
        *,
        triggered_at: float | None = None,
    ) -> None:
        trigger = time.monotonic() if triggered_at is None else triggered_at
        self._active_ocr_frame = frame
        self._active_roi_job = None
        self._active_roi_plan = None
        self._active_roi_anchors = ()
        self._ocr_future = self._ocr_executor.submit(
            self._run_ocr,
            frame,
            trigger,
        )

    def _submit_roi_ocr(self, job: ScheduledRoiScan) -> None:
        if self._ocr_future is not None:
            raise RuntimeError("已有 OCR 任务运行时不能提交新的 ROI 任务")
        planner = self._roi_planner
        if planner is None:
            raise RuntimeError("动态 ROI 规划器未初始化")
        anchors = self._tracker.visible_tracks
        frame_height, frame_width = job.frame.shape[:2]
        plan = planner.plan_proposal(
            job.proposal,
            anchors,
            frame_size=(frame_width, frame_height),
        )
        if not plan.regions:
            raise RuntimeError("动态 ROI 调度产生了空 OCR 计划")
        rois: tuple[OcrRoi, ...] | None = (
            None
            if plan.fallback_full_frame
            else tuple(region.roi for region in plan.regions)
        )
        self._active_ocr_frame = job.frame
        self._active_roi_job = job
        self._active_roi_plan = plan
        self._active_roi_anchors = anchors
        self._ocr_future = self._ocr_executor.submit(
            self._run_ocr,
            job.frame,
            job.observed_at_s,
            rois=rois,
        )

    def _run_ocr(
        self,
        frame: np.ndarray,
        triggered_at: float,
        *,
        rois: Sequence[OcrRoi] | None = None,
    ) -> _OcrTaskResult:
        started_at = time.monotonic()
        raw_observations = (
            tuple(self._ocr.recognize_frame(frame))
            if rois is None
            else recognize_ocr_rois(
                self._ocr,
                frame,
                rois,
                edge_margin=_ROI_INTERNAL_EDGE_MARGIN,
            )
        )
        layout_observations = merge_ocr_text_blocks(raw_observations)
        filtered = self._text_filter.apply(layout_observations)
        completed_at = time.monotonic()
        return _OcrTaskResult(
            filtered.accepted,
            filtered.rejected,
            len(raw_observations),
            len(layout_observations),
            triggered_at,
            started_at,
            completed_at,
        )

    def _collect_ocr(self) -> None:
        future = self._ocr_future
        if future is None or not future.done():
            return
        active_frame = self._active_ocr_frame
        roi_job = self._active_roi_job
        roi_plan = self._active_roi_plan
        roi_anchors = self._active_roi_anchors
        self._ocr_future = None
        self._active_ocr_frame = None
        self._active_roi_job = None
        self._active_roi_plan = None
        self._active_roi_anchors = ()
        now = time.monotonic()
        self._next_ocr_allowed = (
            now + self._config.live.ocr_cooldown_ms / 1000
        )
        # A failed OCR attempt also starts the idle retry interval. Otherwise a
        # static frame could wait forever after the settle retry is exhausted.
        self._last_ocr_completed = now
        try:
            task_result = future.result()
        except Exception as exc:
            follow_up: ScheduledRoiScan | None = None
            if roi_job is not None:
                scheduler = self._roi_scheduler
                assert scheduler is not None
                follow_up = scheduler.complete(
                    roi_job,
                    accepted=False,
                    completed_at_s=now,
                )
                retry_hint = "动态 ROI 已保留最新变化，等待空闲扫描槽重试"
            elif self._roi_scheduler is not None and not self._roi_scheduler.primed:
                self._next_ocr_allowed = max(
                    self._next_ocr_allowed,
                    now + _ROI_INITIAL_RETRY_SECONDS,
                )
                retry_hint = "首次全帧 OCR 将在 1 秒后重试"
            else:
                retry_hint = "等待画面变化或定时复查后重试"
            self._control.set_status(f"OCR 暂时失败，{retry_hint}", str(exc))
            print(f"OCR 错误：{exc}", file=sys.stderr)
            if follow_up is not None:
                self._submit_roi_ocr(follow_up)
            return

        observations = task_result.observations
        contextual_update = None
        if roi_plan is not None:
            contextual_update = build_contextual_ocr_update(
                roi_plan,
                observations,
                roi_anchors,
            )
            tracker_observations = contextual_update.observations
            self._roi_scan_count += 1
            if roi_plan.fallback_full_frame:
                self._roi_full_fallback_count += 1
                self._roi_fallback_reasons[roi_plan.reason] += 1
                if roi_job is not None:
                    self._roi_fallback_peak_changed_fraction = max(
                        self._roi_fallback_peak_changed_fraction,
                        roi_job.proposal.changed_fraction,
                    )
                self._roi_fallback_peak_candidate_coverage = max(
                    self._roi_fallback_peak_candidate_coverage,
                    roi_plan.candidate_coverage_fraction,
                )
                self._roi_fallback_peak_candidate_regions = max(
                    self._roi_fallback_peak_candidate_regions,
                    roi_plan.candidate_region_count,
                )
        else:
            tracker_observations = observations
        self._ocr_text_count += task_result.raw_count
        self._filtered_text_count += len(task_result.rejected)
        set_filter_status = getattr(self._control, "set_filter_status", None)
        if callable(set_filter_status):
            reason_counts = Counter(item.reason for item in task_result.rejected)
            reason_detail = "、".join(
                f"{reason} {count}" for reason, count in reason_counts.items()
            )
            reason_suffix = f"（{reason_detail}）" if reason_detail else ""
            if task_result.layout_count == task_result.raw_count:
                scan_summary = f"本轮识别 {task_result.raw_count} 条"
            else:
                scan_summary = (
                    f"本轮检测 {task_result.raw_count} 框，"
                    f"版面整理为 {task_result.layout_count} 块"
                )
            set_filter_status(
                f"文字过滤：{scan_summary}，保留 {len(observations)} 条，"
                f"过滤 {len(task_result.rejected)} 条{reason_suffix} · "
                f"累计过滤 {self._filtered_text_count} 条"
            )
        ocr_seconds = max(0.0, task_result.completed_at - task_result.started_at)
        self._latency_stats.record_ocr(ocr_seconds)
        self._refresh_latency_display()
        self._ocr_scan_count += 1
        if self._debug:
            print(f"耗时：OCR {ocr_seconds:.3f}s")
            layout_detail = (
                ""
                if task_result.layout_count == task_result.raw_count
                else f"，版面整理 {task_result.layout_count} 块"
            )
            print(
                f"OCR 过滤：识别 {task_result.raw_count} 条{layout_detail}，"
                f"保留 {len(observations)} 条，过滤 {len(task_result.rejected)} 条"
            )
            if task_result.rejected:
                print(
                    "已过滤："
                    + " | ".join(
                        f"{item.observation.text}（{item.reason}）"
                        for item in task_result.rejected
                    )
                )
            if observations:
                print("OCR 保留：" + " | ".join(item.text for item in observations))
            if contextual_update is not None:
                assert roi_job is not None
                target_count = sum(
                    len(group.targets)
                    for group in contextual_update.context_groups
                )
                print(
                    f"动态 ROI：{roi_plan.reason} / 扫描覆盖 "
                    f"{roi_plan.coverage_fraction:.1%} / "
                    f"变化 {roi_job.proposal.changed_fraction:.1%} / "
                    f"候选覆盖 {roi_plan.candidate_coverage_fraction:.1%} / "
                    f"候选区域 {roi_plan.candidate_region_count} / "
                    f"影响 {roi_plan.affected_track_count} 条 / "
                    f"更新 {len(tracker_observations)} 条 / "
                    f"target {target_count} 条"
                )
        previous_keys = {
            (track.track_id, track.revision) for track in self._tracker.visible_tracks
        }
        if contextual_update is not None and not roi_plan.fallback_full_frame:
            update = self._tracker.observe_partial(
                tracker_observations,
                now,
                replace_track_ids=contextual_update.replace_track_ids,
            )
        else:
            update = self._tracker.observe(tracker_observations, now)
        current_keys: set[tuple[str, int]] = set()
        for track in update.visible_tracks:
            key = (track.track_id, track.revision)
            current_keys.add(key)
            if key not in previous_keys or key not in self._source_latency_origins:
                self._source_latency_origins[key] = _SourceLatencyOrigin(
                    pipeline_started_at=task_result.triggered_at,
                    first_recognized_at=task_result.completed_at,
                )
        self._source_latency_origins = {
            key: origin
            for key, origin in self._source_latency_origins.items()
            if key in current_keys
        }
        if update.stable_sources:
            if self._debug:
                print("稳定字幕：" + " | ".join(item.text for item in update.stable_sources))
            self._submit_translations(update.stable_sources)

        follow_up = None
        scheduler = self._roi_scheduler
        if scheduler is not None:
            if roi_job is not None:
                follow_up = scheduler.complete(
                    roi_job,
                    accepted=True,
                    completed_at_s=now,
                )
            elif not scheduler.primed:
                if active_frame is None:
                    raise RuntimeError("首次动态 ROI OCR 缺少基准帧")
                scheduler.prime(active_frame, now)
        if follow_up is not None:
            self._submit_roi_ocr(follow_up)

    def _submit_translations(self, sources: Sequence[SourceText]) -> None:
        if not sources:
            return
        batch_size = self._config.live.max_batch_size
        visible_by_key = {
            (track.track_id, track.revision): track
            for track in self._tracker.visible_tracks
        }
        ordered_sources = tuple(
            sorted(
                sources,
                key=lambda source: (
                    (
                        visible_by_key[(source.track_id, source.revision)].bounds[1],
                        visible_by_key[(source.track_id, source.revision)].bounds[0],
                    )
                    if (source.track_id, source.revision) in visible_by_key
                    else (sys.maxsize, sys.maxsize)
                ),
            )
        )
        queued_sources = self._coalesce_pending_translations(
            ordered_sources,
            visible_by_key,
        )
        self._prune_obsolete_pending_translations()
        self._dispatch_translation_work()
        scheduled_keys = self._scheduled_translation_keys()
        queued_sources = tuple(
            source
            for source in queued_sources
            if (source.track_id, source.revision) not in scheduled_keys
            and (source.track_id, source.revision)
            not in self._translation_exhausted_keys
        )
        if not queued_sources:
            self._dispatch_translation_work()
            return

        context = self._context_snapshot()
        order_group = self._next_translation_order_group
        self._next_translation_order_group += 1
        admission_limit = self._max_pending_translation_batches + max(
            0,
            self._config.translation.max_concurrency
            - len(self._translation_futures),
        )
        for batch_index, offset in enumerate(range(0, len(queued_sources), batch_size)):
            if len(self._pending_translations) >= admission_limit:
                break
            batch = TranslationBatch(
                tuple(queued_sources[offset : offset + batch_size])
            )
            origins = tuple(
                self._source_latency_origins.get((source.track_id, source.revision))
                for source in batch.items
            )
            known_origins = tuple(origin for origin in origins if origin is not None)
            now = time.monotonic()
            pipeline_started_at = (
                min(origin.pipeline_started_at for origin in known_origins)
                if known_origins
                else now
            )
            first_recognized_at = (
                min(origin.first_recognized_at for origin in known_origins)
                if known_origins
                else now
            )
            source_bounds = tuple(
                (
                    visible_by_key[(source.track_id, source.revision)].bounds
                    if (source.track_id, source.revision) in visible_by_key
                    else None
                )
                for source in batch.items
            )
            queued_at = time.monotonic()
            self._pending_translations.append(
                _TranslationSubmission(
                    batch,
                    context,
                    order_group,
                    (batch_index,),
                    queued_at,
                    pipeline_started_at,
                    first_recognized_at,
                    source_bounds,
                    1,
                )
            )
        self._dispatch_translation_work()
        self._translation_queue_peak = max(
            self._translation_queue_peak,
            len(self._pending_translations),
        )

    def _coalesce_pending_translations(
        self,
        sources: Sequence[SourceText],
        visible_by_key: dict[tuple[str, int], TrackedText],
    ) -> tuple[SourceText, ...]:
        replacements = {source.track_id: source for source in sources}
        if not replacements or not self._pending_translations:
            return tuple(sources)

        coalesced: list[_TranslationSubmission] = []
        for submission in self._pending_translations:
            items: list[SourceText] = []
            bounds: list[Bounds | None] = []
            changed = False
            for source, source_bounds in zip(
                submission.batch.items,
                submission.source_bounds,
                strict=True,
            ):
                replacement = replacements.pop(source.track_id, None)
                if replacement is None:
                    items.append(source)
                    bounds.append(source_bounds)
                    continue
                items.append(replacement)
                track = visible_by_key.get((replacement.track_id, replacement.revision))
                bounds.append(track.bounds if track is not None else source_bounds)
                if replacement.revision != source.revision or replacement.text != source.text:
                    self._translation_coalesced_count += 1
                    changed = True
            coalesced.append(
                replace(
                    submission,
                    batch=TranslationBatch(tuple(items)),
                    source_bounds=tuple(bounds),
                )
                if changed
                else submission
            )
        self._pending_translations = coalesced
        return tuple(
            source for source in sources if source.track_id in replacements
        )

    def _prune_obsolete_pending_translations(self) -> None:
        current: list[_TranslationSubmission] = []
        for submission in self._pending_translations:
            batch, source_bounds = self._rebind_visible_sources(
                submission.batch,
                submission.source_bounds,
            )
            if batch is None:
                self._cancelled_stale_count += len(submission.batch.items)
                continue
            removed = len(submission.batch.items) - len(batch.items)
            self._cancelled_stale_count += removed
            current.append(
                replace(
                    submission,
                    batch=batch,
                    source_bounds=source_bounds,
                )
            )
        self._pending_translations = current

    def _scheduled_translation_keys(self) -> set[tuple[str, int]]:
        scheduled: set[tuple[str, int]] = set()
        for submission in self._pending_translations:
            scheduled.update(
                (source.track_id, source.revision) for source in submission.batch.items
            )
        for submission in self._translation_futures.values():
            scheduled.update(
                (source.track_id, source.revision) for source in submission.batch.items
            )
        for retry in self._translation_retries:
            scheduled.update(
                (source.track_id, source.revision) for source in retry.batch.items
            )
        for completed in self._completed_translations.values():
            scheduled.update(
                (source.track_id, source.revision)
                for source in completed.submission.batch.items
            )
        return scheduled

    def _queue_untranslated_visible_sources(self) -> None:
        visible = self._tracker.visible_tracks
        visible_keys = {
            (track.track_id, track.revision) for track in visible
        }
        self._translation_exhausted_keys.intersection_update(visible_keys)
        scheduled = self._scheduled_translation_keys()
        deferred = tuple(
            track.source(self._tracker.zone_id)
            for track in visible
            if track.stable_emitted
            and track.translated_text is None
            and (track.track_id, track.revision) not in scheduled
            and (track.track_id, track.revision)
            not in self._translation_exhausted_keys
        )
        if deferred:
            self._submit_translations(deferred)

    def _dispatch_translation_work(self) -> None:
        self._dispatch_ready_translation_retries()
        self._dispatch_pending_translations()

    def _dispatch_pending_translations(self) -> None:
        concurrency = self._config.translation.max_concurrency
        while self._pending_translations and len(self._translation_futures) < concurrency:
            submission = self._pending_translations.pop(0)
            batch, source_bounds = self._rebind_visible_sources(
                submission.batch,
                submission.source_bounds,
                skip_active=True,
            )
            if batch is None:
                self._cancelled_stale_count += len(submission.batch.items)
                continue
            self._start_translation_submission(
                replace(
                    submission,
                    batch=batch,
                    source_bounds=source_bounds,
                )
            )

    def _context_snapshot(self) -> tuple[ContextPair, ...]:
        limit = self._config.live.context_pairs
        if limit <= 0:
            return ()
        combined = list(self._context)
        for (order_group, _), pairs in self._early_context.items():
            if order_group >= self._latest_context_order_group:
                combined.extend(pairs)
        return tuple(combined[-limit:])

    def _start_translation_submission(
        self,
        submission: _TranslationSubmission,
    ) -> None:
        future = self._translation_executor.submit(
            self._translate_blocking_timed,
            submission.batch,
            submission.context,
        )
        self._translation_futures[future] = submission

    def _translate_blocking(
        self,
        batch: TranslationBatch,
        context: tuple[ContextPair, ...],
    ) -> CachedTranslationOutcome:
        return self._translate_blocking_timed(batch, context).cached_outcome

    def _translate_blocking_timed(
        self,
        batch: TranslationBatch,
        context: tuple[ContextPair, ...],
    ) -> _TranslationWorkerResult:
        started_at = time.monotonic()

        async def translate() -> tuple[CachedTranslationOutcome, float | None]:
            async with OpenAICompatibleTransport(self._config.translation) as transport:
                prompt_builder = HyMtPromptBuilder(
                    self._config.translation.target_language
                )
                service = TranslationService(
                    transport,
                    prompt_builder=prompt_builder,
                    revisions=self._revisions,
                )
                cached_service = CachedTranslationService(
                    service,
                    profile=self._profile,
                    source_language=self._config.ocr.language,
                    target_language=self._config.translation.target_language,
                    model=self._config.translation.model,
                    prompt_version=prompt_builder.prompt_version,
                )
                cached_outcome = await cached_service.translate(batch, context=context)
                durations = transport.completion_durations
                return cached_outcome, (sum(durations) if durations else None)

        cached_outcome, llm_seconds = asyncio.run(translate())
        return _TranslationWorkerResult(
            cached_outcome,
            started_at,
            time.monotonic(),
            llm_seconds,
        )

    def _collect_translations(self) -> None:
        self._cancel_obsolete_translation_futures()
        for future in tuple(self._translation_futures):
            if not future.done():
                continue
            submission = self._translation_futures.pop(future)
            try:
                worker_result = future.result()
            except Exception as exc:
                retry_scheduled = self._handle_translation_failure(submission, exc)
                if retry_scheduled:
                    if isinstance(exc, TranslationProtocolError):
                        status = "翻译格式异常，正在自动恢复"
                        error_label = "翻译协议偏差，正在自动恢复"
                    else:
                        status = "翻译请求失败，正在自动重试"
                        error_label = "翻译请求异常，正在自动重试"
                else:
                    status = "翻译服务异常，屏幕保留原文"
                    error_label = "翻译错误"
                self._control.set_status(status, str(exc))
                print(f"{error_label}：{exc}", file=sys.stderr)
                continue

            cached_outcome = worker_result.cached_outcome
            stability_seconds = max(
                0.0, submission.queued_at - submission.first_recognized_at
            )
            queue_seconds = max(
                0.0, worker_result.started_at - submission.queued_at
            )
            total_seconds = max(
                0.0, time.monotonic() - submission.pipeline_started_at
            )
            self._latency_stats.record_translation(
                stability_seconds=stability_seconds,
                queue_seconds=queue_seconds,
                llm_seconds=worker_result.llm_seconds,
                total_seconds=total_seconds,
                batch_size=len(submission.batch.items),
            )
            self._refresh_latency_display()
            if self._debug:
                llm_label = (
                    f"{worker_result.llm_seconds:.3f}s"
                    if worker_result.llm_seconds is not None
                    else "缓存命中"
                )
                print(
                    f"耗时：稳定 {stability_seconds:.3f}s · "
                    f"翻译排队 {queue_seconds:.3f}s · LLM {llm_label} · "
                    f"总计 {total_seconds:.3f}s · 批次 {len(submission.batch.items)} 条"
                )

            order_key = (submission.order_group, submission.order_path)
            accepted_with_origins, _ = self._accept_current_results(
                submission,
                cached_outcome,
            )
            self._early_context[order_key] = tuple(
                ContextPair(result.source.text, result.translated_text)
                for result, _ in accepted_with_origins
            )
            self._completed_translations[order_key] = _CompletedTranslation(
                submission,
                cached_outcome,
            )

        self._publish_ready_translations()
        self._dispatch_translation_work()

    def _publish_ready_translations(self) -> None:
        scene_changed = False
        while True:
            order_key = self._next_publishable_translation_key()
            if order_key is None:
                break
            completed = self._completed_translations.pop(order_key)
            self._early_context.pop(order_key, None)
            submission = completed.submission
            cached_outcome = completed.cached_outcome
            outcome = cached_outcome.outcome
            accepted_with_origins, reattached = self._accept_current_results(
                submission,
                cached_outcome,
            )
            accepted = tuple(result for result, _ in accepted_with_origins)
            self._stale_result_count += (
                len(outcome.discarded_stale)
                + len(outcome.results)
                - len(accepted)
            )
            self._reattached_result_count += reattached
            self._tracker.apply_translations(accepted)
            if accepted and submission.order_group >= self._latest_context_order_group:
                for result in accepted:
                    self._context.append(
                        ContextPair(result.source.text, result.translated_text)
                    )
                self._latest_context_order_group = submission.order_group
            for _, origin in accepted_with_origins:
                if origin == "manual":
                    self._manual_hit_count += 1
                elif origin == "automatic":
                    self._cache_hit_count += 1
                else:
                    self._model_result_count += 1
            if self._debug and accepted_with_origins:
                origin_labels = {
                    "manual": "人工修订",
                    "automatic": "缓存",
                    "model": "模型",
                }
                print(
                    "翻译："
                    + " | ".join(
                        f"[{origin_labels[origin]}] "
                        f"{result.source.text} -> {result.translated_text}"
                        for result, origin in accepted_with_origins
                    )
                )
            self._translated_count += len(accepted)
            if accepted:
                profile_label = (
                    f" · Profile {self._profile.profile_id}"
                    if self._profile is not None
                    else ""
                )
                self._control.set_status(
                    "实时翻译运行中",
                    f"已覆盖 {self._translated_count} 条 · "
                    f"当前上下文 {len(self._context_snapshot())} 条{profile_label}",
                )
                scene_changed = True
        if scene_changed and self._latest_frame is not None:
            self._overlay.set_scene(self._latest_frame, self._tracker.visible_tracks)

    def _next_publishable_translation_key(
        self,
    ) -> tuple[int, tuple[int, ...]] | None:
        """Return a buffered result whose earlier screen batches are resolved.

        Completed results become temporary prompt context immediately, while
        publication remains ordered only inside one OCR update.  A slow stale
        update therefore cannot block text found by a later OCR pass.
        """
        first_path_by_group: dict[int, tuple[int, ...]] = {}
        for submission in self._pending_translations:
            current = first_path_by_group.get(submission.order_group)
            if current is None or submission.order_path < current:
                first_path_by_group[submission.order_group] = submission.order_path
        for submission in self._translation_futures.values():
            current = first_path_by_group.get(submission.order_group)
            if current is None or submission.order_path < current:
                first_path_by_group[submission.order_group] = submission.order_path
        for retry in self._translation_retries:
            current = first_path_by_group.get(retry.order_group)
            if current is None or retry.order_path < current:
                first_path_by_group[retry.order_group] = retry.order_path
        for order_group, order_path in self._completed_translations:
            current = first_path_by_group.get(order_group)
            if current is None or order_path < current:
                first_path_by_group[order_group] = order_path

        candidates = [
            order_key
            for order_key in self._completed_translations
            if order_key[1] == first_path_by_group.get(order_key[0])
        ]
        if not candidates:
            return None
        return min(candidates)

    def _expire_missing_tracks(self, now: float) -> None:
        expired = self._tracker.expire_missing(now)
        if not expired.removed_track_ids:
            return
        current_keys = {
            (track.track_id, track.revision) for track in expired.visible_tracks
        }
        self._source_latency_origins = {
            key: origin
            for key, origin in self._source_latency_origins.items()
            if key in current_keys
        }

    def _cancel_obsolete_translation_futures(self) -> None:
        visible = self._tracker.visible_tracks
        for future, submission in tuple(self._translation_futures.items()):
            if future.done() or future.running():
                continue
            relevant = any(
                self._matching_visible_track(source, bounds, visible, set()) is not None
                for source, bounds in zip(
                    submission.batch.items,
                    submission.source_bounds,
                    strict=True,
                )
            )
            if relevant or not future.cancel():
                continue
            self._translation_futures.pop(future, None)
            self._cancelled_stale_count += len(submission.batch.items)

    def _handle_translation_failure(
        self,
        submission: _TranslationSubmission,
        error: Exception,
    ) -> bool:
        if not isinstance(error, (TranslationProtocolError, TranslationTransportError)):
            self._translation_failure_count += len(submission.batch.items)
            self._translation_exhausted_keys.update(
                (source.track_id, source.revision) for source in submission.batch.items
            )
            return False

        rebound_batch, rebound_bounds = self._rebind_visible_sources(
            submission.batch,
            submission.source_bounds,
        )
        if rebound_batch is None:
            self._cancelled_stale_count += len(submission.batch.items)
            return False

        if isinstance(error, TranslationProtocolError) and len(rebound_batch.items) > 1:
            midpoint = len(rebound_batch.items) // 2
            slices = (slice(0, midpoint), slice(midpoint, None))
            for child_index, item_slice in enumerate(slices):
                self._schedule_translation_retry(
                    TranslationBatch(rebound_batch.items[item_slice]),
                    context=submission.context,
                    order_group=submission.order_group,
                    order_path=submission.order_path + (child_index,),
                    pipeline_started_at=submission.pipeline_started_at,
                    first_recognized_at=submission.first_recognized_at,
                    source_bounds=rebound_bounds[item_slice],
                    attempt=1,
                    delay_seconds=_TRANSLATION_RETRY_BASE_SECONDS,
                )
            return True

        if (
            isinstance(error, TranslationTransportError)
            and "HTTP 500" in str(error)
            and submission.attempt == 2
            and len(rebound_batch.items) > 1
        ):
            midpoint = len(rebound_batch.items) // 2
            slices = (slice(0, midpoint), slice(midpoint, None))
            for child_index, item_slice in enumerate(slices):
                self._schedule_translation_retry(
                    TranslationBatch(rebound_batch.items[item_slice]),
                    context=submission.context,
                    order_group=submission.order_group,
                    order_path=submission.order_path + (child_index,),
                    pipeline_started_at=submission.pipeline_started_at,
                    first_recognized_at=submission.first_recognized_at,
                    source_bounds=rebound_bounds[item_slice],
                    attempt=_MAX_TRANSLATION_ATTEMPTS,
                    delay_seconds=_TRANSLATION_RETRY_BASE_SECONDS,
                )
            return True

        if submission.attempt >= _MAX_TRANSLATION_ATTEMPTS:
            self._translation_failure_count += len(rebound_batch.items)
            self._translation_exhausted_keys.update(
                (source.track_id, source.revision) for source in rebound_batch.items
            )
            return False

        delay = _TRANSLATION_RETRY_BASE_SECONDS * (2 ** (submission.attempt - 1))
        self._schedule_translation_retry(
            rebound_batch,
            context=submission.context,
            order_group=submission.order_group,
            order_path=submission.order_path,
            pipeline_started_at=submission.pipeline_started_at,
            first_recognized_at=submission.first_recognized_at,
            source_bounds=rebound_bounds,
            attempt=submission.attempt + 1,
            delay_seconds=delay,
        )
        return True

    def _schedule_translation_retry(
        self,
        batch: TranslationBatch,
        *,
        context: tuple[ContextPair, ...],
        order_group: int,
        order_path: tuple[int, ...],
        pipeline_started_at: float,
        first_recognized_at: float,
        source_bounds: tuple[Bounds | None, ...],
        attempt: int,
        delay_seconds: float,
    ) -> None:
        self._translation_retries.append(
            _PendingTranslationRetry(
                batch,
                context,
                order_group,
                order_path,
                time.monotonic() + delay_seconds,
                pipeline_started_at,
                first_recognized_at,
                source_bounds,
                attempt,
            )
        )
        self._translation_retry_count += 1

    def _submit_ready_translation_retries(self) -> None:
        self._dispatch_translation_work()

    def _dispatch_ready_translation_retries(self) -> None:
        now = time.monotonic()
        concurrency = self._config.translation.max_concurrency
        while len(self._translation_futures) < concurrency:
            retry_index = next(
                (
                    index
                    for index, item in enumerate(self._translation_retries)
                    if item.ready_at <= now
                ),
                None,
            )
            if retry_index is None:
                break
            retry = self._translation_retries.pop(retry_index)
            batch, source_bounds = self._rebind_visible_sources(
                retry.batch,
                retry.source_bounds,
                skip_active=True,
            )
            if batch is None:
                self._cancelled_stale_count += len(retry.batch.items)
                continue
            self._start_translation_submission(
                _TranslationSubmission(
                    batch,
                    retry.context,
                    retry.order_group,
                    retry.order_path,
                    now,
                    retry.pipeline_started_at,
                    retry.first_recognized_at,
                    source_bounds,
                    retry.attempt,
                )
            )

    def _rebind_visible_sources(
        self,
        batch: TranslationBatch,
        source_bounds: tuple[Bounds | None, ...],
        *,
        skip_active: bool = False,
    ) -> tuple[TranslationBatch | None, tuple[Bounds | None, ...]]:
        visible = self._tracker.visible_tracks
        active_keys = (
            {
                (source.track_id, source.revision)
                for submission in self._translation_futures.values()
                for source in submission.batch.items
            }
            if skip_active
            else set()
        )
        assigned: set[tuple[str, int]] = set()
        rebound: list[SourceText] = []
        rebound_bounds: list[Bounds | None] = []
        for source, bounds in zip(batch.items, source_bounds, strict=True):
            track = self._matching_visible_track(source, bounds, visible, assigned)
            if track is None:
                continue
            key = (track.track_id, track.revision)
            if key in active_keys or (skip_active and track.translated_text is not None):
                continue
            assigned.add(key)
            rebound.append(track.source(self._tracker.zone_id))
            rebound_bounds.append(track.bounds)
        if not rebound:
            return None, ()
        return TranslationBatch(tuple(rebound)), tuple(rebound_bounds)

    def _accept_current_results(
        self,
        submission: _TranslationSubmission,
        cached_outcome: CachedTranslationOutcome,
    ) -> tuple[tuple[tuple[TranslationResult, str], ...], int]:
        visible = self._tracker.visible_tracks
        bounds_by_key = {
            (source.track_id, source.revision): bounds
            for source, bounds in zip(
                submission.batch.items,
                submission.source_bounds,
                strict=True,
            )
        }
        assigned: set[tuple[str, int]] = set()
        accepted: list[tuple[TranslationResult, str]] = []
        reattached = 0
        for result, origin in zip(
            cached_outcome.outcome.results,
            cached_outcome.origins,
            strict=True,
        ):
            source_key = (result.source.track_id, result.source.revision)
            track = self._matching_visible_track(
                result.source,
                bounds_by_key.get(source_key),
                visible,
                assigned,
            )
            if track is None:
                continue
            track_key = (track.track_id, track.revision)
            assigned.add(track_key)
            if track_key == source_key:
                accepted_result = result
            else:
                accepted_result = TranslationResult(
                    track.source(self._tracker.zone_id),
                    result.translated_text,
                )
                reattached += 1
            accepted.append((accepted_result, origin))
        return tuple(accepted), reattached

    @staticmethod
    def _matching_visible_track(
        source: SourceText,
        source_bounds: Bounds | None,
        visible: Sequence[TrackedText],
        assigned: set[tuple[str, int]],
    ) -> TrackedText | None:
        source_key = (source.track_id, source.revision)
        for track in visible:
            track_key = (track.track_id, track.revision)
            if track_key == source_key and track_key not in assigned:
                return track

        normalized = normalize_text(source.text)
        candidates = [
            track
            for track in visible
            if track.text == normalized
            and (track.track_id, track.revision) not in assigned
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda track: (
                track.translated_text is not None,
                _bounds_distance_squared(source_bounds, track.bounds),
                track.bounds[1],
                track.bounds[0],
            ),
        )

    def _refresh_latency_display(self) -> None:
        self._control.set_latency(self._latency_stats.render())

    def _fatal(self, message: str) -> None:
        print(message, file=sys.stderr)
        self._control.set_status("实时翻译已停止", message)
        self._timer.stop()
        self._capture.close()


def _overlay_geometry(app: QApplication, capture: DxcamCapture, config: AppConfig):
    screens = app.screens()
    if config.live.monitor_index >= len(screens):
        raise RuntimeError(
            f"Qt 只发现 {len(screens)} 个显示器，无法选择 monitor_index={config.live.monitor_index}"
        )
    if capture.output_size is None or capture.region is None:
        raise RuntimeError("采集器没有返回显示器尺寸或区域")
    screen = screens[config.live.monitor_index]
    geometry = screen.geometry()
    output_width, output_height = capture.output_size
    left, top, right, bottom = capture.region
    scale_x = geometry.width() / output_width
    scale_y = geometry.height() / output_height
    return screen, (
        geometry.x() + round(left * scale_x),
        geometry.y() + round(top * scale_y),
        max(1, round((right - left) * scale_x)),
        max(1, round((bottom - top) * scale_y)),
    )


def run_live(
    config: AppConfig,
    config_path: Path,
    *,
    duration_seconds: float | None = None,
    debug_border: bool = False,
    test_source: Path | None = None,
    profile: GameProfile | None = None,
) -> int:
    if not prefer_game_process_priority():
        print("警告：未能将翻译器进程调整为低于游戏的 CPU 优先级。")
    _live_message("creating QApplication")
    app = QApplication.instance() or QApplication([LIVE_PROCESS_NAME])
    app.setApplicationName(PRODUCT_NAME)
    app.setApplicationDisplayName(PRODUCT_NAME)
    app.setQuitOnLastWindowClosed(False)

    _live_message(f"initializing OCR on {config.ocr.device}")
    ocr = PaddleOcrEngine(
        language=config.ocr.language,
        min_score=config.ocr.min_score,
        cache_dir=(config_path.resolve().parent / config.ocr.cache_dir),
        detection_model=config.ocr.detection_model,
        recognition_model=config.ocr.recognition_model,
        model_source=config.ocr.model_source,
        device=config.ocr.device,
        cpu_threads=config.ocr.cpu_threads,
        detection_max_side=config.ocr.detection_max_side,
    )
    _live_message(f"OCR ready: {ocr.runtime_description}")
    _live_message(
        f"starting capture: monitor={config.live.monitor_index} "
        f"region={config.live.left},{config.live.top},"
        f"{config.live.width},{config.live.height}"
    )
    capture = DxcamCapture(
        monitor_index=config.live.monitor_index,
        region_spec=(
            config.live.left,
            config.live.top,
            config.live.width,
            config.live.height,
        ),
        target_fps=config.live.capture_fps,
        backend=config.live.capture_backend,
    )
    capture.start()
    _live_message(f"capture ready: backend={capture.active_backend}")
    screen, geometry = _overlay_geometry(app, capture, config)
    test_window = None
    if test_source is not None:
        from PySide6.QtGui import QPixmap

        source_path = test_source.resolve()
        pixmap = QPixmap(str(source_path))
        if pixmap.isNull():
            capture.close()
            raise FileNotFoundError(f"无法加载实时测试图片：{source_path}")
        test_window = QLabel()
        test_window.setWindowTitle(f"{PRODUCT_NAME} Live Test Source")
        test_window.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        scaled = pixmap.scaled(
            geometry[2],
            geometry[3],
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        test_window.setPixmap(scaled)
        test_window.setFixedSize(scaled.size())
        test_window.move(geometry[0], geometry[1])
        test_window.show()
    overlay = TranslationOverlay(
        geometry=geometry,
        style=OverlayStyle(
            blur_radius=config.preview.blur_radius,
            overlay_opacity=config.preview.overlay_opacity,
            font_path=config.preview.font_path,
        ),
        debug_border=debug_border,
    )
    control = LiveControlWindow(app.quit)
    screen_geometry = screen.availableGeometry()
    control.adjustSize()
    control.move(
        screen_geometry.right() - control.width() - 20,
        screen_geometry.top() + 20,
    )
    controller = LiveController(
        config,
        capture=capture,
        ocr=ocr,
        overlay=overlay,
        control=control,
        app=app,
        profile=profile,
        debug=debug_border,
    )
    app.aboutToQuit.connect(controller.close)
    _live_message("showing overlay and control windows")
    overlay.show()
    control.show()
    controller.start()
    _live_message("ready")
    if duration_seconds is not None:
        if duration_seconds <= 0:
            raise ValueError("--duration 必须大于 0")
        QTimer.singleShot(round(duration_seconds * 1000), app.quit)
    exit_code = app.exec()
    if test_window is not None:
        test_window.close()
    return exit_code

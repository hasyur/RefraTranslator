from __future__ import annotations

import asyncio
import ctypes
import os
import sys
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Sequence

import numpy as np

from game_screen_translator.capture.dxcam_capture import DxcamCapture
from game_screen_translator.config import AppConfig
from game_screen_translator.domain import (
    ContextPair,
    RevisionRegistry,
    SourceText,
    TranslationBatch,
)
from game_screen_translator.live.change_detector import FrameChangeDetector
from game_screen_translator.live.tracker import StableTextTracker
from game_screen_translator.ocr.paddle import PaddleOcrEngine
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
from game_screen_translator.translation.hy_mt import HyMtPromptBuilder
from game_screen_translator.translation.service import TranslationService
from game_screen_translator.translation.transport import OpenAICompatibleTransport

try:
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import (
        QApplication,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - exercised only without GUI extra
    raise RuntimeError("尚未安装 GUI 依赖。请运行：.\\bootstrap.ps1 -WithGui") from exc


BELOW_NORMAL_PRIORITY_CLASS = 0x00004000


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
        self.setWindowTitle("游戏屏幕翻译器")
        self.setFixedWidth(390)
        self._status = QLabel("正在初始化……")
        self._status.setWordWrap(True)
        self._detail = QLabel("")
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet("color: #777;")
        stop_button = QPushButton("停止翻译")
        stop_button.clicked.connect(stop_callback)
        layout = QVBoxLayout(self)
        layout.addWidget(self._status)
        layout.addWidget(self._detail)
        layout.addWidget(stop_button)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt callback name
        super().showEvent(event)
        if not exclude_window_from_capture(int(self.winId())):
            print("警告：Windows 未能将控制窗口排除出屏幕采集。")

    def set_status(self, status: str, detail: str = "") -> None:
        self._status.setText(status)
        self._detail.setText(detail)


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
        self._tracker = StableTextTracker(
            "live-zone-1",
            stable_observations=config.live.stable_observations,
            stable_seconds=config.live.stable_ms / 1000,
            clear_after_seconds=config.live.clear_after_ms / 1000,
        )
        self._context: deque[ContextPair] = deque(maxlen=config.live.context_pairs)
        self._revisions = RevisionRegistry()
        self._ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr")
        self._translation_executor = ThreadPoolExecutor(
            max_workers=config.translation.max_concurrency,
            thread_name_prefix="translation",
        )
        self._ocr_future: Future[tuple[OcrText, ...]] | None = None
        self._translation_futures: dict[
            Future[CachedTranslationOutcome], TranslationBatch
        ] = {}
        self._pending_ocr_frame: np.ndarray | None = None
        self._latest_frame: np.ndarray | None = None
        self._last_ocr_completed = 0.0
        self._next_ocr_allowed = 0.0
        self._shutting_down = False
        self._translated_count = 0
        self._manual_hit_count = 0
        self._cache_hit_count = 0
        self._model_result_count = 0
        self._ocr_scan_count = 0
        self._stale_result_count = 0
        self._timer = QTimer()
        self._timer.setInterval(max(10, round(1000 / config.live.change_poll_fps)))
        self._timer.timeout.connect(self._tick)

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
        region_hint = " · 当前为整屏 OCR，框选字幕区域可继续降载" if full_screen else ""
        self._control.set_status(
            "实时翻译运行中",
            f"捕获：{self._capture.active_backend} {region} · "
            f"{self._config.live.change_poll_fps} 次/秒检测变化 · "
            f"OCR {self._config.ocr.cpu_threads} 线程 / 最长边 "
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
            f"实时统计：OCR {self._ocr_scan_count} 次，覆盖 {self._translated_count} 条，"
            f"人工修订 {self._manual_hit_count} 条，缓存 {self._cache_hit_count} 条，"
            f"模型 {self._model_result_count} 条，丢弃过期译文 {self._stale_result_count} 条"
        )

    def _tick(self) -> None:
        if self._shutting_down:
            return
        self._collect_ocr()
        self._collect_translations()

        try:
            frame = self._capture.latest_frame()
        except Exception as exc:
            self._fatal(f"屏幕采集失败：{exc}")
            return
        if frame is None:
            return

        self._latest_frame = frame
        now = time.monotonic()
        changed = self._detector.changed(frame)
        needs_stability_scan = any(
            not track.stable_emitted for track in self._tracker.visible_tracks
        ) and now - self._last_ocr_completed >= self._config.live.stable_ms / 1000

        if changed or needs_stability_scan:
            self._pending_ocr_frame = frame
        if (
            self._ocr_future is None
            and self._pending_ocr_frame is not None
            and now >= self._next_ocr_allowed
        ):
            pending = self._pending_ocr_frame
            self._pending_ocr_frame = None
            self._submit_ocr(pending)

        self._overlay.set_scene(frame, self._tracker.visible_tracks)

    def _submit_ocr(self, frame: np.ndarray) -> None:
        self._ocr_future = self._ocr_executor.submit(self._ocr.recognize_frame, frame)

    def _collect_ocr(self) -> None:
        future = self._ocr_future
        if future is None or not future.done():
            return
        self._ocr_future = None
        now = time.monotonic()
        self._next_ocr_allowed = (
            now + self._config.live.ocr_cooldown_ms / 1000
        )
        try:
            observations = future.result()
        except Exception as exc:
            self._control.set_status("OCR 暂时失败，等待画面变化后重试", str(exc))
            print(f"OCR 错误：{exc}", file=sys.stderr)
            return

        self._ocr_scan_count += 1
        if self._debug and observations:
            print("OCR：" + " | ".join(item.text for item in observations))
        self._last_ocr_completed = now
        update = self._tracker.observe(observations, now)
        if update.stable_sources:
            if self._debug:
                print("稳定字幕：" + " | ".join(item.text for item in update.stable_sources))
            self._submit_translations(update.stable_sources)

    def _submit_translations(self, sources: Sequence[SourceText]) -> None:
        batch_size = self._config.live.max_batch_size
        for offset in range(0, len(sources), batch_size):
            batch = TranslationBatch(tuple(sources[offset : offset + batch_size]))
            context = tuple(self._context)
            future = self._translation_executor.submit(self._translate_blocking, batch, context)
            self._translation_futures[future] = batch

    def _translate_blocking(
        self,
        batch: TranslationBatch,
        context: tuple[ContextPair, ...],
    ) -> CachedTranslationOutcome:
        async def translate() -> CachedTranslationOutcome:
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
                return await cached_service.translate(batch, context=context)

        return asyncio.run(translate())

    def _collect_translations(self) -> None:
        for future in tuple(self._translation_futures):
            if not future.done():
                continue
            batch = self._translation_futures.pop(future)
            try:
                cached_outcome = future.result()
            except Exception as exc:
                self._control.set_status("翻译服务异常，屏幕保留原文", str(exc))
                print(f"翻译错误：{exc}", file=sys.stderr)
                continue

            outcome = cached_outcome.outcome
            current = {
                (track.track_id, track.revision)
                for track in self._tracker.visible_tracks
            }
            accepted_with_origins = tuple(
                (result, origin)
                for result, origin in zip(outcome.results, cached_outcome.origins)
                if (result.source.track_id, result.source.revision) in current
            )
            accepted = tuple(result for result, _ in accepted_with_origins)
            self._stale_result_count += (
                len(outcome.discarded_stale)
                + len(outcome.results)
                - len(accepted)
            )
            self._tracker.apply_translations(accepted)
            for result in accepted:
                self._context.append(ContextPair(result.source.text, result.translated_text))
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
                    f"当前上下文 {len(self._context)} 条{profile_label}",
                )
            if self._latest_frame is not None:
                self._overlay.set_scene(self._latest_frame, self._tracker.visible_tracks)

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
    app = QApplication.instance() or QApplication(["game-screen-translator"])
    app.setQuitOnLastWindowClosed(False)

    ocr = PaddleOcrEngine(
        language=config.ocr.language,
        min_score=config.ocr.min_score,
        cache_dir=(config_path.resolve().parent / config.ocr.cache_dir),
        detection_model=config.ocr.detection_model,
        recognition_model=config.ocr.recognition_model,
        model_source=config.ocr.model_source,
        cpu_threads=config.ocr.cpu_threads,
        detection_max_side=config.ocr.detection_max_side,
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
        test_window.setWindowTitle("Game Translator Live Test Source")
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
    overlay.show()
    control.show()
    controller.start()
    if duration_seconds is not None:
        if duration_seconds <= 0:
            raise ValueError("--duration 必须大于 0")
        QTimer.singleShot(round(duration_seconds * 1000), app.quit)
    exit_code = app.exec()
    if test_window is not None:
        test_window.close()
    return exit_code

"""Typed access to the processing transaction owned by a LiveController.

The controller remains the sole owner of OCR filtering, tracking, grouping,
arbitration, translation batching/retries, cache/context and result mapping.
This facade lets a frozen-frame caller use that exact transaction without
starting the live capture/ROI scheduling loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import numpy as np

from game_screen_translator.domain import SourceText
from game_screen_translator.live.tracker import Bounds

if TYPE_CHECKING:
    from game_screen_translator.config import AppConfig
    from game_screen_translator.overlay.window import TranslationOverlay
    from game_screen_translator.ocr.paddle import PaddleOcrEngine
    from game_screen_translator.profiles import GameProfile


@dataclass(frozen=True, slots=True)
class ProcessingItemSnapshot:
    source: SourceText
    translated_text: str | None
    bounds: Bounds
    state: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ProcessingStatistics:
    ocr_scans: int = 0
    model_results: int = 0
    cache_hits: int = 0
    retries: int = 0
    failures: int = 0
    stale_results: int = 0


@dataclass(frozen=True, slots=True)
class ProcessingSnapshot:
    request_id: str | int | None
    items: tuple[ProcessingItemSnapshot, ...]
    pending: bool
    terminal: bool
    error: str | None
    stale: bool
    statistics: ProcessingStatistics


class LiveProcessingSession:
    """Stable public adapter for the transaction of one live controller.

    Main mode keeps its normal frame and ROI schedulers. Snapshot mode submits
    one frozen frame and drives only confirmation, arbitration, translation,
    retry and publication work in that same controller.
    """

    def __init__(self, controller: LiveController) -> None:
        self._controller = controller

    def reset_attempt(self) -> None:
        self._controller._reset_processing_attempt()

    def submit_frame(
        self,
        frame: np.ndarray,
        request_id: str | int,
        *,
        is_current: Callable[[], bool] | None = None,
    ) -> None:
        self._controller._submit_snapshot_frame(
            frame,
            request_id=request_id,
            is_current=is_current,
        )

    def snapshot(self) -> ProcessingSnapshot:
        return self._controller._processing_snapshot()

    def close(self) -> None:
        self._controller.close()


class _SessionCaptureGeometry:
    """Passive geometry token; never starts or owns the caller's capture."""

    def __init__(
        self,
        output_size: tuple[int, int],
        region: tuple[int, int, int, int],
        active_backend: str,
    ) -> None:
        self.output_size = output_size
        self.region = region
        self.active_backend = active_backend

    def close(self) -> None:
        pass


class _NullOverlay:
    def set_scene(self, frame, tracks) -> None:
        pass

    def set_roi_debug_snapshot(self, snapshot) -> None:
        pass


class _NullControl:
    def set_latency(self, _value) -> None:
        pass

    def set_status(self, _status, _detail="") -> None:
        pass


def create_processing_session(
    config: AppConfig,
    *,
    app,
    ocr: PaddleOcrEngine,
    profile: GameProfile | None,
    capture_output_size: tuple[int, int],
    capture_region: tuple[int, int, int, int],
    capture_backend: str,
    overlay: TranslationOverlay | None = None,
) -> LiveProcessingSession:
    """Create the public transaction around a controller on the GUI thread.

    The supplied geometry is passive. The session never reads or closes the
    adapter's one-shot capture object. A supplied overlay receives the same
    ``set_scene`` updates as live mode, but remains owned and closed by caller.
    """
    from game_screen_translator.live.runtime import LiveController

    controller = LiveController(
        config,
        capture=_SessionCaptureGeometry(
            capture_output_size,
            capture_region,
            capture_backend,
        ),
        ocr=ocr,
        overlay=overlay if overlay is not None else _NullOverlay(),
        control=_NullControl(),
        app=app,
        profile=profile,
    )
    return controller.processing_session


if TYPE_CHECKING:
    from game_screen_translator.live.runtime import LiveController

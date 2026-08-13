import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication

from game_screen_translator.config import AppConfig, LiveConfig, TranslationConfig
from game_screen_translator.live import runtime as live_runtime
from game_screen_translator.live.runtime import LiveController
from game_screen_translator.ocr.types import OcrText
from game_screen_translator.profiles import create_game_profile
from game_screen_translator.domain import (
    SourceText,
    TranslationBatch,
    TranslationResult,
)
from game_screen_translator.translation.cached import CachedTranslationOutcome
from game_screen_translator.translation.hy_mt import TranslationProtocolError
from game_screen_translator.translation.service import TranslationOutcome
from game_screen_translator.translation.transport import TranslationTransportError


class FakeCapture:
    region = (0, 0, 320, 120)
    active_backend = "fake"

    def __init__(self) -> None:
        self.closed = False

    def latest_frame(self):
        return np.zeros((120, 320, 3), dtype=np.uint8)

    def close(self) -> None:
        self.closed = True


class FakeOcr:
    def recognize_frame(self, frame):
        return (
            OcrText("待って。", 0.99, ((10, 20), (200, 20), (200, 60), (10, 60))),
        )


class FakeNoisyOcr:
    def recognize_frame(self, frame):
        return (
            OcrText("设置", 0.99, ((10, 10), (80, 10), (80, 30), (10, 30))),
            OcrText("⚙", 0.99, ((90, 10), (110, 10), (110, 30), (90, 30))),
            OcrText("待って。", 0.99, ((10, 50), (200, 50), (200, 90), (10, 90))),
        )


class FakeOverlay:
    def __init__(self) -> None:
        self.scenes = 0

    def set_scene(self, frame, tracks) -> None:
        self.scenes += 1


class FakeControl:
    def __init__(self) -> None:
        self.status = ""
        self.detail = ""
        self.latency = ""
        self.filter_status = ""

    def set_status(self, status, detail="") -> None:
        self.status = status
        self.detail = detail

    def set_latency(self, summary) -> None:
        self.latency = summary

    def set_filter_status(self, summary) -> None:
        self.filter_status = summary


def test_debug_tick_logs_only_after_ocr_result(capsys) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-7b",
        ),
        live=LiveConfig(stable_observations=99),
    )
    capture = FakeCapture()
    overlay = FakeOverlay()
    controller = LiveController(
        config,
        capture=capture,
        ocr=FakeOcr(),
        overlay=overlay,
        control=FakeControl(),
        app=app,
        debug=True,
    )

    controller._tick()
    controller._ocr_future.result(timeout=2)
    controller._tick()

    assert controller._ocr_scan_count == 1
    assert "OCR 保留：待って。" in capsys.readouterr().out
    assert overlay.scenes == 2
    controller.close()
    assert capture.closed


def test_live_controller_uses_configured_translation_concurrency() -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-7b",
            max_concurrency=6,
        )
    )
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeOcr(),
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )

    assert controller._translation_executor._max_workers == 6
    controller.close()


def test_ocr_filter_rejects_noise_before_tracking_and_translation() -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-7b",
        ),
        live=LiveConfig(stable_observations=99),
    )
    control = FakeControl()
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeNoisyOcr(),
        overlay=FakeOverlay(),
        control=control,
        app=app,
    )

    controller._tick()
    controller._ocr_future.result(timeout=2)
    controller._tick()

    assert [track.text for track in controller._tracker.visible_tracks] == ["待って。"]
    assert controller._translation_futures == {}
    assert controller._ocr_text_count == 3
    assert controller._filtered_text_count == 2
    assert "识别 3 条，保留 1 条，过滤 2 条" in control.filter_status
    controller.close()


def test_live_translation_path_uses_profile_manual_correction(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://127.0.0.1:1/v1",
            model="hy-mt1.5-7b",
        )
    )
    profile = create_game_profile(tmp_path / "config.toml", config, "game")
    profile.cache.set_manual_correction(
        "待て。",
        "等等。",
        source_language=config.ocr.language,
        target_language=config.translation.target_language,
    )
    capture = FakeCapture()
    controller = LiveController(
        config,
        capture=capture,
        ocr=FakeOcr(),
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
        profile=profile,
    )

    translated = controller._translate_blocking(
        TranslationBatch((SourceText("live", "line", 1, "待て。"),)),
        (),
    )

    assert [item.translated_text for item in translated.outcome.results] == ["等等。"]
    assert translated.origins == ("manual",)
    controller.close()
    assert capture.closed


def test_ocr_backlog_waits_for_cooldown_after_completion(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-7b",
        ),
        live=LiveConfig(stable_observations=99, ocr_cooldown_ms=350),
    )
    capture = FakeCapture()
    ocr = FakeOcr()
    controller = LiveController(
        config,
        capture=capture,
        ocr=ocr,
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )
    clock = [100.0]
    monkeypatch.setattr(live_runtime.time, "monotonic", lambda: clock[0])
    frame = capture.latest_frame()
    controller._submit_ocr(frame)
    controller._pending_ocr_frame = frame
    controller._ocr_future.result(timeout=2)

    controller._collect_ocr()

    assert controller._ocr_scan_count == 1
    assert controller._ocr_future is None
    assert controller._pending_ocr_frame is frame
    assert controller._next_ocr_allowed == 100.35

    clock[0] = 100.1
    controller._tick()
    assert controller._ocr_future is None

    clock[0] = 100.36
    controller._tick()
    assert controller._ocr_future is not None
    controller._ocr_future.result(timeout=2)
    controller.close()


def test_live_latency_display_covers_ocr_queue_and_cached_translation(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://127.0.0.1:1/v1",
            model="hy-mt1.5-7b",
        ),
        live=LiveConfig(stable_observations=1, stable_ms=0),
    )
    profile = create_game_profile(tmp_path / "config.toml", config, "timing-game")
    profile.cache.set_manual_correction(
        "待って。",
        "固定译文",
        source_language=config.ocr.language,
        target_language=config.translation.target_language,
    )
    control = FakeControl()
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeOcr(),
        overlay=FakeOverlay(),
        control=control,
        app=app,
        profile=profile,
    )

    controller._tick()
    controller._ocr_future.result(timeout=2)
    controller._tick()
    translation_future = next(iter(controller._translation_futures))
    translation_future.result(timeout=2)
    controller._collect_translations()

    assert "OCR" in control.latency
    assert "稳定" in control.latency
    assert "排队" in control.latency
    assert "LLM 缓存命中" in control.latency
    assert "总计" in control.latency
    assert control.detail.startswith("已覆盖 1 条")
    controller.close()


def _successful_worker_result(batch: TranslationBatch):
    results = tuple(
        TranslationResult(source, f"译文：{source.text}") for source in batch.items
    )
    return live_runtime._TranslationWorkerResult(
        CachedTranslationOutcome(
            TranslationOutcome(results, ()),
            tuple("model" for _ in results),
        ),
        started_at=100.0,
        completed_at=100.1,
        llm_seconds=0.1,
    )


def _two_visible_sources(controller: LiveController):
    update = controller._tracker.observe(
        (
            OcrText("待って。", 0.99, ((10, 10), (150, 10), (150, 40), (10, 40))),
            OcrText("急げ。", 0.99, ((10, 60), (150, 60), (150, 90), (10, 90))),
        ),
        now=1.0,
    )
    return update.stable_sources


def test_protocol_failure_splits_batch_and_recovers_every_visible_text(
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-1.8b",
        ),
        live=LiveConfig(stable_observations=1, stable_ms=0, max_batch_size=8),
    )
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeOcr(),
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )
    clock = [100.0]
    calls: list[tuple[str, ...]] = []

    def translate(batch, context):
        calls.append(tuple(source.text for source in batch.items))
        if len(batch.items) > 1:
            raise TranslationProtocolError("缺少 id")
        return _successful_worker_result(batch)

    monkeypatch.setattr(live_runtime.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(controller, "_translate_blocking_timed", translate)
    controller._submit_translations(_two_visible_sources(controller))
    next(iter(controller._translation_futures)).exception(timeout=2)

    controller._collect_translations()

    assert len(controller._translation_retries) == 2
    assert [len(item.batch.items) for item in controller._translation_retries] == [1, 1]
    clock[0] = 100.36
    controller._submit_ready_translation_retries()
    for future in tuple(controller._translation_futures):
        future.result(timeout=2)
    controller._collect_translations()

    assert calls[0] == ("待って。", "急げ。")
    assert set(calls[1:]) == {("待って。",), ("急げ。",)}
    assert {track.translated_text for track in controller._tracker.visible_tracks} == {
        "译文：待って。",
        "译文：急げ。",
    }
    assert controller._translation_failure_count == 0
    controller.close()


def test_http_500_retries_same_batch_once_then_splits(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-1.8b",
        ),
        live=LiveConfig(stable_observations=1, stable_ms=0, max_batch_size=8),
    )
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeOcr(),
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )
    clock = [200.0]
    calls: list[int] = []

    def translate(batch, context):
        calls.append(len(batch.items))
        if len(calls) <= 2:
            raise TranslationTransportError("HTTP 500")
        return _successful_worker_result(batch)

    monkeypatch.setattr(live_runtime.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(controller, "_translate_blocking_timed", translate)
    controller._submit_translations(_two_visible_sources(controller))
    next(iter(controller._translation_futures)).exception(timeout=2)
    controller._collect_translations()

    assert len(controller._translation_retries) == 1
    assert len(controller._translation_retries[0].batch.items) == 2
    clock[0] = 200.36
    controller._submit_ready_translation_retries()
    next(iter(controller._translation_futures)).exception(timeout=2)
    controller._collect_translations()

    assert len(controller._translation_retries) == 2
    assert [len(item.batch.items) for item in controller._translation_retries] == [1, 1]
    clock[0] = 200.72
    controller._submit_ready_translation_retries()
    for future in tuple(controller._translation_futures):
        future.result(timeout=2)
    controller._collect_translations()

    assert calls == [2, 2, 1, 1]
    assert all(
        track.translated_text is not None
        for track in controller._tracker.visible_tracks
    )
    controller.close()


def test_late_result_reattaches_when_same_text_moves_to_a_new_track(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-1.8b",
        ),
        live=LiveConfig(stable_observations=1, stable_ms=0, clear_after_ms=0),
    )
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeOcr(),
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )
    monkeypatch.setattr(
        controller,
        "_translate_blocking_timed",
        lambda batch, context: _successful_worker_result(batch),
    )
    old_update = controller._tracker.observe(
        (OcrText("待って。", 0.99, ((10, 10), (150, 10), (150, 40), (10, 40))),),
        now=1.0,
    )
    old_source = old_update.stable_sources[0]
    controller._submit_translations((old_source,))
    next(iter(controller._translation_futures)).result(timeout=2)

    controller._tracker.observe((), now=2.0)
    new_update = controller._tracker.observe(
        (OcrText("待って。", 0.99, ((500, 200), (650, 200), (650, 230), (500, 230))),),
        now=2.1,
    )
    assert new_update.stable_sources[0].track_id != old_source.track_id

    controller._collect_translations()

    assert controller._tracker.visible_tracks[0].translated_text == "译文：待って。"
    assert controller._reattached_result_count == 1
    assert controller._stale_result_count == 0
    controller.close()

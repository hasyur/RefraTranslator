import os
import threading
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


class MutableCapture:
    region = (0, 0, 1600, 900)
    output_size = (1600, 900)
    active_backend = "fake"

    def __init__(self, frame: np.ndarray) -> None:
        self.frame = frame
        self.closed = False

    def latest_frame(self):
        return self.frame.copy()

    def close(self) -> None:
        self.closed = True


class FakeOcr:
    def recognize_frame(self, frame):
        return (
            OcrText("待って。", 0.99, ((10, 20), (200, 20), (200, 60), (10, 60))),
        )


class FakeEmptyOcr:
    def recognize_frame(self, frame):
        return ()


class FakeFailingOcr:
    def recognize_frame(self, frame):
        raise RuntimeError("temporary OCR failure")


class FakeNoisyOcr:
    def recognize_frame(self, frame):
        return (
            OcrText("设置", 0.99, ((10, 10), (80, 10), (80, 30), (10, 30))),
            OcrText("⚙", 0.99, ((90, 10), (110, 10), (110, 30), (90, 30))),
            OcrText("待って。", 0.99, ((10, 50), (200, 50), (200, 90), (10, 90))),
        )


class FakeSplitVerticalOcr:
    def recognize_frame(self, frame):
        return (
            OcrText("希望", 0.99, ((800, 100), (840, 100), (840, 200), (800, 200))),
            OcrText("はある", 0.99, ((800, 195), (840, 195), (840, 330), (800, 330))),
        )


class ColorBlockOcr:
    _TEXT_BY_VALUE = {
        100: "待って。",
        150: "先へ進め。",
        220: "止まれ。",
    }

    def __init__(self) -> None:
        self.input_shapes: list[tuple[int, ...]] = []

    def recognize_frame(self, frame):
        self.input_shapes.append(tuple(frame.shape))
        observations = []
        for value, text in self._TEXT_BY_VALUE.items():
            ys, xs = np.nonzero(frame[:, :, 0] == value)
            if not len(xs):
                continue
            left, right = int(xs.min()), int(xs.max()) + 1
            top, bottom = int(ys.min()), int(ys.max()) + 1
            observations.append(
                OcrText(
                    text,
                    0.99,
                    ((left, top), (right, top), (right, bottom), (left, bottom)),
                )
            )
        return tuple(observations)


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


def test_layout_fragments_merge_before_language_filtering() -> None:
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
        ocr=FakeSplitVerticalOcr(),
        overlay=FakeOverlay(),
        control=control,
        app=app,
    )

    result = controller._run_ocr(np.zeros((400, 900, 3), dtype=np.uint8), 1.0)

    assert [item.text for item in result.observations] == ["希望はある"]
    assert result.raw_count == 2
    assert result.layout_count == 1
    assert result.rejected == ()
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


def test_live_controller_confirms_once_after_scene_settles(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-7b",
        ),
        live=LiveConfig(settle_rescan_ms=500, idle_rescan_ms=0),
    )
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeEmptyOcr(),
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )
    clock = [10.0]
    monkeypatch.setattr(live_runtime.time, "monotonic", lambda: clock[0])

    controller._tick()
    controller._ocr_future.result(timeout=2)
    clock[0] = 10.1
    controller._tick()
    assert controller._ocr_scan_count == 1
    assert controller._ocr_future is None

    clock[0] = 10.49
    controller._tick()
    assert controller._ocr_future is None

    clock[0] = 10.5
    controller._tick()
    assert controller._ocr_future is not None
    controller._ocr_future.result(timeout=2)
    clock[0] = 10.6
    controller._tick()
    assert controller._ocr_scan_count == 2
    assert controller._ocr_future is None

    clock[0] = 11.5
    controller._tick()
    assert controller._ocr_future is None
    controller.close()


def test_live_controller_rechecks_an_unchanged_frame_at_idle_interval(
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-7b",
        ),
        live=LiveConfig(settle_rescan_ms=0, idle_rescan_ms=2000),
    )
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeEmptyOcr(),
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )
    clock = [20.0]
    monkeypatch.setattr(live_runtime.time, "monotonic", lambda: clock[0])

    controller._tick()
    controller._ocr_future.result(timeout=2)
    clock[0] = 20.1
    controller._tick()

    clock[0] = 22.09
    controller._tick()
    assert controller._ocr_future is None

    clock[0] = 22.1
    controller._tick()
    assert controller._ocr_future is not None
    controller._ocr_future.result(timeout=2)
    clock[0] = 22.2
    controller._tick()
    assert controller._ocr_scan_count == 2
    assert controller._ocr_future is None
    controller.close()


def test_failed_ocr_retries_on_idle_interval_without_new_frame_change(
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-7b",
        ),
        live=LiveConfig(settle_rescan_ms=0, idle_rescan_ms=2000),
    )
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeFailingOcr(),
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )
    clock = [30.0]
    monkeypatch.setattr(live_runtime.time, "monotonic", lambda: clock[0])

    controller._tick()
    controller._ocr_future.exception(timeout=2)
    clock[0] = 30.1
    controller._tick()
    assert controller._last_ocr_completed == 30.1

    clock[0] = 32.09
    controller._tick()
    assert controller._ocr_future is None

    clock[0] = 32.1
    controller._tick()
    assert controller._ocr_future is not None
    controller._ocr_future.exception(timeout=2)
    controller.close()


def _dynamic_roi_frame(*, changed: bool = False) -> np.ndarray:
    frame = np.zeros((900, 1600, 3), dtype=np.uint8)
    frame[200:260, 200:600] = 220 if changed else 100
    frame[700:760, 200:600] = 150
    return frame


def test_dynamic_roi_runtime_uses_local_ocr_and_preserves_outside_tracks(
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-7b",
        ),
        live=LiveConfig(
            stable_observations=99,
            dynamic_roi_enabled=True,
            change_poll_fps=5,
            dynamic_roi_settle_ms=100,
            dynamic_roi_ocr_interval_ms=250,
            dynamic_roi_max_coalesce_ms=450,
        ),
    )
    capture = MutableCapture(_dynamic_roi_frame())
    ocr = ColorBlockOcr()
    controller = LiveController(
        config,
        capture=capture,
        ocr=ocr,
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )
    clock = [10.0]
    monkeypatch.setattr(live_runtime.time, "monotonic", lambda: clock[0])

    controller._tick()
    controller._ocr_future.result(timeout=2)
    clock[0] = 10.05
    controller._tick()
    assert controller._roi_scheduler is not None
    assert controller._roi_scheduler.primed
    assert controller._roi_scheduler.settle_interval_s == 0.1
    assert controller._roi_scheduler.min_ocr_interval_s == 0.25
    assert controller._roi_scheduler.max_coalesce_s == 0.45
    assert controller._timer.interval() == 200
    assert [track.text for track in controller._tracker.visible_tracks] == [
        "待って。",
        "先へ進め。",
    ]

    capture.frame = _dynamic_roi_frame(changed=True)
    clock[0] = 10.2
    controller._tick()
    assert controller._ocr_future is None

    clock[0] = 10.4
    controller._tick()
    assert controller._ocr_future is not None
    assert controller._active_roi_plan is not None
    assert not controller._active_roi_plan.fallback_full_frame
    assert controller._active_roi_plan.candidate_coverage_fraction > 0.0
    assert controller._active_roi_plan.candidate_region_count == 1
    controller._ocr_future.result(timeout=2)

    clock[0] = 10.5
    controller._tick()

    assert [track.text for track in controller._tracker.visible_tracks] == [
        "止まれ。",
        "先へ進め。",
    ]
    assert ocr.input_shapes[0] == (900, 1600, 3)
    assert ocr.input_shapes[1][0] < 900
    assert ocr.input_shapes[1][1] < 1600
    assert controller._ocr_scan_count == 2
    assert controller._roi_scan_count == 1
    assert controller._roi_full_fallback_count == 0
    controller.close()


def test_dynamic_roi_initial_failure_retries_without_legacy_idle_scan(
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-7b",
        ),
        live=LiveConfig(
            dynamic_roi_enabled=True,
            idle_rescan_ms=0,
            ocr_cooldown_ms=0,
        ),
    )
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeFailingOcr(),
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )
    clock = [30.0]
    monkeypatch.setattr(live_runtime.time, "monotonic", lambda: clock[0])

    controller._tick()
    controller._ocr_future.exception(timeout=2)
    clock[0] = 30.1
    controller._tick()
    assert controller._ocr_future is None
    assert controller._next_ocr_allowed == 31.1

    clock[0] = 31.09
    controller._tick()
    assert controller._ocr_future is None

    clock[0] = 31.1
    controller._tick()
    assert controller._ocr_future is not None
    controller._ocr_future.exception(timeout=2)
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


def _many_visible_sources(controller: LiveController, count: int):
    observations = tuple(
        OcrText(
            f"字幕{index}です。",
            0.99,
            ((10, index * 30), (180, index * 30), (180, index * 30 + 20), (10, index * 30 + 20)),
        )
        for index in range(count)
    )
    return controller._tracker.observe(observations, now=1.0).stable_sources


def test_translation_scheduler_bounds_pending_work(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-1.8b",
            max_concurrency=2,
        ),
        live=LiveConfig(stable_observations=1, stable_ms=0, max_batch_size=1),
    )
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeOcr(),
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )
    release = threading.Event()

    def translate(batch, context):
        del context
        release.wait(timeout=5)
        return _successful_worker_result(batch)

    monkeypatch.setattr(controller, "_translate_blocking_timed", translate)
    sources = _many_visible_sources(controller, 10)

    try:
        controller._submit_translations(sources)

        assert len(controller._translation_futures) == 2
        assert len(controller._pending_translations) == 4
        assert len(controller._scheduled_translation_keys()) == 6

        controller._queue_untranslated_visible_sources()
        assert len(controller._translation_futures) == 2
        assert len(controller._pending_translations) == 4
    finally:
        release.set()
        controller.close()


def test_pending_translation_is_replaced_by_latest_track_revision(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-1.8b",
            max_concurrency=1,
        ),
        live=LiveConfig(stable_observations=1, stable_ms=0, max_batch_size=1),
    )
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeOcr(),
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )
    release_first = threading.Event()
    calls: list[str] = []

    def translate(batch, context):
        del context
        text = batch.items[0].text
        calls.append(text)
        if text == "先处理。":
            release_first.wait(timeout=5)
        return _successful_worker_result(batch)

    monkeypatch.setattr(controller, "_translate_blocking_timed", translate)
    initial = controller._tracker.observe(
        (
            OcrText("先处理。", 0.99, ((10, 10), (150, 10), (150, 40), (10, 40))),
            OcrText("旧识别。", 0.99, ((10, 60), (150, 60), (150, 90), (10, 90))),
        ),
        now=1.0,
    )

    try:
        controller._submit_translations(initial.stable_sources)
        revised = controller._tracker.observe(
            (
                OcrText("先处理。", 0.99, ((10, 10), (150, 10), (150, 40), (10, 40))),
                OcrText("最新识别。", 0.99, ((10, 60), (150, 60), (150, 90), (10, 90))),
            ),
            now=1.1,
        )
        controller._submit_translations(revised.stable_sources)

        assert [
            submission.batch.items[0].text
            for submission in controller._pending_translations
        ] == ["最新识别。"]
        assert controller._translation_coalesced_count == 1

        release_first.set()
        next(iter(controller._translation_futures)).result(timeout=2)
        controller._collect_translations()
        next(iter(controller._translation_futures)).result(timeout=2)
        controller._collect_translations()

        assert calls == ["先处理。", "最新识别。"]
        assert [
            track.translated_text for track in controller._tracker.visible_tracks
        ] == ["译文：先处理。", "译文：最新识别。"]
    finally:
        release_first.set()
        controller.close()


def test_deferred_visible_text_returns_when_queue_has_capacity(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-1.8b",
            max_concurrency=1,
        ),
        live=LiveConfig(stable_observations=1, stable_ms=0, max_batch_size=1),
    )
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeOcr(),
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )
    calls: list[str] = []

    def translate(batch, context):
        del context
        calls.extend(source.text for source in batch.items)
        return _successful_worker_result(batch)

    monkeypatch.setattr(controller, "_translate_blocking_timed", translate)
    sources = _many_visible_sources(controller, 7)
    controller._submit_translations(sources)

    for _ in range(20):
        for future in tuple(controller._translation_futures):
            future.result(timeout=2)
        controller._collect_translations()
        controller._queue_untranslated_visible_sources()
        controller._dispatch_translation_work()
        if all(
            track.translated_text is not None
            for track in controller._tracker.visible_tracks
        ):
            break

    assert set(calls) == {source.text for source in sources}
    assert all(
        track.translated_text is not None
        for track in controller._tracker.visible_tracks
    )
    assert controller._pending_translations == []
    controller.close()


def test_concurrent_batches_publish_in_top_to_bottom_order(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-1.8b",
            max_concurrency=2,
        ),
        live=LiveConfig(stable_observations=1, stable_ms=0, max_batch_size=1),
    )
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeOcr(),
        overlay=FakeOverlay(),
        control=FakeControl(),
        app=app,
    )
    update = controller._tracker.observe(
        (
            OcrText("下方。", 0.99, ((10, 60), (150, 60), (150, 90), (10, 90))),
            OcrText("上方。", 0.99, ((10, 10), (150, 10), (150, 40), (10, 40))),
        ),
        now=1.0,
    )
    release_top = threading.Event()
    bottom_completed = threading.Event()

    def translate(batch, context):
        del context
        if batch.items[0].text == "上方。":
            release_top.wait(timeout=5)
        else:
            bottom_completed.set()
        return _successful_worker_result(batch)

    monkeypatch.setattr(controller, "_translate_blocking_timed", translate)
    # Deliberately pass the sources in reverse to verify the runtime does not
    # depend on PaddleOCR's result order.
    controller._submit_translations(tuple(reversed(update.stable_sources)))
    futures_by_text = {
        submission.batch.items[0].text: future
        for future, submission in controller._translation_futures.items()
    }

    try:
        assert bottom_completed.wait(timeout=2)
        futures_by_text["下方。"].result(timeout=2)
        assert not futures_by_text["上方。"].done()

        controller._collect_translations()
        assert all(
            track.translated_text is None
            for track in controller._tracker.visible_tracks
        )
        assert tuple(controller._context) == ()
        assert [pair.source for pair in controller._context_snapshot()] == ["下方。"]

        follow_up_update = controller._tracker.observe(
            (
                OcrText("上方。", 0.99, ((10, 10), (150, 10), (150, 40), (10, 40))),
                OcrText("下方。", 0.99, ((10, 60), (150, 60), (150, 90), (10, 90))),
                OcrText("后续。", 0.99, ((10, 110), (150, 110), (150, 140), (10, 140))),
            ),
            now=1.1,
        )
        controller._submit_translations(follow_up_update.stable_sources)
        follow_up_future, follow_up = next(
            (future, submission)
            for future, submission in controller._translation_futures.items()
            if submission.batch.items[0].text == "后续。"
        )
        assert [pair.source for pair in follow_up.context] == ["下方。"]

        release_top.set()
        futures_by_text["上方。"].result(timeout=2)
        follow_up_future.result(timeout=2)
        controller._collect_translations()

        assert [
            track.translated_text for track in controller._tracker.visible_tracks
        ] == ["译文：上方。", "译文：下方。", "译文：后续。"]
        assert [pair.source for pair in controller._context] == [
            "上方。",
            "下方。",
            "后续。",
        ]
        assert controller._early_context == {}
    finally:
        release_top.set()
        controller.close()


def test_protocol_failure_splits_batch_and_recovers_every_visible_text(
    monkeypatch,
    capsys,
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
    control = FakeControl()
    controller = LiveController(
        config,
        capture=FakeCapture(),
        ocr=FakeOcr(),
        overlay=FakeOverlay(),
        control=control,
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
    assert control.status == "翻译格式异常，正在自动恢复"
    captured = capsys.readouterr()
    assert "翻译协议偏差，正在自动恢复：缺少 id" in captured.err
    assert "翻译错误：" not in captured.err
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


def test_split_retries_share_the_configured_concurrency_limit(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-1.8b",
            max_concurrency=1,
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
    clock = [300.0]
    calls: list[int] = []

    def translate(batch, context):
        del context
        calls.append(len(batch.items))
        if len(batch.items) > 1:
            raise TranslationProtocolError("缺少 id")
        return _successful_worker_result(batch)

    monkeypatch.setattr(live_runtime.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(controller, "_translate_blocking_timed", translate)
    controller._submit_translations(_two_visible_sources(controller))
    next(iter(controller._translation_futures)).exception(timeout=2)
    controller._collect_translations()

    assert len(controller._translation_retries) == 2
    clock[0] = 300.36
    controller._submit_ready_translation_retries()
    assert len(controller._translation_futures) == 1
    assert len(controller._translation_retries) == 1

    next(iter(controller._translation_futures)).result(timeout=2)
    controller._collect_translations()
    assert len(controller._translation_futures) == 1
    assert controller._translation_retries == []

    next(iter(controller._translation_futures)).result(timeout=2)
    controller._collect_translations()

    assert calls == [2, 1, 1]
    assert all(
        track.translated_text is not None
        for track in controller._tracker.visible_tracks
    )
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

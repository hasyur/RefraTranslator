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
from game_screen_translator.domain import SourceText, TranslationBatch


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

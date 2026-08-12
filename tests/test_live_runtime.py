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
            OcrText("固定字幕", 0.99, ((10, 20), (200, 20), (200, 60), (10, 60))),
        )


class FakeOverlay:
    def __init__(self) -> None:
        self.scenes = 0

    def set_scene(self, frame, tracks) -> None:
        self.scenes += 1


class FakeControl:
    def __init__(self) -> None:
        self.status = ""

    def set_status(self, status, detail="") -> None:
        self.status = status


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
    assert "OCR：固定字幕" in capsys.readouterr().out
    assert overlay.scenes == 2
    controller.close()
    assert capture.closed


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

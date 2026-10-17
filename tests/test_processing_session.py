"""Exercise both trigger adapters through the same real processing transaction."""
import os
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from game_screen_translator.config import AppConfig, LiveConfig, OcrConfig, TranslationConfig
from game_screen_translator.live.processing_session import LiveProcessingSession, create_processing_session
from game_screen_translator.live.runtime import LiveController
from game_screen_translator.ocr.types import OcrText
from game_screen_translator.translation.service import TranslationService
from game_screen_translator.translation.transport import OpenAICompatibleTransport


class Capture:
    output_size = (600, 120)
    region = (0, 0, 600, 120)
    active_backend = "test"

    def __init__(self):
        self.frame = np.zeros((120, 600, 3), dtype=np.uint8)
        self.calls = 0

    def latest_frame(self):
        self.calls += 1
        return self.frame

    def close(self):
        pass


class Ports:
    def set_scene(self, frame, tracks):
        self.tracks = tuple(tracks)

    def set_status(self, *args):
        pass

    def set_latency(self, *args):
        pass

    def setGeometry(self, *args):
        pass

    def set_roi_debug_snapshot(self, snapshot):
        pass


def observation(text, left, top, right, bottom):
    return OcrText(text, .99, ((left, top), (right, top), (right, bottom), (left, bottom)))


class SceneOcr:
    def __init__(self):
        self.calls = 0

    def recognize_frame(self, frame):
        self.calls += 1
        return (
            observation("長期の保管に適していないため、", 5, 10, 340, 28),
            observation("貿易量は少ない。", 5, 32, 340, 50),
            observation("アンゴラ", 450, 12, 550, 30),
            observation("ベトナム", 450, 55, 550, 73),
            observation("123456", 450, 85, 550, 103),
            observation("世界計", 5, 85, 100, 103),
        )


def configuration(*, dynamic_roi=False):
    return AppConfig(
        translation=TranslationConfig(base_url="http://test.invalid/v1", model="test", max_concurrency=1),
        ocr=OcrConfig(text_merge_llm_arbitration_enabled=False),
        live=LiveConfig(dynamic_roi_enabled=dynamic_roi, settle_rescan_ms=0, idle_rescan_ms=0),
    )


def wait_for(app, predicate, *, tick=None, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if tick is not None:
            tick()
        app.processEvents()
        result = predicate()
        if result:
            return result
        time.sleep(.003)
    pytest.fail("processing transaction did not reach the expected state")


def install_transport(monkeypatch, *, recover=False):
    """Keep the real service, parser, quality validation, retries and mapping."""
    prompts, batches = [], []
    failed_batch = False
    uncorrected_country = False
    original_translate = TranslationService.translate

    async def translate(service, batch, **kwargs):
        batches.append((tuple(asdict(item).items() for item in batch.items), kwargs.get("retry_count")))
        return await original_translate(service, batch, **kwargs)

    async def complete(transport, prompt):
        nonlocal failed_batch, uncorrected_country
        prompts.append(prompt)
        source = ET.fromstring(prompt[prompt.index("<source>"):])
        if recover and len(source) > 1 and not failed_batch:
            failed_batch = True
            return '<target><sn id="1">错误数量</sn></target>'
        targets = []
        for item in source:
            if item.text == "アンゴラ":
                if recover and not uncorrected_country:
                    uncorrected_country = True
                    translated = "アンゴラ"
                else:
                    translated = "安哥拉"
            elif item.text == "ベトナム":
                translated = "越南"
            else:
                translated = "由于不适合长期储存，贸易量很少。"
            targets.append(f'<sn id="{item.attrib["id"]}">{translated}</sn>')
        return "<target>" + "".join(targets) + "</target>"

    monkeypatch.setattr(TranslationService, "translate", translate)
    monkeypatch.setattr(OpenAICompatibleTransport, "complete", complete)
    return prompts, batches


@pytest.mark.parametrize("recover", [False, True])
def test_live_and_frozen_frame_share_units_batches_prompts_retries_and_mapping(monkeypatch, recover):
    app = QApplication.instance() or QApplication([])
    results = []
    for mode in ("live", "hover"):
        prompts, batches = install_transport(monkeypatch, recover=recover)
        capture, ocr, ports = Capture(), SceneOcr(), Ports()
        if mode == "live":
            controller = LiveController(configuration(), capture=capture, ocr=ocr,
                                        overlay=ports, control=ports, app=app)
            session = controller.processing_session
            tick = controller._tick
        else:
            session = create_processing_session(configuration(), app=app, ocr=ocr, profile=None,
                capture_output_size=capture.output_size, capture_region=capture.region,
                capture_backend=capture.active_backend)
            tick = None
            session.submit_frame(capture.frame, 1)
        try:
            assert isinstance(session, LiveProcessingSession)
            snapshot = wait_for(app, lambda: (s if (s := session.snapshot()).terminal and s.items else None), tick=tick)
            mapped = tuple((asdict(item.source), item.bounds, item.state, item.translated_text) for item in snapshot.items)
            assert len(mapped) == 3  # two body lines grouped, table countries remain separate
            assert any(len(batch) > 1 for batch, _ in batches)
            assert all("123456" not in prompt and "世界計" not in prompt for prompt in prompts)
            assert {item.translated_text for item in snapshot.items} == {
                "由于不适合长期储存，贸易量很少。", "安哥拉", "越南"}
            if recover:
                assert any(stage == 1 for _, stage in batches)
                assert len(batches) > 2
            results.append((list(prompts), list(batches), mapped))
        finally:
            session.close()
            # monkeypatch keeps the original; unwind this one wrapper for the next arm.
            monkeypatch.undo()
    assert results[0] == results[1]


def test_frozen_transaction_stops_ocr_when_done_and_reuses_same_text(monkeypatch):
    app = QApplication.instance() or QApplication([])
    prompts, _ = install_transport(monkeypatch)
    ocr, capture = SceneOcr(), Capture()
    session = create_processing_session(configuration(), app=app, ocr=ocr, profile=None,
        capture_output_size=capture.output_size, capture_region=capture.region, capture_backend="test")
    try:
        session.submit_frame(capture.frame, 1)
        wait_for(app, lambda: session.snapshot().terminal)
        count, requests = ocr.calls, len(prompts)
        until = time.monotonic() + .08
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(.003)
        assert ocr.calls == count
        session.submit_frame(capture.frame, 2)
        wait_for(app, lambda: session.snapshot().terminal)
        assert len(prompts) == requests
        assert all(item.state == "translated" for item in session.snapshot().items)
    finally:
        session.close()
    session.close()
    with pytest.raises(RuntimeError):
        session.submit_frame(capture.frame, 3)


def test_stale_inflight_ocr_drains_then_accepts_the_next_request(monkeypatch):
    app = QApplication.instance() or QApplication([])
    install_transport(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    current = [True]

    class SlowOcr(SceneOcr):
        def recognize_frame(self, frame):
            entered.set()
            assert release.wait(3)
            return super().recognize_frame(frame)

    capture = Capture()
    session = create_processing_session(configuration(), app=app, ocr=SlowOcr(), profile=None,
        capture_output_size=capture.output_size, capture_region=capture.region, capture_backend="test")
    try:
        session.submit_frame(capture.frame, 1, is_current=lambda: current[0])
        assert entered.wait(1)
        current[0] = False
        wait_for(app, lambda: session.snapshot().stale)
        release.set()
        wait_for(app, lambda: session.snapshot().terminal)
        assert not session.snapshot().items
        current[0] = True
        session.submit_frame(capture.frame, 2, is_current=lambda: current[0])
        snapshot = wait_for(app, lambda: (s if (s := session.snapshot()).terminal else None))
        assert not snapshot.stale and snapshot.request_id == 2
        assert all(item.state == "translated" for item in snapshot.items)
    finally:
        release.set()
        session.close()


def test_changed_frame_keeps_context_and_does_not_publish_the_old_translation(monkeypatch):
    app = QApplication.instance() or QApplication([])
    prompts, _ = install_transport(monkeypatch)

    class ChangingOcr:
        def recognize_frame(self, frame):
            text = "ベトナム" if frame[0, 0, 0] else "アンゴラ"
            return (observation(text, 10, 10, 150, 30),)

    capture = Capture()
    session = create_processing_session(configuration(), app=app, ocr=ChangingOcr(), profile=None,
        capture_output_size=capture.output_size, capture_region=capture.region, capture_backend="test")
    try:
        session.submit_frame(capture.frame, 1)
        first = wait_for(app, lambda: (s if (s := session.snapshot()).terminal else None))
        assert first.items[0].translated_text == "安哥拉"
        changed = capture.frame.copy()
        changed[0, 0, 0] = 1
        session.submit_frame(changed, 2)
        assert session.snapshot().pending
        second = wait_for(app, lambda: (s if (s := session.snapshot()).terminal else None))
        assert [(item.source.text, item.translated_text) for item in second.items
                if item.state == "translated"] == [("ベトナム", "越南")]
        assert len(prompts) == 2 and "原文：アンゴラ" in prompts[-1]
    finally:
        session.close()


@pytest.mark.parametrize("fail", [False, True])
def test_empty_and_failed_ocr_are_terminal(fail):
    app = QApplication.instance() or QApplication([])

    class Ocr:
        def recognize_frame(self, frame):
            if fail:
                raise RuntimeError("test OCR error")
            return ()

    capture = Capture()
    session = create_processing_session(configuration(), app=app, ocr=Ocr(), profile=None,
        capture_output_size=capture.output_size, capture_region=capture.region, capture_backend="test")
    try:
        session.submit_frame(capture.frame, 1)
        snapshot = wait_for(app, lambda: (s if (s := session.snapshot()).terminal else None))
        assert bool(snapshot.error) is fail
        assert not snapshot.items
    finally:
        session.close()


def test_benchmark_reset_clears_processing_without_resetting_roi_trigger(monkeypatch):
    app = QApplication.instance() or QApplication([])
    install_transport(monkeypatch)
    capture, ports = Capture(), Ports()
    controller = LiveController(configuration(dynamic_roi=True), capture=capture, ocr=SceneOcr(),
        overlay=ports, control=ports, app=app)
    try:
        session = controller.processing_session
        wait_for(app, lambda: (s if (s := session.snapshot()).terminal and s.items else None), tick=controller._tick)
        detector, scheduler = controller._detector, controller._roi_scheduler
        force_scan = controller._force_full_scan
        assert session.snapshot().statistics.model_results > 0
        session.reset_attempt()
        assert controller._detector is detector and controller._roi_scheduler is scheduler
        assert controller._force_full_scan == force_scan
        snapshot = session.snapshot()
        assert not snapshot.items and not snapshot.pending
        assert not any(asdict(snapshot.statistics).values())
        assert not controller._context
    finally:
        controller.close()


def test_frozen_request_waits_for_layout_arbitration_before_mapping(monkeypatch):
    app = QApplication.instance() or QApplication([])
    install_transport(monkeypatch)
    translate_complete = OpenAICompatibleTransport.complete
    entered, release = threading.Event(), threading.Event()

    class AmbiguousOcr:
        def recognize_frame(self, frame):
            return (
                observation("静かな夜に僕たちは", 40, 40, 400, 80),
                observation("古い約束の意味を探し", 40, 86, 400, 126),
                observation("歩き続けていた。", 40, 132, 360, 172),
            )

    async def complete(transport, prompt):
        if "allowed_joins" in prompt:
            entered.set()
            assert release.wait(3)
            return '{"groups":[[1,2,3]]}'
        return await translate_complete(transport, prompt)

    monkeypatch.setattr(OpenAICompatibleTransport, "complete", complete)
    config = configuration()
    config = replace(config, ocr=replace(config.ocr, text_merge_llm_arbitration_enabled=True))
    session = create_processing_session(config, app=app, ocr=AmbiguousOcr(), profile=None,
        capture_output_size=(600, 200), capture_region=(0, 0, 600, 200), capture_backend="test")
    try:
        session.submit_frame(np.zeros((200, 600, 3), dtype=np.uint8), 1)
        wait_for(app, entered.is_set)
        assert session.snapshot().pending and not session.snapshot().terminal
        release.set()
        snapshot = wait_for(app, lambda: (s if (s := session.snapshot()).terminal else None))
        assert len(snapshot.items) == 1
        assert snapshot.items[0].source.text == "静かな夜に僕たちは\n古い約束の意味を探し\n歩き続けていた。"
        assert snapshot.items[0].state == "translated"
    finally:
        release.set()
        session.close()


def test_frozen_request_refills_shared_batch_queue_until_all_items_are_mapped(monkeypatch):
    app = QApplication.instance() or QApplication([])
    translations = {"アンゴラ": "安哥拉", "ベトナム": "越南", "カナダ": "加拿大", "フランス": "法国"}

    class TableOcr:
        calls = 0

        def recognize_frame(self, frame):
            self.calls += 1
            return tuple(observation(text, 10, 5+i*28, 150, 23+i*28)
                         for i, text in enumerate(translations))

    async def complete(transport, prompt):
        source = ET.fromstring(prompt[prompt.index("<source>"):])
        assert len(source) == 1
        return f'<target><sn id="1">{translations[source[0].text]}</sn></target>'

    monkeypatch.setattr(OpenAICompatibleTransport, "complete", complete)
    config = configuration()
    config = replace(config, live=replace(config.live, max_batch_size=1),
                     ocr=replace(config.ocr, text_merge_enabled=False))
    ocr, capture = TableOcr(), Capture()
    session = create_processing_session(config, app=app, ocr=ocr, profile=None,
        capture_output_size=capture.output_size, capture_region=capture.region, capture_backend="test")
    try:
        session.submit_frame(capture.frame, 1)
        snapshot = wait_for(app, lambda: (s if (s := session.snapshot()).terminal else None))
        assert {item.source.text: item.translated_text for item in snapshot.items} == translations
        assert all(item.state == "translated" for item in snapshot.items)
        count = ocr.calls
        until = time.monotonic() + .08
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(.003)
        assert ocr.calls == count
    finally:
        session.close()

from __future__ import annotations

import json

import numpy as np
import pytest

from game_screen_translator.live.snapshot import (
    CacheHit,
    LastRunSnapshot,
    SnapshotEntry,
    load_snapshot,
    new_snapshot,
    save_snapshot,
    snapshot_path,
)
from game_screen_translator.config import AppConfig, TranslationConfig
from game_screen_translator.domain import TranslationResult
from game_screen_translator.live.runtime import LiveController
from game_screen_translator.ocr.types import OcrText
from game_screen_translator.profiles import create_game_profile


class _Capture:
    region = (0, 0, 320, 120)
    active_backend = "fake"

    def close(self) -> None:
        pass


class _Ocr:
    def recognize_frame(self, _frame):
        return ()


class _Overlay:
    def set_scene(self, _frame, _tracks) -> None:
        pass


class _Control:
    def set_status(self, *_args) -> None:
        pass

    def set_latency(self, *_args) -> None:
        pass


def _controller_with_profile(tmp_path):
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    config = AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="test-model",
        )
    )
    profile = create_game_profile(tmp_path / "config.toml", config, "demo")
    return LiveController(
        config,
        capture=_Capture(),
        ocr=_Ocr(),
        overlay=_Overlay(),
        control=_Control(),
        app=app,
        profile=profile,
    )


def _snapshot(source: str = "原文") -> LastRunSnapshot:
    return new_snapshot(
        (
            SnapshotEntry(
                track_id="track-1",
                revision=2,
                source_text=source,
                translated_text="译文",
                confidence=0.98,
                bounds=(10, 20, 110, 60),
            ),
        ),
        (CacheHit("命中原文", 3),),
        ocr_peak_seconds=0.125,
        llm_peak_seconds=1.75,
    )


def test_snapshot_round_trips_one_bounded_run(tmp_path) -> None:
    written = save_snapshot(tmp_path, _snapshot())

    assert written == snapshot_path(tmp_path)
    restored = load_snapshot(tmp_path)
    assert restored is not None
    assert restored.entries[0].source_text == "原文"
    assert restored.entries[0].bounds == (10, 20, 110, 60)
    assert restored.cache_hits == (CacheHit("命中原文", 3),)
    assert restored.ocr_peak_seconds == 0.125
    assert restored.llm_peak_seconds == 1.75


def test_new_snapshot_atomically_replaces_previous_content(tmp_path) -> None:
    save_snapshot(tmp_path, _snapshot("旧原文"))
    save_snapshot(tmp_path, _snapshot("新原文"))

    restored = load_snapshot(tmp_path)
    assert restored is not None
    assert [entry.source_text for entry in restored.entries] == ["新原文"]
    assert not list(tmp_path.glob(".last_run_snapshot.json.*.tmp"))


def test_malformed_snapshot_is_unavailable(tmp_path) -> None:
    path = snapshot_path(tmp_path)
    path.write_text(json.dumps({"version": 999}), encoding="utf-8")

    assert load_snapshot(tmp_path) is None


@pytest.mark.parametrize(
    ("field", "value"),
    (("track_id", 7), ("revision", "new"), ("confidence", "high"), ("bounds", 4)),
)
def test_malformed_snapshot_values_fail_closed(tmp_path, field, value) -> None:
    payload = _snapshot().to_dict()
    payload["entries"][0][field] = value
    snapshot_path(tmp_path).write_text(json.dumps(payload), encoding="utf-8")

    assert load_snapshot(tmp_path) is None


def test_snapshot_rejects_unbounded_entries() -> None:
    entries = tuple(
        SnapshotEntry(
            track_id=f"track-{index}",
            revision=0,
            source_text="原文",
            translated_text="译文",
            confidence=1.0,
            bounds=(0, 0, 1, 1),
        )
        for index in range(129)
    )

    try:
        new_snapshot(entries, (), ocr_peak_seconds=None, llm_peak_seconds=None)
    except ValueError as exc:
        assert "数量" in str(exc)
    else:  # pragma: no cover - assertion keeps the boundary explicit
        raise AssertionError("unbounded snapshot unexpectedly accepted")


def test_runtime_snapshot_uses_published_tracks_and_latency_peaks(tmp_path) -> None:
    controller = _controller_with_profile(tmp_path)
    update = controller._tracker.observe(
        (OcrText("原文", 0.9, ((10, 20), (110, 20), (110, 60), (10, 60))),),
        1.0,
    )
    source = update.stable_sources[0]
    controller._tracker.apply_translations((TranslationResult(source, "译文"),))
    controller._latency_stats.record_ocr(0.25)
    controller._latency_stats.record_translation(
        stability_seconds=0.1,
        queue_seconds=0.2,
        llm_seconds=0.75,
        total_seconds=1.1,
        batch_size=1,
    )
    controller._cache_hit_ranking["原文"] = 4

    controller._save_last_run_snapshot()
    restored = load_snapshot(controller._profile.directory)
    controller.close()

    assert restored is not None
    assert restored.entries[0].translated_text == "译文"
    assert restored.ocr_peak_seconds == 0.25
    assert restored.llm_peak_seconds == 0.75
    assert restored.cache_hits == (CacheHit("原文", 4),)


def test_runtime_snapshot_keeps_last_effective_local_canvas_after_scene_clears(
    tmp_path,
) -> None:
    controller = _controller_with_profile(tmp_path)
    controller._capture.region = (100, 200, 900, 500)
    controller._capture.output_size = (1920, 1080)
    update = controller._tracker.observe(
        (OcrText("局部原文", 0.9, ((10, 20), (110, 20), (110, 60), (10, 60))),),
        1.0,
    )
    controller._tracker.apply_translations(
        (TranslationResult(update.stable_sources[0], "局部译文"),)
    )
    controller._publish_scene(
        np.zeros((300, 800, 3), dtype=np.uint8), controller._tracker.visible_tracks
    )
    controller._publish_scene(None, ())
    controller._save_last_run_snapshot()

    restored = load_snapshot(controller._profile.directory)
    controller.close()

    assert restored is not None
    assert restored.entries[0].source_text == "局部原文"
    assert restored.canvas_size == (800, 300)


def test_runtime_snapshot_cache_top5_has_stable_tie_order(tmp_path) -> None:
    controller = _controller_with_profile(tmp_path)
    update = controller._tracker.observe(
        (OcrText("原文", 0.9, ((10, 20), (110, 20), (110, 60), (10, 60))),),
        1.0,
    )
    source = update.stable_sources[0]
    controller._tracker.apply_translations((TranslationResult(source, "译文"),))
    # This counter is populated only for automatic origins by the runtime;
    # ties must still be deterministic and manual/inflight results never enter it.
    controller._cache_hit_ranking.update(
        {
            "zeta": 2,
            "alpha": 2,
            "middle": 2,
            "one": 1,
            "two": 1,
            "three": 1,
            "manual-only": 99,
        }
    )
    controller._cache_hit_ranking.pop("manual-only")
    controller._save_last_run_snapshot()

    restored = load_snapshot(controller._profile.directory)
    controller.close()

    assert restored is not None
    assert restored.cache_hits == (
        CacheHit("alpha", 2),
        CacheHit("middle", 2),
        CacheHit("zeta", 2),
        CacheHit("one", 1),
        CacheHit("three", 1),
    )

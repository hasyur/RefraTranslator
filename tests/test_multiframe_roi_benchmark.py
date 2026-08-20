from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_SCRIPT = PROJECT_ROOT / "scripts" / "benchmark_multiframe_roi.py"


def _load_benchmark_module():
    spec = importlib.util.spec_from_file_location(
        "multiframe_roi_benchmark", BENCHMARK_SCRIPT
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BENCHMARK = _load_benchmark_module()


def _ocr(text: str, bounds: tuple[int, int, int, int]):
    left, top, right, bottom = bounds
    return BENCHMARK.OcrText(
        text,
        0.99,
        ((left, top), (right, top), (right, bottom), (left, bottom)),
    )


def test_partial_map_update_preserves_rows_inside_safety_crop() -> None:
    anchors = (
        BENCHMARK.AnchorSnapshot("line-1", "川岸に沿って進み、", (100, 200, 500, 240)),
        BENCHMARK.AnchorSnapshot("line-2", "失われた", (100, 270, 280, 310)),
    )
    region = BENCHMARK.ContextualOcrRegion(
        (60, 170, 520, 180),
        ((250, 265, 180, 55),),
        ("line-2",),
        ("line-1",),
        (),
    )
    plan = BENCHMARK.ContextualRoiPlan(
        (region,), 0.13, False, "contextual-local-change"
    )
    observations = (
        _ocr("川岸に沿って進み、", (100, 200, 500, 240)),
        _ocr("失われた鍵を探せ。", (100, 270, 470, 310)),
    )

    updated, _ = BENCHMARK._update_anchors(
        anchors,
        observations,
        (observations[1],),
        plan,
        next_track_index=3,
    )

    assert [item.text for item in updated] == [
        "川岸に沿って進み、",
        "失われた鍵を探せ。",
    ]


def test_exact_typewriter_completion_includes_punctuation() -> None:
    without_stop = (
        BENCHMARK.AnchorSnapshot("one", "門は真夜中に開く。", (0, 0, 100, 20)),
        BENCHMARK.AnchorSnapshot("two", "川岸に沿って進み、", (0, 30, 100, 50)),
        BENCHMARK.AnchorSnapshot("three", "失われた鍵を探せ", (0, 60, 100, 80)),
    )
    complete = (*without_stop[:-1], BENCHMARK.AnchorSnapshot(
        "three", "失われた鍵を探せ。", (0, 60, 100, 80)
    ))

    assert not BENCHMARK._contains_exact_lines(
        BENCHMARK.TYPEWRITER_EXPECTED, without_stop
    )
    assert BENCHMARK._contains_exact_lines(BENCHMARK.TYPEWRITER_EXPECTED, complete)

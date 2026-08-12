import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from game_screen_translator.ocr.paddle import (
    OcrResultError,
    PaddleOcrEngine,
    parse_paddle_results,
)


def test_parse_paddle_results_filters_by_confidence() -> None:
    payload = {
        "res": {
            "rec_texts": ["こんにちは", "noise"],
            "rec_scores": [0.95, 0.2],
            "rec_polys": [
                [[10, 20], [110, 20], [110, 50], [10, 50]],
                [[0, 0], [5, 0], [5, 5], [0, 5]],
            ],
        }
    }

    result = parse_paddle_results((payload,), min_score=0.6)

    assert len(result) == 1
    assert result[0].text == "こんにちは"
    assert result[0].bounds == (10, 20, 110, 50)


def test_parse_paddle_results_rejects_misaligned_arrays() -> None:
    payload = {
        "rec_texts": ["one"],
        "rec_scores": [],
        "rec_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
    }

    with pytest.raises(OcrResultError, match="数量不一致"):
        parse_paddle_results((payload,), min_score=0.0)


def test_engine_forces_project_local_model_cache(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    predict_calls: list[tuple[object, dict[str, object]]] = []

    class FakePaddleOcr:
        def __init__(self, **kwargs) -> None:
            calls.append(kwargs)

        def predict(self, source, **kwargs):
            predict_calls.append((source, kwargs))
            return ()

    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=FakePaddleOcr))
    for variable in (
        "PADDLE_PDX_CACHE_HOME",
        "PADDLE_PDX_MODEL_SOURCE",
        "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK",
        "PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT",
    ):
        monkeypatch.setenv(variable, "test-original")

    cache = tmp_path / "paddlex-cache"
    engine = PaddleOcrEngine(cache_dir=cache, cpu_threads=2, detection_max_side=1280)
    frame = object()
    assert engine.recognize_frame(frame) == ()

    assert Path(os.environ["PADDLE_PDX_CACHE_HOME"]) == cache.resolve()
    assert os.environ["PADDLE_PDX_MODEL_SOURCE"] == "bos"
    assert os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] == "True"
    assert os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] == "False"
    assert calls == [
        {
            "text_detection_model_name": "PP-OCRv6_small_det",
            "text_recognition_model_name": "PP-OCRv6_small_rec",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "device": "cpu",
            "enable_mkldnn": False,
            "cpu_threads": 2,
        }
    ]
    assert predict_calls == [
        (
            frame,
            {
                "text_det_limit_side_len": 1280,
                "text_det_limit_type": "max",
            },
        )
    ]

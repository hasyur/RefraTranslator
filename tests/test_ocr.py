import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from game_screen_translator.ocr import paddle as paddle_module

from game_screen_translator.ocr.paddle import (
    OcrResultError,
    PaddleOcrEngine,
    parse_paddle_results,
    validate_ocr_device,
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


def test_validate_gpu_device_reports_runtime(monkeypatch) -> None:
    fake_paddle = SimpleNamespace(
        __version__="3.3.1",
        device=SimpleNamespace(
            is_compiled_with_cuda=lambda: True,
            cuda=SimpleNamespace(device_count=lambda: 2),
        ),
        version=SimpleNamespace(cuda=lambda: "12.9"),
    )
    monkeypatch.setitem(sys.modules, "paddle", fake_paddle)
    monkeypatch.setattr(paddle_module, "_configure_bundled_nvidia_dlls", lambda: ())

    assert validate_ocr_device("gpu:1") == "gpu:1 · Paddle 3.3.1 · CUDA 12.9"


def test_validate_gpu_device_rejects_cpu_paddle(monkeypatch) -> None:
    fake_paddle = SimpleNamespace(
        device=SimpleNamespace(is_compiled_with_cuda=lambda: False),
    )
    monkeypatch.setitem(sys.modules, "paddle", fake_paddle)
    monkeypatch.setattr(paddle_module, "_configure_bundled_nvidia_dlls", lambda: ())

    with pytest.raises(paddle_module.OcrDependencyError, match="CPU 版 Paddle"):
        validate_ocr_device("gpu:0")

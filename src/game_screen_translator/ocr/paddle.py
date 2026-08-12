from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from game_screen_translator.ocr.types import OcrText, Point


class OcrDependencyError(RuntimeError):
    """Raised when optional PaddleOCR dependencies are unavailable."""


class OcrResultError(RuntimeError):
    """Raised when PaddleOCR returns an unsupported result shape."""


def _plain_payload(result: Any) -> Mapping[str, Any]:
    value = getattr(result, "json", result)
    if callable(value):
        value = value()
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        raise OcrResultError(f"无法识别的 PaddleOCR 结果类型：{type(value).__name__}")
    nested = value.get("res")
    return nested if isinstance(nested, Mapping) else value


def _points(value: Any) -> tuple[Point, ...]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise OcrResultError("OCR polygon 不是点数组")
    points: list[Point] = []
    for point in value:
        if hasattr(point, "tolist"):
            point = point.tolist()
        if not isinstance(point, Sequence) or len(point) < 2:
            raise OcrResultError("OCR polygon 中包含无效坐标")
        points.append((float(point[0]), float(point[1])))
    return tuple(points)


def parse_paddle_results(results: Iterable[Any], *, min_score: float) -> tuple[OcrText, ...]:
    observations: list[OcrText] = []
    for result in results:
        payload = _plain_payload(result)
        texts = payload.get("rec_texts", ())
        scores = payload.get("rec_scores", ())
        polygons = payload.get("rec_polys")
        if polygons is None:
            polygons = payload.get("dt_polys", ())
        if hasattr(texts, "tolist"):
            texts = texts.tolist()
        if hasattr(scores, "tolist"):
            scores = scores.tolist()
        if hasattr(polygons, "tolist"):
            polygons = polygons.tolist()
        if not all(isinstance(values, Sequence) for values in (texts, scores, polygons)):
            raise OcrResultError("PaddleOCR 结果缺少 rec_texts/rec_scores/rec_polys")
        if not (len(texts) == len(scores) == len(polygons)):
            raise OcrResultError("PaddleOCR 文本、分数与坐标数量不一致")
        for text, score, polygon in zip(texts, scores, polygons, strict=True):
            normalized_text = str(text).strip()
            confidence = float(score)
            if not normalized_text or confidence < min_score:
                continue
            observations.append(OcrText(normalized_text, confidence, _points(polygon)))
    return tuple(observations)


class PaddleOcrEngine:
    def __init__(
        self,
        *,
        language: str = "japan",
        min_score: float = 0.60,
        cache_dir: str | Path = ".cache/paddlex",
        detection_model: str = "PP-OCRv6_small_det",
        recognition_model: str = "PP-OCRv6_small_rec",
        model_source: str = "bos",
        cpu_threads: int = 2,
        detection_max_side: int = 1280,
    ) -> None:
        isolated_cache = Path(cache_dir).resolve()
        isolated_cache.mkdir(parents=True, exist_ok=True)
        # PaddleX reads this at import time. Set it before importing PaddleOCR so
        # model weights never fall back to the user-wide ~/.paddlex directory.
        os.environ["PADDLE_PDX_CACHE_HOME"] = str(isolated_cache)
        os.environ["PADDLE_PDX_MODEL_SOURCE"] = model_source
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        # Paddle 3.3.1 on Windows currently fails while converting oneDNN PIR
        # array attributes for PP-OCRv6. The plain CPU executor is stable.
        os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise OcrDependencyError(
                "尚未安装 OCR 可选依赖。请运行："
                ".\\bootstrap.ps1 -WithOcr"
            ) from exc

        self._min_score = min_score
        self._detection_max_side = detection_max_side
        try:
            self._engine = PaddleOCR(
                text_detection_model_name=detection_model,
                text_recognition_model_name=recognition_model,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                device="cpu",
                enable_mkldnn=False,
                cpu_threads=cpu_threads,
            )
        except Exception as exc:
            raise OcrDependencyError(
                f"无法初始化 PaddleOCR（语言={language}，检测={detection_model}，"
                f"识别={recognition_model}）：{exc}"
            ) from exc

    def recognize(self, image_path: str | Path) -> tuple[OcrText, ...]:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"找不到截图：{path}")
        results = self._predict(str(path))
        return parse_paddle_results(results, min_score=self._min_score)

    def recognize_frame(self, frame: Any) -> tuple[OcrText, ...]:
        results = self._predict(frame)
        return parse_paddle_results(results, min_score=self._min_score)

    def _predict(self, source: Any):
        # "max" prevents large full-screen frames from being upscaled and asks
        # PaddleOCR to restore polygons to the original coordinate system.
        return self._engine.predict(
            source,
            text_det_limit_side_len=self._detection_max_side,
            text_det_limit_type="max",
        )

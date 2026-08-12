from __future__ import annotations

from dataclasses import dataclass


Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class OcrText:
    text: str
    confidence: float
    polygon: tuple[Point, ...]

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("OCR 文本不能为空")
        if not 0 <= self.confidence <= 1:
            raise ValueError("OCR 置信度必须在 0 到 1 之间")
        if len(self.polygon) < 4:
            raise ValueError("OCR polygon 至少需要四个点")

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        xs = [point[0] for point in self.polygon]
        ys = [point[1] for point in self.polygon]
        return (
            int(min(xs)),
            int(min(ys)),
            int(max(xs) + 0.999),
            int(max(ys) + 0.999),
        )

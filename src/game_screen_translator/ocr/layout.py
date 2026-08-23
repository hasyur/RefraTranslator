from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from game_screen_translator.ocr.grouping import build_translation_groups
from game_screen_translator.ocr.types import OcrText


@dataclass(frozen=True, slots=True)
class _StaticOcrLine:
    track_id: str
    text: str
    confidence: float
    bounds: tuple[int, int, int, int]


def merge_ocr_text_blocks(
    observations: Iterable[OcrText],
    *,
    source_language: str = "japan",
) -> tuple[OcrText, ...]:
    """Stateless compatibility wrapper around the V2 translation grouper.

    Live translation uses stable OCR-line track IDs and a topology stabilizer.
    Static preview images have no cross-frame identity, so deterministic local
    IDs are sufficient while sharing the same grouping rules.
    """

    lines = tuple(
        _StaticOcrLine(
            f"static-line-{index}",
            observation.text,
            observation.confidence,
            observation.bounds,
        )
        for index, observation in enumerate(observations)
    )
    groups = build_translation_groups(
        lines,
        source_language=source_language,
        merge_enabled=True,
    )
    static_observations: list[OcrText] = []
    for group in groups:
        observation = group.observation
        static_observations.append(
            OcrText(
                observation.text,
                observation.confidence,
                observation.polygon,
            )
        )
    return tuple(static_observations)

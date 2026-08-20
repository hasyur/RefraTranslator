from __future__ import annotations

from typing import Any, Iterable

from game_screen_translator.ocr.types import OcrText


OcrRoi = tuple[int, int, int, int]


def resolve_ocr_roi(frame: Any, roi: OcrRoi) -> tuple[int, int, int, int]:
    """Resolve (left, top, width, height) to clipped edge coordinates."""
    if not hasattr(frame, "shape") or len(frame.shape) < 2:
        raise ValueError("ROI 输入必须是图像数组")
    frame_height, frame_width = int(frame.shape[0]), int(frame.shape[1])
    left, top, width, height = roi
    if width <= 0 or height <= 0:
        raise ValueError("OCR ROI 的宽和高必须大于 0")
    right, bottom = left + width, top + height
    if not (0 <= left < right <= frame_width and 0 <= top < bottom <= frame_height):
        raise ValueError(
            f"OCR ROI {roi} 超出图像 {frame_width}x{frame_height}"
        )
    return left, top, right, bottom


def crop_ocr_roi(frame: Any, roi: OcrRoi):
    """Return a contiguous high-resolution ROI and its full-frame origin."""
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("OCR ROI 需要 NumPy") from exc
    left, top, right, bottom = resolve_ocr_roi(frame, roi)
    return np.ascontiguousarray(frame[top:bottom, left:right]), (left, top)


def offset_ocr_texts(
    observations: Iterable[OcrText], *, left: int, top: int
) -> tuple[OcrText, ...]:
    """Map crop-local OCR polygons back into full-frame coordinates."""
    return tuple(
        OcrText(
            text=item.text,
            confidence=item.confidence,
            polygon=tuple((x + left, y + top) for x, y in item.polygon),
        )
        for item in observations
    )


def recognize_ocr_roi(engine: Any, frame: Any, roi: OcrRoi) -> tuple[OcrText, ...]:
    """Crop, recognize, then map results back to full-frame coordinates."""
    crop, (left, top) = crop_ocr_roi(frame, roi)
    return offset_ocr_texts(engine.recognize_frame(crop), left=left, top=top)


def recognize_ocr_rois(
    engine: Any,
    frame: Any,
    rois: Iterable[OcrRoi],
    *,
    edge_margin: int = 0,
) -> tuple[OcrText, ...]:
    """Recognize non-overlapping ROIs and return full-frame observations.

    When edge_margin is positive, observations touching an internal crop edge
    are discarded because they may be fragments of text outside that ROI.
    Edges that coincide with the original frame boundary remain valid.
    """
    if edge_margin < 0:
        raise ValueError("edge_margin 不能为负数")
    frame_height, frame_width = frame.shape[:2]
    observations: list[OcrText] = []
    for roi in rois:
        crop, (left, top) = crop_ocr_roi(frame, roi)
        local_observations = tuple(engine.recognize_frame(crop))
        if edge_margin:
            crop_height, crop_width = crop.shape[:2]
            local_observations = tuple(
                item
                for item in local_observations
                if not _touches_internal_roi_edge(
                    item,
                    left=left,
                    top=top,
                    crop_width=crop_width,
                    crop_height=crop_height,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    margin=edge_margin,
                )
            )
        observations.extend(offset_ocr_texts(local_observations, left=left, top=top))
    return tuple(sorted(observations, key=lambda item: (item.bounds[1], item.bounds[0])))


def _touches_internal_roi_edge(
    item: OcrText,
    *,
    left: int,
    top: int,
    crop_width: int,
    crop_height: int,
    frame_width: int,
    frame_height: int,
    margin: int,
) -> bool:
    item_left, item_top, item_right, item_bottom = item.bounds
    return (
        (left > 0 and item_left <= margin)
        or (top > 0 and item_top <= margin)
        or (left + crop_width < frame_width and item_right >= crop_width - margin)
        or (top + crop_height < frame_height and item_bottom >= crop_height - margin)
    )

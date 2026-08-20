from __future__ import annotations

from typing import TypeAlias

import numpy as np
from PIL import Image, ImageFilter


Bounds: TypeAlias = tuple[int, int, int, int]
BackgroundPatch: TypeAlias = tuple[Bounds, np.ndarray]


def render_background_patch(
    frame: np.ndarray,
    bounds: Bounds,
    *,
    blur_radius: float,
    overlay_opacity: float,
) -> BackgroundPatch | None:
    """Build the background drawn behind one translated OCR region.

    Blur-only mode first estimates the low-frequency game background from the
    clean edges around the OCR box. This prevents the source glyphs themselves
    from spreading into a grey or black-looking rectangle. Dark-blur mode keeps
    the historical direct blur and adds its configured black layer.
    """

    if blur_radius < 0:
        raise ValueError("blur_radius 不能为负数")
    if not 0 <= overlay_opacity <= 1:
        raise ValueError("overlay_opacity 必须在 0 到 1 之间")
    pixels = np.asarray(frame)
    if pixels.ndim != 3 or pixels.shape[2] < 3:
        return None
    height, width = pixels.shape[:2]
    if height < 1 or width < 1:
        return None
    left, top, right, bottom = bounds
    left = max(0, min(int(left), width - 1))
    right = max(left + 1, min(int(right), width))
    top = max(0, min(int(top), height - 1))
    bottom = max(top + 1, min(int(bottom), height))
    resolved_bounds = left, top, right, bottom

    crop = _rgb_crop(pixels, resolved_bounds)
    if blur_radius > 0:
        if overlay_opacity == 0:
            estimated = _estimate_background(
                pixels,
                resolved_bounds,
                blur_radius=blur_radius,
            )
            if estimated is not None:
                crop = estimated
        crop = np.asarray(
            Image.fromarray(crop).filter(ImageFilter.GaussianBlur(blur_radius))
        )
    if overlay_opacity > 0:
        processed = Image.fromarray(crop)
        crop = np.asarray(
            Image.blend(
                processed,
                Image.new("RGB", processed.size, (0, 0, 0)),
                overlay_opacity,
            )
        )
    return resolved_bounds, np.ascontiguousarray(crop)


def _rgb_crop(frame: np.ndarray, bounds: Bounds) -> np.ndarray:
    left, top, right, bottom = bounds
    crop = np.ascontiguousarray(frame[top:bottom, left:right, :3])
    if crop.dtype == np.uint8:
        return crop
    return np.clip(crop, 0, 255).astype(np.uint8)


def _estimate_background(
    frame: np.ndarray,
    bounds: Bounds,
    *,
    blur_radius: float,
) -> np.ndarray | None:
    left, top, right, bottom = bounds
    frame_height, frame_width = frame.shape[:2]
    patch_height = bottom - top
    patch_width = right - left
    band = max(2, min(8, round(blur_radius / 2)))

    top_band = frame[max(0, top - band) : top, left:right, :3]
    bottom_band = frame[bottom : min(frame_height, bottom + band), left:right, :3]
    left_band = frame[top:bottom, max(0, left - band) : left, :3]
    right_band = frame[top:bottom, right : min(frame_width, right + band), :3]

    vertical = _interpolate_rows(top_band, bottom_band, patch_height)
    horizontal = _interpolate_columns(left_band, right_band, patch_width)
    aspect_ratio = patch_width / max(1, patch_height)
    if aspect_ratio >= 1.25 and vertical is not None:
        estimated = vertical
    elif aspect_ratio <= 0.8 and horizontal is not None:
        estimated = horizontal
    elif vertical is not None and horizontal is not None:
        estimated = (vertical + horizontal) / 2
    else:
        estimated = vertical if vertical is not None else horizontal
    if estimated is None:
        return None
    return np.clip(np.rint(estimated), 0, 255).astype(np.uint8)


def _interpolate_rows(
    top_band: np.ndarray,
    bottom_band: np.ndarray,
    height: int,
) -> np.ndarray | None:
    top_line = _median_band(top_band, axis=0)
    bottom_line = _median_band(bottom_band, axis=0)
    if top_line is None and bottom_line is None:
        return None
    if top_line is None:
        top_line = bottom_line
    if bottom_line is None:
        bottom_line = top_line
    assert top_line is not None and bottom_line is not None
    weights = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    return top_line[None, :, :] * (1 - weights) + bottom_line[None, :, :] * weights


def _interpolate_columns(
    left_band: np.ndarray,
    right_band: np.ndarray,
    width: int,
) -> np.ndarray | None:
    left_line = _median_band(left_band, axis=1)
    right_line = _median_band(right_band, axis=1)
    if left_line is None and right_line is None:
        return None
    if left_line is None:
        left_line = right_line
    if right_line is None:
        right_line = left_line
    assert left_line is not None and right_line is not None
    weights = np.linspace(0, 1, width, dtype=np.float32)[None, :, None]
    return left_line[:, None, :] * (1 - weights) + right_line[:, None, :] * weights


def _median_band(values: np.ndarray, *, axis: int) -> np.ndarray | None:
    if not values.size:
        return None
    return np.median(values.astype(np.float32), axis=axis)

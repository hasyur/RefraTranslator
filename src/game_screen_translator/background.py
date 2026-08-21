from __future__ import annotations

import math
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

    Both display modes blur real pixels from an expanded game-frame crop. The
    expansion gives the Gaussian kernel genuine neighboring colors instead of
    forcing it to extrapolate from the OCR-box edge. Dark-blur mode only adds a
    black layer after that shared blur step.
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
        effective_radius = _effective_blur_radius(
            blur_radius,
            patch_height=bottom - top,
        )
        margin = max(1, math.ceil(effective_radius * 3))
        expanded_bounds = (
            max(0, left - margin),
            max(0, top - margin),
            min(width, right + margin),
            min(height, bottom + margin),
        )
        expanded = _rgb_crop(pixels, expanded_bounds)
        blurred = np.asarray(
            Image.fromarray(expanded).filter(
                ImageFilter.GaussianBlur(effective_radius)
            )
        )
        expanded_left, expanded_top, _, _ = expanded_bounds
        crop = blurred[
            top - expanded_top : bottom - expanded_top,
            left - expanded_left : right - expanded_left,
        ]
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


def _effective_blur_radius(configured: float, *, patch_height: int) -> float:
    adaptive = max(8.0, min(18.0, patch_height * 0.25))
    return max(configured, adaptive)

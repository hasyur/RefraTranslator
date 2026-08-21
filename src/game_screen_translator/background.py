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
    sample_step: int = 1,
) -> BackgroundPatch | None:
    """Build the background drawn behind one translated OCR region.

    Both display modes blur real pixels from an expanded game-frame crop. The
    expansion gives the Gaussian kernel genuine neighboring colors instead of
    forcing it to extrapolate from the OCR-box edge. Dark-blur mode only adds a
    black layer after that shared blur step. ``sample_step`` may reduce the
    live blur workload before filtering; the caller can scale the returned
    patch back over ``resolved_bounds`` when drawing it.
    """

    if blur_radius < 0:
        raise ValueError("blur_radius 不能为负数")
    if not 0 <= overlay_opacity <= 1:
        raise ValueError("overlay_opacity 必须在 0 到 1 之间")
    if sample_step < 1:
        raise ValueError("sample_step 必须至少为 1")
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
        expanded_left, expanded_top, expanded_right, expanded_bottom = (
            expanded_bounds
        )
        # Align the sampled grid with the requested patch. This preserves the
        # exact source-to-overlay mapping while still keeping neighboring
        # pixels around every side for the Gaussian kernel.
        sample_left = expanded_left + (left - expanded_left) % sample_step
        sample_top = expanded_top + (top - expanded_top) % sample_step
        sampled_bounds = (
            sample_left,
            sample_top,
            expanded_right,
            expanded_bottom,
        )
        expanded = _rgb_sample(pixels, sampled_bounds, step=sample_step)
        blurred = np.asarray(
            Image.fromarray(expanded).filter(
                ImageFilter.GaussianBlur(effective_radius / sample_step)
            )
        )
        crop_top = (top - sample_top) // sample_step
        crop_left = (left - sample_left) // sample_step
        crop_height = max(1, math.ceil((bottom - top) / sample_step))
        crop_width = max(1, math.ceil((right - left) / sample_step))
        crop = blurred[
            crop_top : crop_top + crop_height,
            crop_left : crop_left + crop_width,
        ]
    else:
        # With blur disabled, keep the native pixels rather than turning a
        # dark-only overlay into a visibly pixelated background.
        crop = _rgb_crop(pixels, resolved_bounds)
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
    return _rgb_sample(frame, bounds, step=1)


def _rgb_sample(frame: np.ndarray, bounds: Bounds, *, step: int) -> np.ndarray:
    left, top, right, bottom = bounds
    crop = np.ascontiguousarray(frame[top:bottom:step, left:right:step, :3])
    if crop.dtype == np.uint8:
        return crop
    return np.clip(crop, 0, 255).astype(np.uint8)


def _effective_blur_radius(configured: float, *, patch_height: int) -> float:
    adaptive = max(8.0, min(18.0, patch_height * 0.25))
    return max(configured, adaptive)

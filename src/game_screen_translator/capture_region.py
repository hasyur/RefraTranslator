from __future__ import annotations

import math
from collections.abc import Sequence

RegionRatio = tuple[float, float, float, float]
FULL_SCREEN_REGION: RegionRatio = (0.0, 0.0, 1.0, 1.0)
LEGACY_REGION_FIELDS = frozenset({"left", "top", "width", "height"})


def validate_region_ratio(value: object) -> RegionRatio:
    """Validate monitor-relative left/top/width/height fractions."""
    if (
        not isinstance(value, (tuple, list))
        or len(value) != 4
        or any(type(part) not in (int, float) or not math.isfinite(part) for part in value)
    ):
        raise ValueError("区域比例必须是四个有限数字：LEFT,TOP,WIDTH,HEIGHT")
    left, top, width, height = map(float, value)
    if not (
        0 <= left < 1
        and 0 <= top < 1
        and 0 < width <= 1
        and 0 < height <= 1
        and left + width <= 1 + 1e-12
        and top + height <= 1 + 1e-12
    ):
        raise ValueError("区域比例必须在显示器范围内，宽高必须大于 0")
    return left, top, width, height


def region_to_pixels(
    ratio: RegionRatio, size: tuple[int, int],
) -> tuple[int, int, int, int]:
    """Resolve the original fractions against the current capture size (LTRB)."""
    left, top, width, height = validate_region_ratio(ratio)
    display_width, display_height = size
    if min(size) <= 0:
        raise ValueError("显示器尺寸必须大于 0")
    x = min(display_width - 1, round(left * display_width))
    y = min(display_height - 1, round(top * display_height))
    right = min(display_width, max(x + 1, round((left + width) * display_width)))
    bottom = min(display_height, max(y + 1, round((top + height) * display_height)))
    return x, y, right, bottom


def pixels_to_region_ratio(
    region: Sequence[int], size: tuple[int, int],
) -> RegionRatio:
    """Convert a physical-pixel selection (LTWH) to monitor fractions."""
    left, top, width, height = region
    display_width, display_height = size
    if min(size) <= 0:
        raise ValueError("显示器尺寸必须大于 0")
    if not (
        0 <= left < left + width <= display_width
        and 0 <= top < top + height <= display_height
    ):
        raise ValueError("框选区域必须是显示器内的非空矩形")
    return validate_region_ratio(
        (left / display_width, top / display_height, width / display_width, height / display_height)
    )

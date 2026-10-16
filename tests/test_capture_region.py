import pytest

from game_screen_translator.capture_region import (
    FULL_SCREEN_REGION,
    pixels_to_region_ratio,
    region_to_pixels,
    validate_region_ratio,
)


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((1920, 1080), (192, 756, 1728, 1026)),
        ((2560, 1440), (256, 1008, 2304, 1368)),
        ((3840, 2160), (384, 1512, 3456, 2052)),
    ],
)
def test_region_resolves_at_each_resolution(size, expected) -> None:
    ratio = pixels_to_region_ratio((192, 756, 1536, 270), (1920, 1080))
    assert ratio == (0.1, 0.7, 0.8, 0.25)
    assert region_to_pixels(ratio, size) == expected


def test_region_edges_round_inside_display_without_collapsing() -> None:
    assert region_to_pixels((0.9999, 0.9999, 0.0001, 0.0001), (800, 600)) == (
        799, 599, 800, 600,
    )
    assert region_to_pixels(FULL_SCREEN_REGION, (1, 1)) == (0, 0, 1, 1)
    ratio = pixels_to_region_ratio((71, 81, 1850, 1000), (1921, 1081))
    assert region_to_pixels(ratio, (1921, 1081)) == (71, 81, 1921, 1081)


@pytest.mark.parametrize(
    "value",
    [
        None, "0,0,1,1", (0, 0, 1), (False, 0, 1, 1), (0, 0, "1", 1),
        (0, 0, float("nan"), 1), (0, 0, float("inf"), 1),
        (-0.1, 0, 1, 1), (0, 0, 0, 1), (0.8, 0, 0.3, 1), (0, 0.9, 1, 0.2),
    ],
)
def test_invalid_region_ratios_are_rejected(value) -> None:
    with pytest.raises(ValueError):
        validate_region_ratio(value)


def test_pixel_selection_requires_a_valid_capture_size_and_bounds() -> None:
    with pytest.raises(ValueError):
        pixels_to_region_ratio((0, 0, 100, 100), (0, 1080))
    with pytest.raises(ValueError):
        pixels_to_region_ratio((1800, 0, 200, 100), (1920, 1080))
    with pytest.raises(ValueError):
        region_to_pixels(FULL_SCREEN_REGION, (0, 1080))

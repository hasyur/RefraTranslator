import numpy as np

from game_screen_translator.background import render_background_patch


def test_blur_only_reconstructs_horizontal_text_background() -> None:
    height, width = 120, 320
    background = np.empty((height, width, 3), dtype=np.uint8)
    for y in range(height):
        background[y, :, :] = (60 + y // 2, 40 + y // 3, 50 + y // 4)
    frame = background.copy()
    frame[52:68, 50:270, :] = 240

    rendered = render_background_patch(
        frame,
        (36, 26, 284, 94),
        blur_radius=8,
        overlay_opacity=0.0,
    )

    assert rendered is not None
    bounds, patch = rendered
    assert bounds == (36, 26, 284, 94)
    expected = background[60, 160].astype(int)
    actual = patch[60 - bounds[1], 160 - bounds[0]].astype(int)
    assert np.max(np.abs(actual - expected)) <= 2


def test_blur_only_reconstructs_vertical_text_background() -> None:
    height, width = 140, 240
    background = np.empty((height, width, 3), dtype=np.uint8)
    for x in range(width):
        background[:, x, :] = (50 + x // 3, 45 + x // 4, 40 + x // 5)
    frame = background.copy()
    frame[25:115, 108:124, :] = 240

    rendered = render_background_patch(
        frame,
        (90, 16, 142, 124),
        blur_radius=8,
        overlay_opacity=0.0,
    )

    assert rendered is not None
    bounds, patch = rendered
    expected = background[70, 116].astype(int)
    actual = patch[70 - bounds[1], 116 - bounds[0]].astype(int)
    assert np.max(np.abs(actual - expected)) <= 2


def test_dark_blur_keeps_direct_crop_and_adds_black_layer() -> None:
    frame = np.full((100, 240, 3), (200, 120, 80), dtype=np.uint8)

    rendered = render_background_patch(
        frame,
        (30, 20, 210, 80),
        blur_radius=0,
        overlay_opacity=0.55,
    )

    assert rendered is not None
    _, patch = rendered
    assert tuple(patch[0, 0]) == (90, 54, 36)


def test_dark_blur_preserves_historical_source_glyph_blur() -> None:
    frame = np.full((120, 320, 3), (100, 120, 140), dtype=np.uint8)
    frame[52:68, 50:270, :] = 240

    rendered = render_background_patch(
        frame,
        (36, 26, 284, 94),
        blur_radius=8,
        overlay_opacity=0.55,
    )

    assert rendered is not None
    _, patch = rendered
    assert tuple(patch[2, 2]) == (45, 54, 63)
    assert patch[34, 124, 0] >= 80


def test_background_patch_clamps_bounds_at_frame_edge() -> None:
    frame = np.full((20, 30, 3), (80, 90, 100), dtype=np.uint8)

    rendered = render_background_patch(
        frame,
        (-10, -5, 15, 12),
        blur_radius=8,
        overlay_opacity=0.0,
    )

    assert rendered is not None
    bounds, patch = rendered
    assert bounds == (0, 0, 15, 12)
    assert patch.shape == (12, 15, 3)
    assert tuple(patch[6, 7]) == (80, 90, 100)


def test_background_patch_rejects_empty_frame() -> None:
    assert (
        render_background_patch(
            np.empty((0, 0, 3), dtype=np.uint8),
            (0, 0, 1, 1),
            blur_radius=8,
            overlay_opacity=0.0,
        )
        is None
    )

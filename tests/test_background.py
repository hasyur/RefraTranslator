import numpy as np

from game_screen_translator.background import render_background_patch


def test_blur_only_preserves_real_multicolor_layout() -> None:
    frame = np.empty((120, 320, 3), dtype=np.uint8)
    frame[:, :160] = (220, 40, 30)
    frame[:, 160:] = (30, 50, 220)

    rendered = render_background_patch(
        frame,
        (40, 20, 280, 100),
        blur_radius=8,
        overlay_opacity=0.0,
    )

    assert rendered is not None
    bounds, patch = rendered
    assert bounds == (40, 20, 280, 100)
    left_color = patch[40, 20].astype(int)
    right_color = patch[40, 220].astype(int)
    assert left_color[0] > left_color[2] + 100
    assert right_color[2] > right_color[0] + 100


def test_blur_uses_real_pixels_outside_the_requested_patch() -> None:
    frame = np.empty((100, 240, 3), dtype=np.uint8)
    frame[:, :120] = (220, 40, 30)
    frame[:, 120:] = (30, 50, 220)

    rendered = render_background_patch(
        frame,
        (80, 20, 110, 80),
        blur_radius=8,
        overlay_opacity=0.0,
    )

    assert rendered is not None
    _, patch = rendered
    assert patch[30, -1, 2] > 30


def test_strong_direct_blur_suppresses_source_glyph_contrast() -> None:
    frame = np.full((120, 320, 3), (30, 40, 50), dtype=np.uint8)
    for left in range(80, 240, 8):
        frame[45:75, left : left + 4] = 240

    rendered = render_background_patch(
        frame,
        (60, 30, 260, 90),
        blur_radius=8,
        overlay_opacity=0.0,
    )

    assert rendered is not None
    _, patch = rendered
    center_line = patch[30, 40:160, 0].astype(int)
    assert np.ptp(center_line) <= 12


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


def test_dark_blur_uses_the_same_direct_source_glyph_blur() -> None:
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
    assert np.max(np.abs(patch[2, 2].astype(int) - (45, 54, 63))) <= 2
    assert patch[34, 124, 0] >= 60


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


def test_sampled_blur_reduces_pixel_count_and_preserves_color_layout() -> None:
    frame = np.empty((120, 320, 3), dtype=np.uint8)
    frame[:, :160] = (220, 40, 30)
    frame[:, 160:] = (30, 50, 220)

    rendered = render_background_patch(
        frame,
        (40, 20, 280, 100),
        blur_radius=8,
        overlay_opacity=0.0,
        sample_step=6,
    )

    assert rendered is not None
    bounds, patch = rendered
    assert bounds == (40, 20, 280, 100)
    assert patch.shape == (14, 40, 3)
    left_color = patch[7, 3].astype(int)
    right_color = patch[7, -4].astype(int)
    assert left_color[0] > left_color[2] + 100
    assert right_color[2] > right_color[0] + 100


def test_sampled_blur_still_suppresses_source_glyph_contrast() -> None:
    frame = np.full((120, 320, 3), (30, 40, 50), dtype=np.uint8)
    for left in range(80, 240, 8):
        frame[45:75, left : left + 4] = 240

    rendered = render_background_patch(
        frame,
        (60, 30, 260, 90),
        blur_radius=8,
        overlay_opacity=0.0,
        sample_step=6,
    )

    assert rendered is not None
    _, patch = rendered
    assert patch.shape == (10, 34, 3)
    assert np.ptp(patch[5, 7:27, 0].astype(int)) <= 20


def test_sample_step_does_not_reduce_unblurred_patch() -> None:
    frame = np.full((40, 60, 3), (80, 90, 100), dtype=np.uint8)

    rendered = render_background_patch(
        frame,
        (10, 5, 50, 35),
        blur_radius=0,
        overlay_opacity=0.55,
        sample_step=6,
    )

    assert rendered is not None
    _, patch = rendered
    assert patch.shape == (30, 40, 3)


def test_background_patch_rejects_invalid_sample_step() -> None:
    frame = np.full((20, 30, 3), (80, 90, 100), dtype=np.uint8)

    try:
        render_background_patch(
            frame,
            (0, 0, 10, 10),
            blur_radius=8,
            overlay_opacity=0.0,
            sample_step=0,
        )
    except ValueError as exc:
        assert "sample_step" in str(exc)
    else:
        raise AssertionError("sample_step=0 should fail")


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

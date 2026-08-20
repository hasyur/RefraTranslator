import numpy as np
import pytest

from game_screen_translator.ocr.dynamic_roi import FullScreenRoiDetector


def _detector(**overrides) -> FullScreenRoiDetector:
    options = {
        "sample_size": (80, 45),
        "tile_size": (2, 2),
        "min_changed_samples": 1,
        "tile_dilation": 0,
        "padding": (10, 6),
        "min_roi_size": (80, 32),
        "merge_gap": (4, 4),
    }
    options.update(overrides)
    return FullScreenRoiDetector(**options)


def test_unchanged_frame_proposes_no_ocr() -> None:
    frame = np.full((180, 320, 3), 30, dtype=np.uint8)

    proposal = _detector().propose(frame, frame.copy())

    assert proposal.rois == ()
    assert proposal.reason == "unchanged"
    assert not proposal.fallback_full_frame


def test_local_text_like_change_proposes_clipped_context_roi() -> None:
    before = np.zeros((180, 320, 3), dtype=np.uint8)
    after = before.copy()
    after[78:94, 250:300] = 255

    proposal = _detector().propose(before, after)

    assert proposal.reason == "local-change"
    assert not proposal.fallback_full_frame
    assert len(proposal.rois) == 1
    left, top, width, height = proposal.rois[0]
    assert left <= 250 < left + width
    assert top <= 78 < top + height
    assert width >= 80
    assert height >= 32
    assert left + width <= 320
    assert top + height <= 180
    seed_left, seed_top, seed_width, seed_height = proposal.change_rois[0]
    assert seed_left <= 250 < seed_left + seed_width
    assert seed_top <= 78 < seed_top + seed_height
    assert seed_width <= width
    assert seed_height <= height
    assert proposal.candidate_coverage_fraction == proposal.coverage_fraction
    assert proposal.candidate_region_count == 1


def test_default_change_limit_falls_back_for_moderate_structural_change() -> None:
    before = np.zeros((180, 320, 3), dtype=np.uint8)
    after = before.copy()
    after[:, :128] = 255

    proposal = _detector(max_coverage_fraction=1.0).propose(before, after)

    assert proposal.changed_fraction == pytest.approx(0.4)
    assert proposal.reason == "widespread-change"
    assert proposal.fallback_full_frame


def test_default_coverage_limit_falls_back_for_large_single_candidate() -> None:
    before = np.zeros((180, 320, 3), dtype=np.uint8)
    after = before.copy()
    after[80:88, 150:158] = 255

    proposal = FullScreenRoiDetector().propose(before, after)

    assert 0.45 < proposal.candidate_coverage_fraction < 0.80
    assert proposal.reason == "roi-coverage-too-large"
    assert proposal.fallback_full_frame


def test_uniform_brightness_shift_is_removed_before_region_detection() -> None:
    before = np.full((180, 320, 3), 40, dtype=np.uint8)
    after = np.full((180, 320, 3), 60, dtype=np.uint8)

    proposal = _detector().propose(before, after)

    assert proposal.rois == ()
    assert proposal.reason == "unchanged"


def test_last_accepted_baseline_accumulates_subthreshold_local_changes() -> None:
    baseline = np.zeros((180, 320, 3), dtype=np.uint8)
    faint = baseline.copy()
    visible = baseline.copy()
    faint[78:94, 120:200] = 8
    visible[78:94, 120:200] = 16
    detector = _detector(pixel_threshold=14)

    first_adjacent = detector.propose(baseline, faint)
    second_adjacent = detector.propose(faint, visible)
    accumulated = detector.propose(baseline, visible)

    assert first_adjacent.reason == "unchanged"
    assert second_adjacent.reason == "unchanged"
    assert accumulated.reason == "local-change"
    assert accumulated.rois


def test_widespread_structural_change_falls_back_to_full_frame() -> None:
    before = np.zeros((180, 320, 3), dtype=np.uint8)
    after = before.copy()
    after[:, :160] = 255

    proposal = _detector(full_frame_change_fraction=0.2).propose(before, after)

    assert proposal.rois == ((0, 0, 320, 180),)
    assert proposal.fallback_full_frame
    assert proposal.reason == "widespread-change"
    assert proposal.candidate_coverage_fraction == 1.0
    assert proposal.candidate_region_count == 1


def test_too_many_isolated_regions_fall_back_instead_of_dropping_changes() -> None:
    before = np.zeros((180, 320, 3), dtype=np.uint8)
    after = before.copy()
    for left, top in ((10, 10), (110, 10), (210, 10), (10, 130)):
        after[top : top + 8, left : left + 8] = 255

    proposal = _detector(
        padding=(0, 0),
        min_roi_size=(8, 8),
        merge_gap=(0, 0),
        max_rois=2,
    ).propose(before, after)

    assert proposal.rois == ((0, 0, 320, 180),)
    assert proposal.fallback_full_frame
    assert proposal.reason == "too-many-regions"
    assert proposal.candidate_region_count > 2


def test_mismatched_frames_are_rejected() -> None:
    with pytest.raises(ValueError, match="尺寸必须一致"):
        _detector().propose(
            np.zeros((10, 10, 3), dtype=np.uint8),
            np.zeros((10, 11, 3), dtype=np.uint8),
        )

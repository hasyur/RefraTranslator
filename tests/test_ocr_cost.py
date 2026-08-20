import pytest

from game_screen_translator.ocr.cost import (
    OcrComputeStats,
    estimate_ocr_compute_cost,
)


def test_full_frame_cost_uses_paddle_max_side_resize() -> None:
    estimate = estimate_ocr_compute_cost(
        (2560, 1440),
        detection_max_side=1280,
        executed_rois=None,
    )

    assert estimate.executed_full_frame
    assert estimate.executed.call_count == 1
    assert estimate.executed.source_pixels == 2560 * 1440
    assert estimate.executed.detector_pixels == 1280 * 720
    assert estimate.executed_to_full_ratio == 1.0
    assert estimate.candidate_to_full_ratio == 1.0


def test_multiple_square_rois_can_have_more_detector_pixels_than_full_frame() -> None:
    rois = ((0, 0, 1200, 1000), (1200, 0, 200, 200))

    estimate = estimate_ocr_compute_cost(
        (2560, 1440),
        detection_max_side=1280,
        executed_rois=rois,
    )

    assert not estimate.executed_full_frame
    assert estimate.executed.call_count == 2
    assert estimate.executed.source_pixels == 1_240_000
    assert estimate.executed.detector_pixels == 1_240_000
    assert estimate.executed_to_full_ratio == pytest.approx(1_240_000 / 921_600)


def test_full_frame_fallback_retains_candidate_roi_cost() -> None:
    candidate_rois = ((0, 0, 1200, 1000), (1200, 0, 200, 200))

    estimate = estimate_ocr_compute_cost(
        (2560, 1440),
        detection_max_side=1280,
        executed_rois=None,
        candidate_rois=candidate_rois,
    )

    assert estimate.executed.call_count == 1
    assert estimate.executed.detector_pixels == 921_600
    assert estimate.candidate.call_count == 2
    assert estimate.candidate.detector_pixels == 1_240_000
    assert estimate.candidate_to_full_ratio > 1.0


def test_cost_stats_report_roi_candidates_that_exceed_full_frame() -> None:
    stats = OcrComputeStats()
    baseline = estimate_ocr_compute_cost(
        (2560, 1440),
        detection_max_side=1280,
        executed_rois=None,
    )
    fallback = estimate_ocr_compute_cost(
        (2560, 1440),
        detection_max_side=1280,
        executed_rois=None,
        candidate_rois=((0, 0, 1200, 1000), (1200, 0, 200, 200)),
    )

    stats.record(baseline, is_dynamic_roi=False)
    stats.record(fallback, is_dynamic_roi=True)

    assert stats.candidate_more_expensive_count == 1
    assert stats.candidate_ratio_peak == pytest.approx(1_240_000 / 921_600)
    assert "执行整屏 1 次" in stats.render()
    assert "候选 ROI 2 次" in stats.render()
    assert "像素高于整屏 1 轮" in stats.summary()


def test_cost_estimate_rejects_out_of_frame_roi() -> None:
    with pytest.raises(ValueError, match="超出图像"):
        estimate_ocr_compute_cost(
            (800, 600),
            detection_max_side=1280,
            executed_rois=((700, 500, 200, 200),),
        )

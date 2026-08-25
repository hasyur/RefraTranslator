from __future__ import annotations

import numpy as np
import pytest

from game_screen_translator.ocr.dynamic_roi import FullScreenRoiDetector
from game_screen_translator.ocr.roi_scheduler import LatestFrameRoiScheduler


def _detector() -> FullScreenRoiDetector:
    return FullScreenRoiDetector(
        sample_size=(80, 45),
        pixel_threshold=14,
        tile_size=(2, 2),
        min_changed_samples=1,
        tile_dilation=0,
        padding=(8, 4),
        min_roi_size=(32, 24),
        merge_gap=(0, 0),
        max_rois=6,
        max_coverage_fraction=0.45,
        full_frame_change_fraction=0.22,
    )


def _blank() -> np.ndarray:
    return np.zeros((180, 320, 3), dtype=np.uint8)


def _paint(
    frame: np.ndarray, left: int, top: int, width: int = 24, height: int = 16
) -> np.ndarray:
    result = frame.copy()
    result[top : top + height, left : left + width] = 255
    return result


def _contains(roi, x: int, y: int) -> bool:
    left, top, width, height = roi
    return left <= x < left + width and top <= y < top + height


def test_coalesces_10hz_observations_until_the_3hz_ocr_slot() -> None:
    base = _blank()
    first = _paint(base, 40, 70)
    second = _paint(first, 240, 70)
    scheduler = LatestFrameRoiScheduler(
        _detector(),
        min_ocr_interval_s=1.0 / 3.0,
        settle_interval_s=0.18,
        max_coalesce_s=1.0 / 3.0,
    )
    scheduler.prime(base, 0.0)

    assert scheduler.observe(first, 0.1) is None
    assert scheduler.observe(second, 0.2) is None
    assert scheduler.observe(second.copy(), 0.3) is None
    job = scheduler.observe(second.copy(), 0.4)

    assert job is not None
    assert job.trigger_reason == "settled"
    assert job.change_started_at_s == 0.1
    assert job.last_changed_at_s == 0.2
    assert job.observed_at_s == 0.4
    assert np.array_equal(job.frame, second)
    assert not job.proposal.fallback_full_frame
    assert any(_contains(roi, 45, 75) for roi in job.proposal.change_rois)
    assert any(_contains(roi, 245, 75) for roi in job.proposal.change_rois)


def test_each_observed_frame_is_sampled_only_once(monkeypatch) -> None:
    detector = _detector()
    sample_calls = 0
    original_sample_frame = detector.sample_frame

    def sample_frame(frame: np.ndarray):
        nonlocal sample_calls
        sample_calls += 1
        return original_sample_frame(frame)

    monkeypatch.setattr(detector, "sample_frame", sample_frame)
    scheduler = LatestFrameRoiScheduler(
        detector,
        min_ocr_interval_s=0.4,
        settle_interval_s=0.1,
        max_coalesce_s=0.4,
    )
    base = _blank()
    scheduler.prime(base, 0.0)
    scheduler.observe(_paint(base, 40, 70), 0.1)
    scheduler.observe(_paint(base, 120, 70), 0.2)
    scheduler.observe(_paint(base, 200, 70), 0.3)

    assert sample_calls == 4


def test_latest_wins_keeps_only_one_pending_frame_while_ocr_is_busy() -> None:
    base = _blank()
    first = _paint(base, 40, 70)
    third = _paint(first, 140, 70)
    latest = _paint(third, 240, 70)
    scheduler = LatestFrameRoiScheduler(
        _detector(),
        min_ocr_interval_s=0.3,
        settle_interval_s=0.15,
        max_coalesce_s=0.3,
    )
    scheduler.prime(base, 0.0)
    assert scheduler.observe(first, 0.1) is None
    assert scheduler.observe(first.copy(), 0.2) is None
    first_job = scheduler.observe(first.copy(), 0.3)
    assert first_job is not None

    assert scheduler.observe(third, 0.4) is None
    assert scheduler.observe(latest, 0.5) is None
    assert scheduler.busy
    assert not scheduler.is_latest(first_job)
    assert scheduler.complete(first_job, accepted=True, completed_at_s=0.5) is None

    assert scheduler.observe(latest.copy(), 0.6) is None
    latest_job = scheduler.observe(latest.copy(), 0.7)
    assert latest_job is not None
    assert latest_job.generation == scheduler.latest_generation
    assert np.array_equal(latest_job.frame, latest)


def test_full_frame_fallback_stays_sticky_until_successful_ocr() -> None:
    base = _blank()
    widespread = base.copy()
    widespread[:, :160] = 255
    latest = _paint(base, 240, 70)
    scheduler = LatestFrameRoiScheduler(
        _detector(),
        min_ocr_interval_s=0.3,
        settle_interval_s=0.15,
        max_coalesce_s=0.3,
    )
    scheduler.prime(base, 0.0)

    assert scheduler.observe(widespread, 0.1) is None
    assert scheduler.observe(latest, 0.2) is None
    assert scheduler.observe(latest.copy(), 0.3) is None
    job = scheduler.observe(latest.copy(), 0.4)

    assert job is not None
    assert job.proposal.fallback_full_frame
    assert job.proposal.rois == ((0, 0, 320, 180),)
    assert job.proposal.reason == "widespread-change"
    assert job.proposal.candidate_coverage_fraction == 1.0
    assert job.proposal.candidate_region_count == 1


def test_rejected_ocr_does_not_consume_the_pending_change() -> None:
    base = _blank()
    changed = _paint(base, 120, 70)
    scheduler = LatestFrameRoiScheduler(
        _detector(),
        min_ocr_interval_s=0.1,
        settle_interval_s=0.0,
        max_coalesce_s=0.1,
    )
    scheduler.prime(base, 0.0)

    first_job = scheduler.observe(changed, 0.1)
    assert first_job is not None
    with pytest.raises(ValueError, match="失败的 OCR"):
        scheduler.complete(
            first_job,
            accepted=False,
            completed_at_s=0.1,
            target_count=0,
        )
    assert scheduler.complete(
        first_job, accepted=False, completed_at_s=0.1
    ) is None
    assert scheduler.has_pending

    retry = scheduler.observe(changed.copy(), 0.2)
    assert retry is not None
    assert np.array_equal(retry.frame, changed)


def test_rejected_ocr_can_wait_for_a_fresh_observation_before_retry() -> None:
    base = _blank()
    changed = _paint(base, 120, 70)
    scheduler = LatestFrameRoiScheduler(
        _detector(),
        min_ocr_interval_s=0.1,
        settle_interval_s=0.0,
        max_coalesce_s=0.1,
    )
    scheduler.prime(base, 0.0)
    first_job = scheduler.observe(changed, 0.1)
    assert first_job is not None

    follow_up = scheduler.complete(
        first_job,
        accepted=False,
        completed_at_s=0.2,
        dispatch_follow_up=False,
    )

    assert follow_up is None
    assert not scheduler.busy
    assert scheduler.has_pending
    retry = scheduler.observe(changed.copy(), 0.2)
    assert retry is not None
    assert retry.generation > first_job.generation
    assert retry.frame is not first_job.frame


def test_latest_frame_returning_to_baseline_drops_a_local_transient() -> None:
    base = _blank()
    transient = _paint(base, 120, 70)
    scheduler = LatestFrameRoiScheduler(
        _detector(),
        min_ocr_interval_s=0.5,
        settle_interval_s=0.2,
        max_coalesce_s=0.5,
    )
    scheduler.prime(base, 0.0)

    assert scheduler.observe(transient, 0.1) is None
    assert scheduler.has_pending
    assert scheduler.observe(base.copy(), 0.2) is None

    assert not scheduler.has_pending
    assert scheduler.poll(1.0, force=True) is None


def test_repeated_empty_results_back_off_and_real_target_restores_rate() -> None:
    scheduler = LatestFrameRoiScheduler(
        _detector(),
        min_ocr_interval_s=0.4,
        settle_interval_s=0.0,
        max_coalesce_s=0.4,
    )
    frame = _blank()
    scheduler.prime(frame, 0.0)

    expected_intervals = (0.4, 0.6, 0.8, 1.0)
    dispatch_times = (0.4, 0.8, 1.4, 2.2)
    for index, (now_s, expected_interval) in enumerate(
        zip(dispatch_times, expected_intervals, strict=True)
    ):
        frame = _paint(frame, 40 + index * 48, 70)
        job = scheduler.observe(frame, now_s)
        assert job is not None
        assert scheduler.complete(
            job,
            accepted=True,
            completed_at_s=now_s,
            target_count=0,
        ) is None
        assert scheduler.effective_min_ocr_interval_s == pytest.approx(
            expected_interval
        )

    assert scheduler.empty_result_count == 4
    assert scheduler.empty_result_streak == 4
    assert scheduler.peak_adaptive_ocr_interval_s == pytest.approx(1.0)

    frame = _paint(frame, 240, 70)
    productive = scheduler.observe(frame, 3.2)
    assert productive is not None
    assert scheduler.complete(
        productive,
        accepted=True,
        completed_at_s=3.2,
        target_count=2,
    ) is None

    assert scheduler.productive_result_count == 1
    assert scheduler.empty_result_streak == 0
    assert scheduler.effective_min_ocr_interval_s == pytest.approx(0.4)


def test_response_target_dispatches_before_unreachable_full_frame_budget() -> None:
    base = _blank()
    widespread = base.copy()
    widespread[:, :160] = 255
    scheduler = LatestFrameRoiScheduler(
        _detector(),
        min_ocr_interval_s=0.4,
        settle_interval_s=0.3,
        max_coalesce_s=0.5,
        response_target_s=0.5,
    )
    scheduler.prime(base, 0.0)
    scheduler.record_scan_cost("full", 0.8)

    job = scheduler.observe(widespread, 0.1)

    assert job is not None
    assert job.proposal.fallback_full_frame
    assert job.trigger_reason == "response-deadline"
    assert job.predicted_scan_kind == "full"
    assert job.predicted_remaining_s == pytest.approx(0.8)
    assert job.response_wait_budget_s == 0.0


def test_response_target_still_allows_a_settled_local_frame_to_run_early() -> None:
    base = _blank()
    changed = _paint(base, 120, 70)
    scheduler = LatestFrameRoiScheduler(
        _detector(),
        min_ocr_interval_s=0.1,
        settle_interval_s=0.05,
        max_coalesce_s=0.5,
        response_target_s=0.5,
    )
    scheduler.prime(base, 0.0)
    scheduler.record_scan_cost("roi", 0.12)

    assert scheduler.observe(changed, 0.1) is None
    job = scheduler.observe(changed.copy(), 0.16)

    assert job is not None
    assert job.trigger_reason == "settled"
    assert job.predicted_scan_kind == "roi"
    assert job.predicted_remaining_s == pytest.approx(0.12)
    assert job.response_wait_budget_s == pytest.approx(0.38)


def test_response_cost_learning_is_separate_and_smoothed_by_scan_kind() -> None:
    scheduler = LatestFrameRoiScheduler(
        _detector(),
        response_target_s=0.5,
    )

    scheduler.record_scan_cost("full", 1.0)
    assert scheduler.predicted_full_remaining_s == pytest.approx(1.0)
    assert scheduler.predicted_roi_remaining_s == pytest.approx(0.3)

    scheduler.record_scan_cost("full", 0.6)
    scheduler.record_scan_cost("roi", 0.2)
    scheduler.record_scan_cost("roi", 0.4)

    assert scheduler.predicted_full_remaining_s == pytest.approx(0.9)
    assert scheduler.predicted_roi_remaining_s == pytest.approx(0.25)
    assert scheduler.remaining_cost_sample_counts == (2, 2)


def test_late_contextual_full_fallback_guides_only_the_next_local_budget() -> None:
    base = _blank()
    first = _paint(base, 40, 70)
    second = _paint(first, 140, 70)
    third = _paint(second, 240, 70)
    scheduler = LatestFrameRoiScheduler(
        _detector(),
        min_ocr_interval_s=0.1,
        settle_interval_s=0.05,
        max_coalesce_s=0.5,
        response_target_s=0.5,
    )
    scheduler.prime(base, 0.0)
    scheduler.record_scan_cost("full", 0.8)

    assert scheduler.observe(first, 0.1) is None
    first_job = scheduler.observe(first.copy(), 0.16)
    assert first_job is not None
    assert first_job.predicted_scan_kind == "roi"
    scheduler.record_scan_outcome(first_job, "full")
    assert scheduler.complete(
        first_job,
        accepted=True,
        completed_at_s=0.16,
        target_count=1,
    ) is None

    second_job = scheduler.observe(second, 0.17)
    assert second_job is not None
    assert not second_job.proposal.fallback_full_frame
    assert second_job.predicted_scan_kind == "full"
    assert second_job.trigger_reason == "response-deadline"
    scheduler.record_scan_outcome(second_job, "roi")
    assert scheduler.complete(
        second_job,
        accepted=True,
        completed_at_s=0.17,
        target_count=1,
    ) is None

    assert scheduler.observe(third, 0.27) is None
    third_job = scheduler.observe(third.copy(), 0.33)
    assert third_job is not None
    assert third_job.predicted_scan_kind == "roi"


def test_pending_timestamp_without_regions_is_cleared_not_dispatched() -> None:
    scheduler = LatestFrameRoiScheduler(
        _detector(),
        min_ocr_interval_s=0.1,
        settle_interval_s=0.0,
        max_coalesce_s=0.1,
        response_target_s=0.1,
    )
    scheduler.prime(_blank(), 0.0)
    # Regression guard for a rejected/follow-up state observed in live.log:
    # the timestamp alone must never occupy the one OCR in-flight slot.
    scheduler._pending_since_s = 0.1

    assert scheduler.poll(0.1) is None
    assert not scheduler.has_pending
    assert not scheduler.busy


@pytest.mark.parametrize(
    ("scan_kind", "seconds", "message"),
    (
        ("unknown", 0.1, "scan_kind"),
        ("roi", -0.1, "remaining_seconds"),
        ("full", float("nan"), "remaining_seconds"),
    ),
)
def test_response_cost_learning_rejects_invalid_samples(
    scan_kind: str,
    seconds: float,
    message: str,
) -> None:
    scheduler = LatestFrameRoiScheduler(_detector())

    with pytest.raises(ValueError, match=message):
        scheduler.record_scan_cost(scan_kind, seconds)

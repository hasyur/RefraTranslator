from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from game_screen_translator.ocr.dynamic_roi import (
    DynamicRoiProposal,
    FullScreenRoiDetector,
    SampledRoiFrame,
)
from game_screen_translator.ocr.roi import OcrRoi


_EMPTY_RESULT_GRACE_SCANS = 1
_EMPTY_RESULT_BACKOFF_STEPS = 3
_EMPTY_RESULT_MAX_INTERVAL_S = 1.0
_EMPTY_RESULT_MAX_INTERVAL_FACTOR = 2.5
_DEFAULT_ROI_REMAINING_COST_S = 0.12
_DEFAULT_FULL_REMAINING_COST_S = 0.65
_ROI_COST_FROM_FULL_FACTOR = 0.3
_COST_ESTIMATE_ALPHA = 0.25


@dataclass(frozen=True, slots=True)
class ScheduledRoiScan:
    """One immutable snapshot selected for OCR by a latest-frame scheduler."""

    job_id: int
    generation: int
    change_started_at_s: float
    last_changed_at_s: float
    observed_at_s: float
    dispatched_at_s: float
    frame: np.ndarray
    sampled_frame: SampledRoiFrame
    proposal: DynamicRoiProposal
    trigger_reason: str
    predicted_scan_kind: str
    predicted_remaining_s: float
    response_wait_budget_s: float


class LatestFrameRoiScheduler:
    """Coalesce cheap change scans into one latest-frame OCR slot.

    The caller performs cheap observations at its own cadence (for example
    10 Hz). At most one OCR job may be in flight. While that job is running,
    intermediate observations replace the single pending frame instead of
    forming a queue.

    Frames passed to this class are treated as immutable. A capture backend
    that reuses its image buffer must copy the frame before calling ``prime``
    or ``observe``.
    """

    def __init__(
        self,
        detector: FullScreenRoiDetector,
        *,
        min_ocr_interval_s: float = 1.0 / 3.0,
        settle_interval_s: float = 0.18,
        max_coalesce_s: float = 1.0 / 3.0,
        response_target_s: float | None = None,
    ) -> None:
        for name, value in (
            ("min_ocr_interval_s", min_ocr_interval_s),
            ("settle_interval_s", settle_interval_s),
            ("max_coalesce_s", max_coalesce_s),
        ):
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} 必须是非负有限数")
        if min_ocr_interval_s == 0.0 and max_coalesce_s == 0.0:
            raise ValueError("OCR 间隔和合并窗口不能同时为 0")
        if response_target_s is not None and (
            not math.isfinite(response_target_s) or response_target_s <= 0.0
        ):
            raise ValueError("response_target_s 必须是正有限数或 None")

        self.detector = detector
        self.min_ocr_interval_s = min_ocr_interval_s
        self.settle_interval_s = settle_interval_s
        self.max_coalesce_s = max_coalesce_s
        self.response_target_s = response_target_s
        self._max_adaptive_ocr_interval_s = max(
            min_ocr_interval_s,
            min(
                _EMPTY_RESULT_MAX_INTERVAL_S,
                min_ocr_interval_s * _EMPTY_RESULT_MAX_INTERVAL_FACTOR,
            ),
        )
        self._effective_min_ocr_interval_s = min_ocr_interval_s
        self._empty_result_streak = 0
        self._empty_result_count = 0
        self._productive_result_count = 0
        self._peak_adaptive_ocr_interval_s = min_ocr_interval_s
        self._remaining_cost_estimates: dict[str, float | None] = {
            "roi": None,
            "full": None,
        }
        self._remaining_cost_sample_counts = {"roi": 0, "full": 0}
        self._expect_contextual_full_frame = False

        self._accepted_sample: SampledRoiFrame | None = None
        self._accepted_at_s: float | None = None
        self._latest_frame: np.ndarray | None = None
        self._latest_sample: SampledRoiFrame | None = None
        self._latest_at_s: float | None = None
        self._last_observed_sample: SampledRoiFrame | None = None
        self._last_observed_at_s: float | None = None
        self._last_motion_at_s: float | None = None
        self._last_dispatch_at_s: float | None = None

        self._generation = 0
        self._next_job_id = 1
        self._in_flight: ScheduledRoiScan | None = None

        self._pending_since_s: float | None = None
        self._pending_change_rois: tuple[OcrRoi, ...] = ()
        self._pending_changed_fraction = 0.0
        self._pending_fallback_reason: str | None = None
        self._pending_fallback_candidate_coverage = 0.0
        self._pending_fallback_candidate_region_count = 0

    @property
    def primed(self) -> bool:
        return self._accepted_sample is not None

    @property
    def busy(self) -> bool:
        return self._in_flight is not None

    @property
    def has_pending(self) -> bool:
        return self._pending_since_s is not None

    @property
    def in_flight(self) -> ScheduledRoiScan | None:
        return self._in_flight

    @property
    def latest_generation(self) -> int:
        return self._generation

    @property
    def effective_min_ocr_interval_s(self) -> float:
        """Current OCR rate gate after conservative empty-result backoff."""
        return self._effective_min_ocr_interval_s

    @property
    def max_adaptive_ocr_interval_s(self) -> float:
        return self._max_adaptive_ocr_interval_s

    @property
    def peak_adaptive_ocr_interval_s(self) -> float:
        return self._peak_adaptive_ocr_interval_s

    @property
    def empty_result_streak(self) -> int:
        return self._empty_result_streak

    @property
    def empty_result_count(self) -> int:
        return self._empty_result_count

    @property
    def productive_result_count(self) -> int:
        return self._productive_result_count

    @property
    def predicted_roi_remaining_s(self) -> float:
        estimate = self._remaining_cost_estimates["roi"]
        if estimate is not None:
            return estimate
        full_estimate = self._remaining_cost_estimates["full"]
        if full_estimate is not None:
            return max(
                _DEFAULT_ROI_REMAINING_COST_S,
                full_estimate * _ROI_COST_FROM_FULL_FACTOR,
            )
        return _DEFAULT_ROI_REMAINING_COST_S

    @property
    def predicted_full_remaining_s(self) -> float:
        estimate = self._remaining_cost_estimates["full"]
        return _DEFAULT_FULL_REMAINING_COST_S if estimate is None else estimate

    @property
    def remaining_cost_sample_counts(self) -> tuple[int, int]:
        """Return learned local/full sample counts for diagnostics."""
        return (
            self._remaining_cost_sample_counts["roi"],
            self._remaining_cost_sample_counts["full"],
        )

    def record_scan_cost(self, scan_kind: str, remaining_seconds: float) -> None:
        """Learn post-dispatch cost separately for local and full OCR scans."""
        if scan_kind not in self._remaining_cost_estimates:
            raise ValueError("scan_kind 必须是 roi 或 full")
        if not math.isfinite(remaining_seconds) or remaining_seconds < 0.0:
            raise ValueError("remaining_seconds 必须是非负有限数")
        previous = self._remaining_cost_estimates[scan_kind]
        self._remaining_cost_estimates[scan_kind] = (
            remaining_seconds
            if previous is None
            else previous
            + _COST_ESTIMATE_ALPHA * (remaining_seconds - previous)
        )
        self._remaining_cost_sample_counts[scan_kind] += 1

    def record_scan_outcome(
        self,
        job: ScheduledRoiScan,
        actual_scan_kind: str,
    ) -> None:
        """Remember a late contextual fallback without replanning every tick."""
        if actual_scan_kind not in self._remaining_cost_estimates:
            raise ValueError("actual_scan_kind 必须是 roi 或 full")
        if self._in_flight is None or self._in_flight.job_id != job.job_id:
            raise ValueError("记录的不是当前 OCR job")
        if job.proposal.fallback_full_frame:
            return
        self._expect_contextual_full_frame = actual_scan_kind == "full"

    def prime(self, frame: np.ndarray, now_s: float) -> None:
        """Set the frame whose OCR map has already been accepted."""
        self._validate_time(now_s)
        if self.primed:
            raise RuntimeError("scheduler 已经初始化")
        sampled_frame = self.detector.sample_frame(frame)
        self._accepted_sample = sampled_frame
        self._accepted_at_s = now_s
        self._latest_frame = frame
        self._latest_sample = sampled_frame
        self._latest_at_s = now_s
        self._last_observed_sample = sampled_frame
        self._last_observed_at_s = now_s
        self._last_motion_at_s = now_s
        self._last_dispatch_at_s = now_s

    def observe(self, frame: np.ndarray, now_s: float) -> ScheduledRoiScan | None:
        """Observe the newest frame and dispatch it if the OCR slot is ready."""
        self._require_primed()
        self._validate_monotonic_time(now_s)
        assert self._last_observed_sample is not None

        sampled_frame = self.detector.sample_frame(frame)
        adjacent = self.detector.propose_sampled(
            self._last_observed_sample,
            sampled_frame,
        )
        if adjacent.rois:
            self._last_motion_at_s = now_s

        baseline_sample = (
            self._in_flight.sampled_frame
            if self._in_flight is not None
            else self._accepted_sample
        )
        assert baseline_sample is not None
        proposal = self.detector.propose_sampled(baseline_sample, sampled_frame)

        self._generation += 1
        self._latest_frame = frame
        self._latest_sample = sampled_frame
        self._latest_at_s = now_s
        self._last_observed_sample = sampled_frame
        self._last_observed_at_s = now_s

        if proposal.rois:
            self._record_pending(proposal, now_s)
        elif self._pending_fallback_reason is None:
            # Latest Wins: a local transient that returned to the accepted (or
            # in-flight) state before OCR does not need to be scanned.
            self._clear_pending()

        return self.poll(now_s)

    def poll(
        self, now_s: float, *, force: bool = False
    ) -> ScheduledRoiScan | None:
        """Dispatch pending work when its rate/coalesce gates are satisfied."""
        self._require_primed()
        self._validate_poll_time(now_s)
        if self._in_flight is not None or self._pending_since_s is None:
            return None
        if (
            self._pending_fallback_reason is None
            and not self._pending_change_rois
        ):
            # A pending timestamp without executable regions is not work. If
            # dispatched, it would occupy the single OCR slot forever because
            # the contextual planner cannot build a crop for it.
            self._clear_pending()
            return None

        assert self._last_dispatch_at_s is not None
        rate_ready = (
            now_s - self._last_dispatch_at_s + 1e-12
            >= self._effective_min_ocr_interval_s
        )
        assert self._last_motion_at_s is not None
        settled = (
            now_s - self._last_motion_at_s + 1e-12
            >= self.settle_interval_s
        )
        predicted_scan_kind, predicted_remaining_s, response_wait_budget_s = (
            self._pending_response_budget()
        )
        # Stability and rate gates are soft. The response deadline covers the
        # interval from the first observed change through the predicted text-
        # map update, so it must win when the remaining budget is exhausted.
        response_deadline_reached = (
            now_s - self._pending_since_s + 1e-12
            >= min(self.max_coalesce_s, response_wait_budget_s)
        )
        if (
            not force
            and not response_deadline_reached
            and (not rate_ready or not settled)
        ):
            return None

        proposal = self._pending_proposal()
        change_started_at_s = self._pending_since_s
        assert change_started_at_s is not None
        assert self._last_motion_at_s is not None
        last_changed_at_s = max(change_started_at_s, self._last_motion_at_s)
        assert self._latest_frame is not None
        assert self._latest_sample is not None
        assert self._latest_at_s is not None
        trigger_reason = (
            "forced"
            if force
            else "response-deadline"
            if (
                self.response_target_s is not None
                and response_wait_budget_s <= self.max_coalesce_s
                and response_deadline_reached
            )
            else "settled"
            if settled
            else "max-coalesce"
        )
        job = ScheduledRoiScan(
            self._next_job_id,
            self._generation,
            change_started_at_s,
            min(last_changed_at_s, now_s),
            self._latest_at_s,
            now_s,
            self._latest_frame,
            self._latest_sample,
            proposal,
            trigger_reason,
            predicted_scan_kind,
            predicted_remaining_s,
            response_wait_budget_s,
        )
        self._next_job_id += 1
        self._in_flight = job
        self._last_dispatch_at_s = now_s
        self._clear_pending()
        return job

    def complete(
        self,
        job: ScheduledRoiScan,
        *,
        accepted: bool,
        completed_at_s: float,
        target_count: int | None = None,
    ) -> ScheduledRoiScan | None:
        """Finish a job, advancing the baseline only for accepted OCR output.

        Accepted OCR results may report how many changed translation targets
        they produced. Repeated empty results gradually lower only the OCR
        cadence (the cheap global change scan keeps running); the first empty
        result receives a grace scan, and any real target restores the user
        configured interval immediately.
        """
        self._require_primed()
        self._validate_poll_time(completed_at_s)
        if self._in_flight is None or self._in_flight.job_id != job.job_id:
            raise ValueError("完成的不是当前 OCR job")
        if target_count is not None:
            if not isinstance(target_count, int) or isinstance(target_count, bool):
                raise TypeError("target_count 必须是整数或 None")
            if target_count < 0:
                raise ValueError("target_count 不能为负数")
            if not accepted:
                raise ValueError("失败的 OCR 不能提交 target_count")

        post_job_pending_since = self._pending_since_s
        post_job_rois = self._pending_change_rois
        post_job_changed_fraction = self._pending_changed_fraction
        post_job_fallback = self._pending_fallback_reason
        post_job_fallback_coverage = self._pending_fallback_candidate_coverage
        post_job_fallback_region_count = (
            self._pending_fallback_candidate_region_count
        )
        self._in_flight = None

        if accepted:
            self._accepted_sample = job.sampled_frame
            self._accepted_at_s = completed_at_s
            if target_count is not None:
                self._record_target_feedback(target_count)
        else:
            # The failed job did not consume its change. Rebuild from the last
            # accepted frame to the newest frame and retain any full-frame
            # safety decision made by either the failed or pending work.
            assert self._accepted_sample is not None
            assert self._latest_frame is not None
            assert self._latest_sample is not None
            rebuilt = self.detector.propose_sampled(
                self._accepted_sample,
                self._latest_sample,
            )
            self._clear_pending()
            if rebuilt.rois:
                self._record_pending(rebuilt, job.observed_at_s)
            if job.proposal.fallback_full_frame:
                self._pending_fallback_reason = job.proposal.reason
                self._pending_fallback_candidate_coverage = (
                    job.proposal.candidate_coverage_fraction
                )
                self._pending_fallback_candidate_region_count = (
                    job.proposal.candidate_region_count
                )

            self._pending_change_rois = self._merge_rois(
                (*self._pending_change_rois, *post_job_rois)
            )
            self._pending_changed_fraction = max(
                self._pending_changed_fraction,
                post_job_changed_fraction,
                job.proposal.changed_fraction,
            )
            if (
                self._pending_fallback_reason is None
                and post_job_fallback is not None
            ):
                self._pending_fallback_reason = post_job_fallback
                self._pending_fallback_candidate_coverage = (
                    post_job_fallback_coverage
                )
                self._pending_fallback_candidate_region_count = (
                    post_job_fallback_region_count
                )
            if (
                self._pending_fallback_reason is None
                and not self._pending_change_rois
            ):
                self._clear_pending()
            else:
                pending_times = tuple(
                    value
                    for value in (
                        self._pending_since_s,
                        post_job_pending_since,
                    )
                    if value is not None
                )
                self._pending_since_s = min(
                    pending_times,
                    default=job.observed_at_s,
                )

        return self.poll(completed_at_s)

    def _record_target_feedback(self, target_count: int) -> None:
        if target_count > 0:
            self._productive_result_count += 1
            self._empty_result_streak = 0
            self._effective_min_ocr_interval_s = self.min_ocr_interval_s
            return

        self._empty_result_count += 1
        self._empty_result_streak += 1
        backoff_step = min(
            _EMPTY_RESULT_BACKOFF_STEPS,
            max(0, self._empty_result_streak - _EMPTY_RESULT_GRACE_SCANS),
        )
        progress = backoff_step / _EMPTY_RESULT_BACKOFF_STEPS
        self._effective_min_ocr_interval_s = self.min_ocr_interval_s + (
            self._max_adaptive_ocr_interval_s - self.min_ocr_interval_s
        ) * progress
        self._peak_adaptive_ocr_interval_s = max(
            self._peak_adaptive_ocr_interval_s,
            self._effective_min_ocr_interval_s,
        )

    def is_latest(self, job: ScheduledRoiScan) -> bool:
        """Return whether no newer captured state appeared after dispatch."""
        return job.generation == self._generation

    def _record_pending(
        self, proposal: DynamicRoiProposal, observed_at_s: float
    ) -> None:
        if self._pending_since_s is None:
            self._pending_since_s = observed_at_s
        seeds = proposal.change_rois or proposal.rois
        self._pending_change_rois = self._merge_rois(
            (*self._pending_change_rois, *seeds)
        )
        self._pending_changed_fraction = max(
            self._pending_changed_fraction, proposal.changed_fraction
        )
        if proposal.fallback_full_frame and self._pending_fallback_reason is None:
            self._pending_fallback_reason = proposal.reason
            self._pending_fallback_candidate_coverage = (
                proposal.candidate_coverage_fraction
            )
            self._pending_fallback_candidate_region_count = (
                proposal.candidate_region_count
            )

    def _pending_proposal(self) -> DynamicRoiProposal:
        assert self._latest_frame is not None
        frame_height, frame_width = self._latest_frame.shape[:2]
        full_frame = (0, 0, frame_width, frame_height)
        if self._pending_fallback_reason is not None:
            return DynamicRoiProposal(
                (full_frame,),
                self._pending_changed_fraction,
                1.0,
                True,
                self._pending_fallback_reason,
                self._pending_change_rois or (full_frame,),
                self._pending_fallback_candidate_coverage,
                self._pending_fallback_candidate_region_count,
            )

        coverage = self._coverage_fraction(
            self._pending_change_rois,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        return DynamicRoiProposal(
            self._pending_change_rois,
            self._pending_changed_fraction,
            coverage,
            False,
            "coalesced-local-change",
            self._pending_change_rois,
            coverage,
            len(self._pending_change_rois),
        )

    def _pending_response_budget(self) -> tuple[str, float, float]:
        proposal = self._pending_proposal()
        predicted_scan_kind = (
            "full"
            if proposal.fallback_full_frame or self._expect_contextual_full_frame
            else "roi"
        )
        predicted = (
            self.predicted_full_remaining_s
            if predicted_scan_kind == "full"
            else self.predicted_roi_remaining_s
        )
        if self.response_target_s is None:
            return predicted_scan_kind, predicted, self.max_coalesce_s
        return (
            predicted_scan_kind,
            predicted,
            max(0.0, self.response_target_s - predicted),
        )

    def _clear_pending(self) -> None:
        self._pending_since_s = None
        self._pending_change_rois = ()
        self._pending_changed_fraction = 0.0
        self._pending_fallback_reason = None
        self._pending_fallback_candidate_coverage = 0.0
        self._pending_fallback_candidate_region_count = 0

    @staticmethod
    def _merge_rois(rois: tuple[OcrRoi, ...]) -> tuple[OcrRoi, ...]:
        pending = [
            (left, top, left + width, top + height)
            for left, top, width, height in rois
            if width > 0 and height > 0
        ]
        merged: list[tuple[int, int, int, int]] = []
        while pending:
            current = pending.pop()
            changed = True
            while changed:
                changed = False
                index = 0
                while index < len(pending):
                    other = pending[index]
                    if not (
                        current[2] < other[0]
                        or other[2] < current[0]
                        or current[3] < other[1]
                        or other[3] < current[1]
                    ):
                        current = (
                            min(current[0], other[0]),
                            min(current[1], other[1]),
                            max(current[2], other[2]),
                            max(current[3], other[3]),
                        )
                        pending.pop(index)
                        changed = True
                    else:
                        index += 1
            merged.append(current)
        return tuple(
            sorted(
                (
                    (left, top, right - left, bottom - top)
                    for left, top, right, bottom in merged
                ),
                key=lambda roi: (roi[1], roi[0]),
            )
        )

    @staticmethod
    def _coverage_fraction(
        rois: tuple[OcrRoi, ...], *, frame_width: int, frame_height: int
    ) -> float:
        if not rois:
            return 0.0
        return min(
            1.0,
            sum(width * height for _, _, width, height in rois)
            / (frame_width * frame_height),
        )

    def _require_primed(self) -> None:
        if not self.primed:
            raise RuntimeError("必须先用已接受的 OCR 帧初始化 scheduler")

    @staticmethod
    def _validate_time(now_s: float) -> None:
        if not math.isfinite(now_s):
            raise ValueError("时间必须是有限数")

    def _validate_monotonic_time(self, now_s: float) -> None:
        self._validate_time(now_s)
        assert self._last_observed_at_s is not None
        if now_s < self._last_observed_at_s:
            raise ValueError("observe 时间必须单调递增")

    def _validate_poll_time(self, now_s: float) -> None:
        self._validate_time(now_s)
        assert self._last_observed_at_s is not None
        if now_s < self._last_observed_at_s:
            raise ValueError("poll/complete 不能早于最后一次 observe")

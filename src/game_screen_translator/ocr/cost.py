from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from game_screen_translator.ocr.roi import OcrRoi


@dataclass(frozen=True, slots=True)
class OcrInputCost:
    call_count: int
    source_pixels: int
    detector_pixels: int


@dataclass(frozen=True, slots=True)
class OcrComputeEstimate:
    """Pixel-based proxy for one OCR task; it does not predict recognition cost."""

    executed: OcrInputCost
    candidate: OcrInputCost
    full_frame: OcrInputCost
    executed_full_frame: bool

    @property
    def executed_to_full_ratio(self) -> float:
        return self.executed.detector_pixels / self.full_frame.detector_pixels

    @property
    def candidate_to_full_ratio(self) -> float:
        return self.candidate.detector_pixels / self.full_frame.detector_pixels


def estimate_ocr_compute_cost(
    frame_size: tuple[int, int],
    *,
    detection_max_side: int,
    executed_rois: Sequence[OcrRoi] | None,
    candidate_rois: Sequence[OcrRoi] | None = None,
) -> OcrComputeEstimate:
    """Estimate detector pixels after Paddle's max-side resize.

    ``executed_rois=None`` represents one full-frame model call. Candidate ROIs
    are diagnostic only and allow a full-frame fallback to retain the cost of
    the local plan that preceded it.
    """

    frame_width, frame_height = frame_size
    if frame_width < 1 or frame_height < 1:
        raise ValueError("frame_size 必须为正数")
    if detection_max_side < 1:
        raise ValueError("detection_max_side 必须大于 0")
    full_roi = (0, 0, frame_width, frame_height)
    full_cost = _input_cost(
        (full_roi,),
        frame_size=frame_size,
        detection_max_side=detection_max_side,
    )
    resolved_executed = (
        (full_roi,)
        if executed_rois is None
        else _validated_rois(executed_rois, frame_size=frame_size)
    )
    resolved_candidate = (
        resolved_executed
        if candidate_rois is None
        else _validated_rois(candidate_rois, frame_size=frame_size)
    )
    return OcrComputeEstimate(
        executed=_input_cost(
            resolved_executed,
            frame_size=frame_size,
            detection_max_side=detection_max_side,
        ),
        candidate=_input_cost(
            resolved_candidate,
            frame_size=frame_size,
            detection_max_side=detection_max_side,
        ),
        full_frame=full_cost,
        executed_full_frame=executed_rois is None,
    )


class OcrComputeStats:
    """Accumulate lightweight OCR cost estimates for diagnostics only."""

    def __init__(self) -> None:
        self._latest: OcrComputeEstimate | None = None
        self._latest_is_dynamic_roi = False
        self._sample_count = 0
        self._total_calls = 0
        self._total_detector_pixels = 0
        self._dynamic_roi_samples = 0
        self._candidate_ratio_total = 0.0
        self._candidate_ratio_peak = 0.0
        self._candidate_more_expensive_count = 0

    @property
    def latest(self) -> OcrComputeEstimate | None:
        return self._latest

    @property
    def candidate_more_expensive_count(self) -> int:
        return self._candidate_more_expensive_count

    @property
    def candidate_ratio_peak(self) -> float:
        return self._candidate_ratio_peak

    def record(self, estimate: OcrComputeEstimate, *, is_dynamic_roi: bool) -> None:
        self._latest = estimate
        self._latest_is_dynamic_roi = is_dynamic_roi
        self._sample_count += 1
        self._total_calls += estimate.executed.call_count
        self._total_detector_pixels += estimate.executed.detector_pixels
        if not is_dynamic_roi:
            return
        ratio = estimate.candidate_to_full_ratio
        self._dynamic_roi_samples += 1
        self._candidate_ratio_total += ratio
        self._candidate_ratio_peak = max(self._candidate_ratio_peak, ratio)
        if ratio > 1.0:
            self._candidate_more_expensive_count += 1

    def render(self) -> str:
        estimate = self._latest
        if estimate is None:
            return "OCR 成本：等待首个样本……"
        executed_mode = "整屏" if estimate.executed_full_frame else "ROI"
        rendered = (
            f"OCR 成本：执行{executed_mode} {estimate.executed.call_count} 次 · "
            f"原图 {_megapixels(estimate.executed.source_pixels)} · "
            f"检测约 {_megapixels(estimate.executed.detector_pixels)}"
        )
        if self._latest_is_dynamic_roi:
            rendered += (
                f"；候选 ROI {estimate.candidate.call_count} 次 · "
                f"原图 {_megapixels(estimate.candidate.source_pixels)} · "
                f"检测约 {_megapixels(estimate.candidate.detector_pixels)} · "
                f"整屏的 {estimate.candidate_to_full_ratio:.2f} 倍 · "
                f"累计更高 {self._candidate_more_expensive_count}/"
                f"{self._dynamic_roi_samples} 轮"
            )
        rendered += f"；整屏约 {_megapixels(estimate.full_frame.detector_pixels)}"
        return rendered

    def summary(self) -> str:
        if self._sample_count == 0:
            return "OCR 成本估算：没有样本"
        rendered = (
            f"OCR 成本估算：执行 {self._sample_count} 轮/"
            f"{self._total_calls} 次模型调用/检测约 "
            f"{_megapixels(self._total_detector_pixels)}"
        )
        if self._dynamic_roi_samples:
            average = self._candidate_ratio_total / self._dynamic_roi_samples
            rendered += (
                f"；ROI 候选 {self._dynamic_roi_samples} 轮，"
                f"像素高于整屏 {self._candidate_more_expensive_count} 轮，"
                f"候选/整屏平均 {average:.2f} 倍/"
                f"峰值 {self._candidate_ratio_peak:.2f} 倍"
            )
        return rendered


def _validated_rois(
    rois: Sequence[OcrRoi], *, frame_size: tuple[int, int]
) -> tuple[OcrRoi, ...]:
    values = tuple(rois)
    if not values:
        raise ValueError("OCR ROI 不能为空")
    frame_width, frame_height = frame_size
    for roi in values:
        left, top, width, height = roi
        if width < 1 or height < 1:
            raise ValueError("OCR ROI 的宽和高必须大于 0")
        if (
            left < 0
            or top < 0
            or left + width > frame_width
            or top + height > frame_height
        ):
            raise ValueError(f"OCR ROI {roi} 超出图像 {frame_width}x{frame_height}")
    return values


def _input_cost(
    rois: Sequence[OcrRoi],
    *,
    frame_size: tuple[int, int],
    detection_max_side: int,
) -> OcrInputCost:
    values = _validated_rois(rois, frame_size=frame_size)
    return OcrInputCost(
        call_count=len(values),
        source_pixels=sum(width * height for _, _, width, height in values),
        detector_pixels=sum(
            _detector_pixels(width, height, detection_max_side)
            for _, _, width, height in values
        ),
    )


def _detector_pixels(width: int, height: int, max_side: int) -> int:
    scale = min(1.0, max_side / max(width, height))
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    return resized_width * resized_height


def _megapixels(pixels: int) -> str:
    return f"{pixels / 1_000_000:.2f} MP"

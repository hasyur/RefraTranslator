from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from statistics import fmean


_OCR_SAMPLE_WINDOW = 256
_OCR_SCAN_KIND_LABELS = {
    "roi": "局部 ROI",
    "full": "整帧",
}


def _duration_label(seconds: float) -> str:
    if seconds < 1:
        return f"{round(seconds * 1000)}ms"
    return f"{seconds:.2f}s"


@dataclass(frozen=True, slots=True)
class LatencySnapshot:
    ocr_seconds: float | None = None
    stability_seconds: float | None = None
    translation_queue_seconds: float | None = None
    llm_seconds: float | None = None
    total_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class OcrLatencyBreakdown:
    """One successful OCR scan from first detected change to updated text state."""

    scan_kind: str
    scan_label: str
    change_activity_seconds: float
    scheduling_seconds: float
    preparation_seconds: float
    worker_queue_seconds: float
    ocr_seconds: float
    collection_seconds: float
    processing_seconds: float

    @property
    def total_seconds(self) -> float:
        return sum(
            (
                self.change_activity_seconds,
                self.scheduling_seconds,
                self.preparation_seconds,
                self.worker_queue_seconds,
                self.ocr_seconds,
                self.collection_seconds,
                self.processing_seconds,
            )
        )


class LiveLatencyStats:
    """Keeps lightweight latest/peak timings for the live control window."""

    def __init__(self) -> None:
        self._latest = LatencySnapshot()
        self._peaks = LatencySnapshot()
        self._latest_batch_size: int | None = None
        self._latest_was_cache_only = False
        self._latest_ocr_breakdown: OcrLatencyBreakdown | None = None
        self._ocr_samples = {
            kind: deque(maxlen=_OCR_SAMPLE_WINDOW)
            for kind in _OCR_SCAN_KIND_LABELS
        }
        self._ocr_sample_counts = {kind: 0 for kind in _OCR_SCAN_KIND_LABELS}

    @property
    def latest(self) -> LatencySnapshot:
        return self._latest

    @property
    def peaks(self) -> LatencySnapshot:
        return self._peaks

    @property
    def latest_ocr_breakdown(self) -> OcrLatencyBreakdown | None:
        return self._latest_ocr_breakdown

    def record_ocr(self, seconds: float) -> None:
        seconds = self._validated(seconds, "OCR")
        self._latest = LatencySnapshot(
            ocr_seconds=seconds,
            stability_seconds=self._latest.stability_seconds,
            translation_queue_seconds=self._latest.translation_queue_seconds,
            llm_seconds=self._latest.llm_seconds,
            total_seconds=self._latest.total_seconds,
        )
        self._peaks = LatencySnapshot(
            ocr_seconds=self._maximum(self._peaks.ocr_seconds, seconds),
            stability_seconds=self._peaks.stability_seconds,
            translation_queue_seconds=self._peaks.translation_queue_seconds,
            llm_seconds=self._peaks.llm_seconds,
            total_seconds=self._peaks.total_seconds,
        )

    def record_ocr_pipeline(
        self,
        *,
        scan_kind: str,
        scan_label: str,
        change_activity_seconds: float,
        scheduling_seconds: float,
        preparation_seconds: float,
        worker_queue_seconds: float,
        ocr_seconds: float,
        collection_seconds: float,
        processing_seconds: float,
    ) -> OcrLatencyBreakdown:
        if scan_kind not in _OCR_SCAN_KIND_LABELS:
            raise ValueError("scan_kind 必须是 roi 或 full")
        if not scan_label.strip():
            raise ValueError("scan_label 不能为空")
        breakdown = OcrLatencyBreakdown(
            scan_kind=scan_kind,
            scan_label=scan_label.strip(),
            change_activity_seconds=self._validated(
                change_activity_seconds, "画面持续变化"
            ),
            scheduling_seconds=self._validated(scheduling_seconds, "OCR 调度"),
            preparation_seconds=self._validated(preparation_seconds, "OCR 准备"),
            worker_queue_seconds=self._validated(worker_queue_seconds, "OCR 线程排队"),
            ocr_seconds=self._validated(ocr_seconds, "OCR"),
            collection_seconds=self._validated(collection_seconds, "OCR 结果接收"),
            processing_seconds=self._validated(processing_seconds, "OCR 结果更新"),
        )
        self.record_ocr(breakdown.ocr_seconds)
        self._latest_ocr_breakdown = breakdown
        self._ocr_samples[scan_kind].append(breakdown)
        self._ocr_sample_counts[scan_kind] += 1
        return breakdown

    def record_translation(
        self,
        *,
        stability_seconds: float,
        queue_seconds: float,
        llm_seconds: float | None,
        total_seconds: float,
        batch_size: int,
    ) -> None:
        stability_seconds = self._validated(stability_seconds, "稳定确认")
        queue_seconds = self._validated(queue_seconds, "翻译排队")
        total_seconds = self._validated(total_seconds, "总延迟")
        if llm_seconds is not None:
            llm_seconds = self._validated(llm_seconds, "LLM")
        if batch_size < 1:
            raise ValueError("batch_size 必须大于 0")

        self._latest = LatencySnapshot(
            ocr_seconds=self._latest.ocr_seconds,
            stability_seconds=stability_seconds,
            translation_queue_seconds=queue_seconds,
            llm_seconds=llm_seconds,
            total_seconds=total_seconds,
        )
        self._peaks = LatencySnapshot(
            ocr_seconds=self._peaks.ocr_seconds,
            stability_seconds=self._maximum(
                self._peaks.stability_seconds, stability_seconds
            ),
            translation_queue_seconds=self._maximum(
                self._peaks.translation_queue_seconds, queue_seconds
            ),
            llm_seconds=(
                self._peaks.llm_seconds
                if llm_seconds is None
                else self._maximum(self._peaks.llm_seconds, llm_seconds)
            ),
            total_seconds=self._maximum(self._peaks.total_seconds, total_seconds),
        )
        self._latest_batch_size = batch_size
        self._latest_was_cache_only = llm_seconds is None

    def render(self) -> str:
        latest_parts: list[str] = []
        if self._latest.ocr_seconds is not None:
            latest_parts.append(f"OCR {_duration_label(self._latest.ocr_seconds)}")
        if self._latest.stability_seconds is not None:
            latest_parts.append(
                f"稳定 {_duration_label(self._latest.stability_seconds)}"
            )
        if self._latest.translation_queue_seconds is not None:
            latest_parts.append(
                f"排队 {_duration_label(self._latest.translation_queue_seconds)}"
            )
        if self._latest_was_cache_only and self._latest_batch_size is not None:
            latest_parts.append("LLM 缓存命中")
        elif self._latest.llm_seconds is not None:
            latest_parts.append(f"LLM {_duration_label(self._latest.llm_seconds)}")
        if self._latest.total_seconds is not None:
            latest_parts.append(f"总计 {_duration_label(self._latest.total_seconds)}")

        if not latest_parts:
            return "延迟统计：等待首个 OCR 样本……"

        batch = (
            f"（{self._latest_batch_size} 条）"
            if self._latest_batch_size is not None
            else ""
        )
        peak_parts = self._peak_parts()
        rendered = f"最近{batch}：" + " · ".join(latest_parts)
        if self._latest_ocr_breakdown is not None:
            rendered += "\n" + self._render_latest_ocr_breakdown(
                self._latest_ocr_breakdown
            )
        if peak_parts:
            rendered += "\n峰值：" + " · ".join(peak_parts)
        return rendered

    def render_ocr_summary(self) -> str:
        """Render bounded per-kind percentiles and phase averages for logs."""

        parts: list[str] = []
        for scan_kind, default_label in _OCR_SCAN_KIND_LABELS.items():
            samples = tuple(self._ocr_samples[scan_kind])
            if not samples:
                continue
            total_count = self._ocr_sample_counts[scan_kind]
            window_label = (
                f"最近 {len(samples)} 个" if total_count > len(samples) else f"{len(samples)} 个"
            )
            totals = tuple(sample.total_seconds for sample in samples)
            ocr_values = tuple(sample.ocr_seconds for sample in samples)
            phase_averages = (
                ("变化持续", fmean(sample.change_activity_seconds for sample in samples)),
                ("调度", fmean(sample.scheduling_seconds for sample in samples)),
                ("准备", fmean(sample.preparation_seconds for sample in samples)),
                ("线程", fmean(sample.worker_queue_seconds for sample in samples)),
                ("OCR", fmean(ocr_values)),
                ("接收", fmean(sample.collection_seconds for sample in samples)),
                ("更新", fmean(sample.processing_seconds for sample in samples)),
            )
            parts.append(
                f"{default_label}累计 {total_count} 次（统计 {window_label}）："
                f"总计 P50 {_duration_label(self._percentile(totals, 0.50))}/"
                f"P95 {_duration_label(self._percentile(totals, 0.95))}，"
                f"OCR P50 {_duration_label(self._percentile(ocr_values, 0.50))}/"
                f"P95 {_duration_label(self._percentile(ocr_values, 0.95))}；"
                "阶段均值 "
                + " · ".join(
                    f"{label} {_duration_label(seconds)}"
                    for label, seconds in phase_averages
                )
            )
        if not parts:
            return "画面扫描延迟：尚无成功 OCR 样本"
        return "画面扫描延迟：\n" + "\n".join(parts)

    def render_latest_ocr(self) -> str:
        if self._latest_ocr_breakdown is None:
            return "画面扫描延迟：尚无成功 OCR 样本"
        return self._render_latest_ocr_breakdown(self._latest_ocr_breakdown)

    @staticmethod
    def _render_latest_ocr_breakdown(breakdown: OcrLatencyBreakdown) -> str:
        return (
            f"画面最近［{breakdown.scan_label}］："
            f"总计 {_duration_label(breakdown.total_seconds)} · "
            f"变化持续 {_duration_label(breakdown.change_activity_seconds)} · "
            f"调度 {_duration_label(breakdown.scheduling_seconds)} · "
            f"准备 {_duration_label(breakdown.preparation_seconds)} · "
            f"线程 {_duration_label(breakdown.worker_queue_seconds)} · "
            f"OCR {_duration_label(breakdown.ocr_seconds)} · "
            f"接收 {_duration_label(breakdown.collection_seconds)} · "
            f"更新 {_duration_label(breakdown.processing_seconds)}"
        )

    def _peak_parts(self) -> list[str]:
        labels = (
            ("OCR", self._peaks.ocr_seconds),
            ("稳定", self._peaks.stability_seconds),
            ("排队", self._peaks.translation_queue_seconds),
            ("LLM", self._peaks.llm_seconds),
            ("总计", self._peaks.total_seconds),
        )
        return [
            f"{label} {_duration_label(seconds)}"
            for label, seconds in labels
            if seconds is not None
        ]

    @staticmethod
    def _validated(seconds: float, label: str) -> float:
        value = float(seconds)
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{label}耗时必须是非负有限数")
        return value

    @staticmethod
    def _maximum(current: float | None, candidate: float) -> float:
        return candidate if current is None else max(current, candidate)

    @staticmethod
    def _percentile(values: tuple[float, ...], quantile: float) -> float:
        ordered = sorted(values)
        index = max(0, math.ceil(len(ordered) * quantile) - 1)
        return ordered[index]

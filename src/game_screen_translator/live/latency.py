from __future__ import annotations

from dataclasses import dataclass


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


class LiveLatencyStats:
    """Keeps lightweight latest/peak timings for the live control window."""

    def __init__(self) -> None:
        self._latest = LatencySnapshot()
        self._peaks = LatencySnapshot()
        self._latest_batch_size: int | None = None
        self._latest_was_cache_only = False

    @property
    def latest(self) -> LatencySnapshot:
        return self._latest

    @property
    def peaks(self) -> LatencySnapshot:
        return self._peaks

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
        if peak_parts:
            rendered += "\n峰值：" + " · ".join(peak_parts)
        return rendered

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
        if value < 0:
            raise ValueError(f"{label}耗时不能为负数")
        return value

    @staticmethod
    def _maximum(current: float | None, candidate: float) -> float:
        return candidate if current is None else max(current, candidate)

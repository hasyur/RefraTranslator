from __future__ import annotations

import numpy as np


class FrameChangeDetector:
    """Cheap low-resolution luminance comparison used to gate expensive OCR."""

    def __init__(self, threshold: float = 3.0, sample_size: tuple[int, int] = (160, 90)) -> None:
        if threshold < 0:
            raise ValueError("threshold 不能为负数")
        if sample_size[0] < 1 or sample_size[1] < 1:
            raise ValueError("sample_size 必须为正数")
        self.threshold = threshold
        self.sample_size = sample_size
        self._previous: np.ndarray | None = None
        self.last_score: float = 0.0

    def reset(self) -> None:
        self._previous = None
        self.last_score = 0.0

    def changed(self, frame: np.ndarray) -> bool:
        sample = self._sample(frame)
        if self._previous is None:
            self._previous = sample
            self.last_score = float("inf")
            return True

        self.last_score = float(
            np.mean(np.abs(sample.astype(np.float32) - self._previous.astype(np.float32)))
        )
        self._previous = sample
        return self.last_score >= self.threshold

    def _sample(self, frame: np.ndarray) -> np.ndarray:
        if not isinstance(frame, np.ndarray):
            raise TypeError("frame 必须是 numpy.ndarray")
        if frame.ndim not in (2, 3):
            raise ValueError("frame 必须是灰度或 RGB/BGR 数组")
        if frame.ndim == 3 and frame.shape[2] < 3:
            raise ValueError("彩色 frame 至少需要三个通道")

        frame_height, frame_width = frame.shape[:2]
        sample_width, sample_height = self.sample_size
        # Sample cell centres before converting to luminance. The previous
        # implementation converted the complete 4K RGB frame to float32 first,
        # allocating roughly 100 MB per poll even though only 160x90 pixels were
        # retained. Advanced indexing keeps the temporary data at sample size.
        y_indices = (
            (np.arange(sample_height, dtype=np.int64) * 2 + 1)
            * frame_height
            // (sample_height * 2)
        ).clip(0, frame_height - 1)
        x_indices = (
            (np.arange(sample_width, dtype=np.int64) * 2 + 1)
            * frame_width
            // (sample_width * 2)
        ).clip(0, frame_width - 1)

        if frame.ndim == 2:
            return frame[y_indices[:, None], x_indices[None, :]].astype(
                np.uint8,
                copy=False,
            )

        rgb = frame[y_indices[:, None], x_indices[None, :], :3].astype(
            np.uint16,
            copy=False,
        )
        # Integer BT.601 approximation; coefficients total 256.
        return (
            (rgb[..., 0] * 77 + rgb[..., 1] * 150 + rgb[..., 2] * 29) >> 8
        ).astype(np.uint8)

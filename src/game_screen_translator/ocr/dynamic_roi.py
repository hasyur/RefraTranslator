from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from game_screen_translator.ocr.roi import OcrRoi


@dataclass(frozen=True, slots=True)
class DynamicRoiProposal:
    """Local OCR regions derived from a cheap full-frame change scan."""

    rois: tuple[OcrRoi, ...]
    changed_fraction: float
    coverage_fraction: float
    fallback_full_frame: bool
    reason: str
    change_rois: tuple[OcrRoi, ...] = ()
    candidate_coverage_fraction: float = 0.0
    candidate_region_count: int = 0


class FullScreenRoiDetector:
    """Find changed regions without running OCR or retaining frame state.

    The detector compares the current frame with the caller's last accepted
    baseline. It samples four points per low-resolution cell so that thin text
    strokes are less likely to fall between sample positions. Candidate cells
    are grouped into padded rectangles; unsafe plans fall back to one full-frame
    ROI instead of silently dropping changed content.
    """

    def __init__(
        self,
        *,
        sample_size: tuple[int, int] = (320, 180),
        pixel_threshold: float = 14.0,
        tile_size: tuple[int, int] = (4, 3),
        min_changed_samples: int = 1,
        tile_dilation: int = 1,
        padding: tuple[int, int] = (160, 32),
        min_roi_size: tuple[int, int] = (768, 112),
        merge_gap: tuple[int, int] = (64, 32),
        max_rois: int = 6,
        max_coverage_fraction: float = 0.45,
        full_frame_change_fraction: float = 0.22,
    ) -> None:
        if sample_size[0] < 1 or sample_size[1] < 1:
            raise ValueError("sample_size 必须为正数")
        if pixel_threshold < 0:
            raise ValueError("pixel_threshold 不能为负数")
        if tile_size[0] < 1 or tile_size[1] < 1:
            raise ValueError("tile_size 必须为正数")
        tile_area = tile_size[0] * tile_size[1]
        if min_changed_samples < 1 or min_changed_samples > tile_area:
            raise ValueError("min_changed_samples 必须适合 tile_size")
        if tile_dilation < 0:
            raise ValueError("tile_dilation 不能为负数")
        if any(value < 0 for value in padding + merge_gap):
            raise ValueError("padding 和 merge_gap 不能为负数")
        if min_roi_size[0] < 1 or min_roi_size[1] < 1:
            raise ValueError("min_roi_size 必须为正数")
        if max_rois < 1:
            raise ValueError("max_rois 必须大于 0")
        if not 0 < max_coverage_fraction <= 1:
            raise ValueError("max_coverage_fraction 必须在 0 到 1 之间")
        if not 0 < full_frame_change_fraction <= 1:
            raise ValueError("full_frame_change_fraction 必须在 0 到 1 之间")

        self.sample_size = sample_size
        self.pixel_threshold = pixel_threshold
        self.tile_size = tile_size
        self.min_changed_samples = min_changed_samples
        self.tile_dilation = tile_dilation
        self.padding = padding
        self.min_roi_size = min_roi_size
        self.merge_gap = merge_gap
        self.max_rois = max_rois
        self.max_coverage_fraction = max_coverage_fraction
        self.full_frame_change_fraction = full_frame_change_fraction

    def propose(self, baseline: np.ndarray, current: np.ndarray) -> DynamicRoiProposal:
        self._validate_frames(baseline, current)
        frame_height, frame_width = current.shape[:2]
        full_frame = (0, 0, frame_width, frame_height)

        difference = self._sampled_difference(baseline, current)
        changed = difference >= self.pixel_threshold
        changed_fraction = float(np.mean(changed))
        if not np.any(changed):
            return DynamicRoiProposal((), 0.0, 0.0, False, "unchanged", ())

        active_tiles = self._active_tiles(changed)
        active_tiles = self._dilate(active_tiles, self.tile_dilation)
        tile_boxes = self._connected_tile_boxes(active_tiles)
        change_candidates = tuple(
            self._tile_box_to_change_roi(
                box, frame_width=frame_width, frame_height=frame_height
            )
            for box in tile_boxes
        )
        change_rois = self._merge_rois(change_candidates)
        candidates = tuple(
            self._expand_change_roi(
                roi, frame_width=frame_width, frame_height=frame_height
            )
            for roi in change_rois
        )
        rois = self._merge_rois(candidates)
        coverage = sum(width * height for _, _, width, height in rois) / (
            frame_width * frame_height
        )
        candidate_region_count = len(rois)

        if changed_fraction >= self.full_frame_change_fraction:
            return DynamicRoiProposal(
                (full_frame,),
                changed_fraction,
                1.0,
                True,
                "widespread-change",
                (full_frame,),
                coverage,
                candidate_region_count,
            )

        if candidate_region_count > self.max_rois:
            return DynamicRoiProposal(
                (full_frame,),
                changed_fraction,
                1.0,
                True,
                "too-many-regions",
                change_rois,
                coverage,
                candidate_region_count,
            )
        if coverage >= self.max_coverage_fraction:
            return DynamicRoiProposal(
                (full_frame,),
                changed_fraction,
                1.0,
                True,
                "roi-coverage-too-large",
                change_rois,
                coverage,
                candidate_region_count,
            )
        return DynamicRoiProposal(
            rois,
            changed_fraction,
            coverage,
            False,
            "local-change",
            change_rois,
            coverage,
            candidate_region_count,
        )

    @staticmethod
    def _validate_frames(baseline: np.ndarray, current: np.ndarray) -> None:
        if not isinstance(baseline, np.ndarray) or not isinstance(current, np.ndarray):
            raise TypeError("baseline 和 current 必须是 numpy.ndarray")
        if baseline.shape != current.shape:
            raise ValueError("baseline 和 current 的尺寸必须一致")
        if current.ndim not in (2, 3):
            raise ValueError("frame 必须是灰度或 RGB/BGR 数组")
        if current.ndim == 3 and current.shape[2] < 3:
            raise ValueError("彩色 frame 至少需要三个通道")
        if current.shape[0] < 1 or current.shape[1] < 1:
            raise ValueError("frame 不能为空")

    def _sampled_difference(
        self, baseline: np.ndarray, current: np.ndarray
    ) -> np.ndarray:
        sample_width, sample_height = self.sample_size
        frame_height, frame_width = current.shape[:2]
        signed_samples: list[np.ndarray] = []
        for y_offset in (1, 3):
            y_indices = (
                (np.arange(sample_height, dtype=np.int64) * 4 + y_offset)
                * frame_height
                // (sample_height * 4)
            ).clip(0, frame_height - 1)
            for x_offset in (1, 3):
                x_indices = (
                    (np.arange(sample_width, dtype=np.int64) * 4 + x_offset)
                    * frame_width
                    // (sample_width * 4)
                ).clip(0, frame_width - 1)
                before = self._sample_luminance(baseline, y_indices, x_indices)
                after = self._sample_luminance(current, y_indices, x_indices)
                signed_samples.append(after.astype(np.int16) - before.astype(np.int16))

        stacked = np.stack(signed_samples, axis=0)
        global_shift = float(np.median(stacked))
        return np.max(np.abs(stacked.astype(np.float32) - global_shift), axis=0)

    @staticmethod
    def _sample_luminance(
        frame: np.ndarray, y_indices: np.ndarray, x_indices: np.ndarray
    ) -> np.ndarray:
        if frame.ndim == 2:
            return frame[y_indices[:, None], x_indices[None, :]].astype(
                np.uint8, copy=False
            )
        rgb = frame[y_indices[:, None], x_indices[None, :], :3].astype(
            np.uint16, copy=False
        )
        return (
            (rgb[..., 0] * 77 + rgb[..., 1] * 150 + rgb[..., 2] * 29) >> 8
        ).astype(np.uint8)

    def _active_tiles(self, changed: np.ndarray) -> np.ndarray:
        tile_width, tile_height = self.tile_size
        sample_height, sample_width = changed.shape
        tile_rows = (sample_height + tile_height - 1) // tile_height
        tile_columns = (sample_width + tile_width - 1) // tile_width
        padded = np.zeros(
            (tile_rows * tile_height, tile_columns * tile_width), dtype=bool
        )
        padded[:sample_height, :sample_width] = changed
        counts = padded.reshape(
            tile_rows, tile_height, tile_columns, tile_width
        ).sum(axis=(1, 3))
        return counts >= self.min_changed_samples

    @staticmethod
    def _dilate(active: np.ndarray, radius: int) -> np.ndarray:
        if radius == 0:
            return active
        height, width = active.shape
        result = np.zeros_like(active)
        for y_offset in range(-radius, radius + 1):
            source_top = max(0, -y_offset)
            source_bottom = min(height, height - y_offset)
            target_top = source_top + y_offset
            target_bottom = source_bottom + y_offset
            for x_offset in range(-radius, radius + 1):
                source_left = max(0, -x_offset)
                source_right = min(width, width - x_offset)
                target_left = source_left + x_offset
                target_right = source_right + x_offset
                result[target_top:target_bottom, target_left:target_right] |= active[
                    source_top:source_bottom, source_left:source_right
                ]
        return result

    @staticmethod
    def _connected_tile_boxes(
        active: np.ndarray,
    ) -> tuple[tuple[int, int, int, int], ...]:
        height, width = active.shape
        visited = np.zeros_like(active)
        boxes: list[tuple[int, int, int, int]] = []
        for top in range(height):
            for left in range(width):
                if not active[top, left] or visited[top, left]:
                    continue
                stack = [(left, top)]
                visited[top, left] = True
                min_x = max_x = left
                min_y = max_y = top
                while stack:
                    x, y = stack.pop()
                    min_x, max_x = min(min_x, x), max(max_x, x)
                    min_y, max_y = min(min_y, y), max(max_y, y)
                    for next_y in range(max(0, y - 1), min(height, y + 2)):
                        for next_x in range(max(0, x - 1), min(width, x + 2)):
                            if active[next_y, next_x] and not visited[next_y, next_x]:
                                visited[next_y, next_x] = True
                                stack.append((next_x, next_y))
                boxes.append((min_x, min_y, max_x + 1, max_y + 1))
        return tuple(boxes)

    def _tile_box_to_change_roi(
        self,
        box: tuple[int, int, int, int],
        *,
        frame_width: int,
        frame_height: int,
    ) -> OcrRoi:
        tile_width, tile_height = self.tile_size
        sample_width, sample_height = self.sample_size
        left_tile, top_tile, right_tile, bottom_tile = box
        left = int(left_tile * tile_width * frame_width // sample_width)
        top = int(top_tile * tile_height * frame_height // sample_height)
        right = int(np.ceil(right_tile * tile_width * frame_width / sample_width))
        bottom = int(
            np.ceil(bottom_tile * tile_height * frame_height / sample_height)
        )
        left, top = max(0, left), max(0, top)
        right, bottom = min(frame_width, right), min(frame_height, bottom)
        return left, top, right - left, bottom - top

    def _expand_change_roi(
        self,
        roi: OcrRoi,
        *,
        frame_width: int,
        frame_height: int,
    ) -> OcrRoi:
        left, top, width, height = roi
        right, bottom = left + width, top + height
        padding_x, padding_y = self.padding
        left, top = left - padding_x, top - padding_y
        right, bottom = right + padding_x, bottom + padding_y
        left, right = self._ensure_span(
            left, right, minimum=self.min_roi_size[0], limit=frame_width
        )
        top, bottom = self._ensure_span(
            top, bottom, minimum=self.min_roi_size[1], limit=frame_height
        )
        return left, top, right - left, bottom - top

    @staticmethod
    def _ensure_span(
        start: int, end: int, *, minimum: int, limit: int
    ) -> tuple[int, int]:
        start, end = max(0, start), min(limit, end)
        missing = min(limit, minimum) - (end - start)
        if missing > 0:
            before = missing // 2
            after = missing - before
            start -= before
            end += after
            if start < 0:
                end = min(limit, end - start)
                start = 0
            if end > limit:
                start = max(0, start - (end - limit))
                end = limit
        return start, end

    def _merge_rois(self, rois: tuple[OcrRoi, ...]) -> tuple[OcrRoi, ...]:
        pending = [self._edges(roi) for roi in rois]
        gap_x, gap_y = self.merge_gap
        changed = True
        while changed:
            changed = False
            merged: list[tuple[int, int, int, int]] = []
            while pending:
                current = pending.pop()
                index = 0
                while index < len(pending):
                    other = pending[index]
                    if self._near(current, other, gap_x=gap_x, gap_y=gap_y):
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
            pending = merged

        normalized = tuple(
            (left, top, right - left, bottom - top)
            for left, top, right, bottom in pending
            if right > left and bottom > top
        )
        return tuple(sorted(normalized, key=lambda roi: (roi[1], roi[0])))

    @staticmethod
    def _edges(roi: OcrRoi) -> tuple[int, int, int, int]:
        left, top, width, height = roi
        return left, top, left + width, top + height

    @staticmethod
    def _near(
        first: tuple[int, int, int, int],
        second: tuple[int, int, int, int],
        *,
        gap_x: int,
        gap_y: int,
    ) -> bool:
        return not (
            first[2] + gap_x < second[0]
            or second[2] + gap_x < first[0]
            or first[3] + gap_y < second[1]
            or second[3] + gap_y < first[1]
        )

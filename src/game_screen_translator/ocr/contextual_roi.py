from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, Sequence

from game_screen_translator.ocr.dynamic_roi import DynamicRoiProposal
from game_screen_translator.ocr.roi import OcrRoi
from game_screen_translator.ocr.types import OcrText


Bounds = tuple[int, int, int, int]
_SPACE_RE = re.compile(r"\s+")


class TextAnchor(Protocol):
    """Minimal view of an existing OCR track used for spatial association."""

    track_id: str
    text: str
    bounds: Bounds


@dataclass(frozen=True, slots=True)
class ContextualOcrRegion:
    roi: OcrRoi
    change_rois: tuple[OcrRoi, ...]
    affected_track_ids: tuple[str, ...]
    context_before_ids: tuple[str, ...]
    context_after_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContextualRoiPlan:
    regions: tuple[ContextualOcrRegion, ...]
    coverage_fraction: float
    fallback_full_frame: bool
    reason: str
    candidate_coverage_fraction: float = 0.0
    candidate_region_count: int = 0
    affected_track_count: int = 0


@dataclass(frozen=True, slots=True)
class ContextText:
    track_id: str
    text: str


@dataclass(frozen=True, slots=True)
class TranslationContextGroup:
    roi: OcrRoi
    targets: tuple[OcrText, ...]
    affected_track_ids: tuple[str, ...]
    context_before: tuple[ContextText, ...]
    context_after: tuple[ContextText, ...]


@dataclass(frozen=True, slots=True)
class ContextualOcrUpdate:
    """Filtered local OCR output and the old tracks it is allowed to replace."""

    observations: tuple[OcrText, ...]
    replace_track_ids: tuple[str, ...]
    context_groups: tuple[TranslationContextGroup, ...]


class ContextualRoiPlanner:
    """Expand tight change seeds with related OCR tracks, without sticky flood fill."""

    def __init__(
        self,
        *,
        direct_margin: int = 12,
        same_row_overlap: float = 0.35,
        same_row_gap_lines: float = 3.0,
        context_gap_lines: float = 2.5,
        context_horizontal_gap_lines: float = 4.0,
        ocr_padding: tuple[int, int] = (32, 24),
        min_roi_size: tuple[int, int] = (384, 96),
        merge_gap: tuple[int, int] = (24, 16),
        max_regions: int = 6,
        max_affected_tracks: int = 16,
        max_coverage_fraction: float = 0.45,
    ) -> None:
        if direct_margin < 0:
            raise ValueError("direct_margin 不能为负数")
        if not 0 <= same_row_overlap <= 1:
            raise ValueError("same_row_overlap 必须在 0 到 1 之间")
        if same_row_gap_lines < 0 or context_gap_lines < 0:
            raise ValueError("行间距倍数不能为负数")
        if context_horizontal_gap_lines < 0:
            raise ValueError("上下文水平间距倍数不能为负数")
        if any(value < 0 for value in ocr_padding + merge_gap):
            raise ValueError("padding 和 merge_gap 不能为负数")
        if min_roi_size[0] < 1 or min_roi_size[1] < 1:
            raise ValueError("min_roi_size 必须为正数")
        if max_regions < 1 or max_affected_tracks < 1:
            raise ValueError("区域和文字框上限必须大于 0")
        if not 0 < max_coverage_fraction <= 1:
            raise ValueError("max_coverage_fraction 必须在 0 到 1 之间")

        self.direct_margin = direct_margin
        self.same_row_overlap = same_row_overlap
        self.same_row_gap_lines = same_row_gap_lines
        self.context_gap_lines = context_gap_lines
        self.context_horizontal_gap_lines = context_horizontal_gap_lines
        self.ocr_padding = ocr_padding
        self.min_roi_size = min_roi_size
        self.merge_gap = merge_gap
        self.max_regions = max_regions
        self.max_affected_tracks = max_affected_tracks
        self.max_coverage_fraction = max_coverage_fraction

    def plan_proposal(
        self,
        proposal: DynamicRoiProposal,
        anchors: Sequence[TextAnchor],
        *,
        frame_size: tuple[int, int],
    ) -> ContextualRoiPlan:
        if proposal.fallback_full_frame:
            return self.plan(
                proposal.change_rois or proposal.rois,
                anchors,
                frame_size=frame_size,
                force_full_frame=True,
                fallback_reason=proposal.reason,
                fallback_candidate_coverage=proposal.candidate_coverage_fraction,
                fallback_candidate_region_count=proposal.candidate_region_count,
            )
        return self.plan(
            proposal.change_rois or proposal.rois,
            anchors,
            frame_size=frame_size,
        )

    def plan(
        self,
        change_rois: Sequence[OcrRoi],
        anchors: Sequence[TextAnchor],
        *,
        frame_size: tuple[int, int],
        force_full_frame: bool = False,
        fallback_reason: str = "upstream-full-frame",
        fallback_candidate_coverage: float = 1.0,
        fallback_candidate_region_count: int = 1,
        fallback_affected_track_count: int | None = None,
    ) -> ContextualRoiPlan:
        frame_width, frame_height = frame_size
        if frame_width < 1 or frame_height < 1:
            raise ValueError("frame_size 必须为正数")
        anchor_by_id = {anchor.track_id: anchor for anchor in anchors}
        if len(anchor_by_id) != len(anchors):
            raise ValueError("anchors 中存在重复 track_id")
        full_frame = (0, 0, frame_width, frame_height)
        if force_full_frame:
            region = ContextualOcrRegion(
                full_frame,
                (full_frame,),
                self._ordered_ids(anchors),
                (),
                (),
            )
            return ContextualRoiPlan(
                (region,),
                1.0,
                True,
                fallback_reason,
                fallback_candidate_coverage,
                fallback_candidate_region_count,
                (
                    len(anchors)
                    if fallback_affected_track_count is None
                    else fallback_affected_track_count
                ),
            )
        if not change_rois:
            return ContextualRoiPlan((), 0.0, False, "unchanged")

        provisional = tuple(
            self._region_for_seed(
                seed,
                anchors,
                frame_width=frame_width,
                frame_height=frame_height,
            )
            for seed in change_rois
        )
        regions = self._merge_regions(provisional)
        affected_count = len(
            {track_id for region in regions for track_id in region.affected_track_ids}
        )
        coverage = sum(
            region.roi[2] * region.roi[3] for region in regions
        ) / (frame_width * frame_height)
        if len(regions) > self.max_regions:
            return self.plan(
                (full_frame,),
                anchors,
                frame_size=frame_size,
                force_full_frame=True,
                fallback_reason="too-many-contextual-regions",
                fallback_candidate_coverage=coverage,
                fallback_candidate_region_count=len(regions),
                fallback_affected_track_count=affected_count,
            )
        if affected_count > self.max_affected_tracks:
            return self.plan(
                (full_frame,),
                anchors,
                frame_size=frame_size,
                force_full_frame=True,
                fallback_reason="too-many-affected-tracks",
                fallback_candidate_coverage=coverage,
                fallback_candidate_region_count=len(regions),
                fallback_affected_track_count=affected_count,
            )
        if coverage >= self.max_coverage_fraction:
            return self.plan(
                (full_frame,),
                anchors,
                frame_size=frame_size,
                force_full_frame=True,
                fallback_reason="contextual-coverage-too-large",
                fallback_candidate_coverage=coverage,
                fallback_candidate_region_count=len(regions),
                fallback_affected_track_count=affected_count,
            )
        return ContextualRoiPlan(
            regions,
            coverage,
            False,
            "contextual-local-change",
            coverage,
            len(regions),
            affected_count,
        )

    def _region_for_seed(
        self,
        seed: OcrRoi,
        anchors: Sequence[TextAnchor],
        *,
        frame_width: int,
        frame_height: int,
    ) -> ContextualOcrRegion:
        seed_bounds = self._roi_edges(seed)
        direct = {
            anchor.track_id
            for anchor in anchors
            if self._seed_relates_to_anchor(seed_bounds, anchor.bounds)
        }
        affected = set(direct)
        # Same-row chaining is intentionally the only recursive association.
        # It can recover fragmented OCR words, but cannot spread vertically
        # through a dense menu or paragraph.
        changed = True
        while changed and len(affected) <= self.max_affected_tracks:
            changed = False
            selected = tuple(anchor for anchor in anchors if anchor.track_id in affected)
            for candidate in anchors:
                if candidate.track_id in affected:
                    continue
                if any(self._same_row_neighbors(candidate.bounds, item.bounds) for item in selected):
                    affected.add(candidate.track_id)
                    changed = True

        affected_anchors = tuple(
            anchor for anchor in anchors if anchor.track_id in affected
        )
        content_bounds = self._union_bounds(
            (seed_bounds, *(anchor.bounds for anchor in affected_anchors))
        )
        roi = self._padded_roi(
            content_bounds, frame_width=frame_width, frame_height=frame_height
        )
        before, after = self._context_lines(
            content_bounds,
            anchors,
            excluded_ids=affected,
        )
        return ContextualOcrRegion(
            roi,
            (seed,),
            self._ordered_ids(affected_anchors),
            self._ordered_ids(before),
            self._ordered_ids(after),
        )

    def _seed_relates_to_anchor(self, seed: Bounds, anchor: Bounds) -> bool:
        if self._intersects(self._expand_bounds(seed, self.direct_margin), anchor):
            return True
        return self._same_row_neighbors(seed, anchor)

    def _same_row_neighbors(self, first: Bounds, second: Bounds) -> bool:
        first_height = max(1, first[3] - first[1])
        second_height = max(1, second[3] - second[1])
        overlap = max(0, min(first[3], second[3]) - max(first[1], second[1]))
        overlap_ratio = overlap / min(first_height, second_height)
        gap = self._horizontal_gap(first, second)
        line_height = max(first_height, second_height)
        return (
            overlap_ratio >= self.same_row_overlap
            and gap <= self.same_row_gap_lines * line_height
        )

    def _context_lines(
        self,
        content: Bounds,
        anchors: Sequence[TextAnchor],
        *,
        excluded_ids: set[str],
    ) -> tuple[tuple[TextAnchor, ...], tuple[TextAnchor, ...]]:
        content_height = max(1, content[3] - content[1])
        candidates_before: list[tuple[int, TextAnchor]] = []
        candidates_after: list[tuple[int, TextAnchor]] = []
        for anchor in anchors:
            if anchor.track_id in excluded_ids:
                continue
            line_height = max(content_height, anchor.bounds[3] - anchor.bounds[1], 1)
            horizontal_gap = self._horizontal_gap(content, anchor.bounds)
            if horizontal_gap > self.context_horizontal_gap_lines * line_height:
                continue
            if anchor.bounds[3] <= content[1]:
                gap = content[1] - anchor.bounds[3]
                if gap <= self.context_gap_lines * line_height:
                    candidates_before.append((gap, anchor))
            elif anchor.bounds[1] >= content[3]:
                gap = anchor.bounds[1] - content[3]
                if gap <= self.context_gap_lines * line_height:
                    candidates_after.append((gap, anchor))

        return (
            self._nearest_line(candidates_before),
            self._nearest_line(candidates_after),
        )

    @staticmethod
    def _nearest_line(
        candidates: Sequence[tuple[int, TextAnchor]],
    ) -> tuple[TextAnchor, ...]:
        if not candidates:
            return ()
        nearest_gap = min(gap for gap, _ in candidates)
        nearest = [anchor for gap, anchor in candidates if gap == nearest_gap]
        reference = min(nearest, key=lambda anchor: anchor.bounds[1])
        reference_center = (reference.bounds[1] + reference.bounds[3]) / 2
        reference_height = max(1, reference.bounds[3] - reference.bounds[1])
        line = tuple(
            anchor
            for _, anchor in candidates
            if abs((anchor.bounds[1] + anchor.bounds[3]) / 2 - reference_center)
            <= max(reference_height, anchor.bounds[3] - anchor.bounds[1]) * 0.5
        )
        return tuple(sorted(line, key=lambda anchor: (anchor.bounds[1], anchor.bounds[0])))

    def _padded_roi(
        self, bounds: Bounds, *, frame_width: int, frame_height: int
    ) -> OcrRoi:
        left, top, right, bottom = bounds
        padding_x, padding_y = self.ocr_padding
        left, top = left - padding_x, top - padding_y
        right, bottom = right + padding_x, bottom + padding_y
        left, right = self._ensure_span(
            left, right, minimum=self.min_roi_size[0], limit=frame_width
        )
        top, bottom = self._ensure_span(
            top, bottom, minimum=self.min_roi_size[1], limit=frame_height
        )
        return left, top, right - left, bottom - top

    def _merge_regions(
        self, regions: Sequence[ContextualOcrRegion]
    ) -> tuple[ContextualOcrRegion, ...]:
        pending = list(regions)
        changed = True
        while changed:
            changed = False
            merged: list[ContextualOcrRegion] = []
            while pending:
                current = pending.pop()
                index = 0
                while index < len(pending):
                    other = pending[index]
                    if self._rois_near(current.roi, other.roi):
                        current = self._merge_two_regions(current, other)
                        pending.pop(index)
                        changed = True
                    else:
                        index += 1
                merged.append(current)
            pending = merged
        return tuple(sorted(pending, key=lambda region: (region.roi[1], region.roi[0])))

    def _rois_near(self, first: OcrRoi, second: OcrRoi) -> bool:
        gap_x, gap_y = self.merge_gap
        a, b = self._roi_edges(first), self._roi_edges(second)
        return not (
            a[2] + gap_x < b[0]
            or b[2] + gap_x < a[0]
            or a[3] + gap_y < b[1]
            or b[3] + gap_y < a[1]
        )

    def _merge_two_regions(
        self, first: ContextualOcrRegion, second: ContextualOcrRegion
    ) -> ContextualOcrRegion:
        bounds = self._union_bounds((self._roi_edges(first.roi), self._roi_edges(second.roi)))
        roi = bounds[0], bounds[1], bounds[2] - bounds[0], bounds[3] - bounds[1]
        affected = set(first.affected_track_ids) | set(second.affected_track_ids)
        before = (set(first.context_before_ids) | set(second.context_before_ids)) - affected
        after = (set(first.context_after_ids) | set(second.context_after_ids)) - affected
        return ContextualOcrRegion(
            roi,
            tuple(sorted((*first.change_rois, *second.change_rois), key=lambda item: (item[1], item[0]))),
            tuple(sorted(affected)),
            tuple(sorted(before)),
            tuple(sorted(after)),
        )

    @staticmethod
    def _ordered_ids(anchors: Sequence[TextAnchor]) -> tuple[str, ...]:
        return tuple(
            anchor.track_id
            for anchor in sorted(anchors, key=lambda item: (item.bounds[1], item.bounds[0]))
        )

    @staticmethod
    def _roi_edges(roi: OcrRoi) -> Bounds:
        left, top, width, height = roi
        return left, top, left + width, top + height

    @staticmethod
    def _expand_bounds(bounds: Bounds, margin: int) -> Bounds:
        return (
            bounds[0] - margin,
            bounds[1] - margin,
            bounds[2] + margin,
            bounds[3] + margin,
        )

    @staticmethod
    def _intersects(first: Bounds, second: Bounds) -> bool:
        return not (
            first[2] <= second[0]
            or second[2] <= first[0]
            or first[3] <= second[1]
            or second[3] <= first[1]
        )

    @staticmethod
    def _horizontal_gap(first: Bounds, second: Bounds) -> int:
        if first[2] < second[0]:
            return second[0] - first[2]
        if second[2] < first[0]:
            return first[0] - second[2]
        return 0

    @staticmethod
    def _union_bounds(bounds: Sequence[Bounds]) -> Bounds:
        if not bounds:
            raise ValueError("至少需要一个 bounds")
        return (
            min(item[0] for item in bounds),
            min(item[1] for item in bounds),
            max(item[2] for item in bounds),
            max(item[3] for item in bounds),
        )

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


def _normalized_text(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip()


def _unchanged_anchor_for(
    item: OcrText,
    anchors: Sequence[TextAnchor],
) -> TextAnchor | None:
    normalized = _normalized_text(item.text)
    return next(
        (
            anchor
            for anchor in anchors
            if _normalized_text(anchor.text) == normalized
            and ContextualRoiPlanner._intersects(item.bounds, anchor.bounds)
        ),
        None,
    )


def build_translation_context_group(
    region: ContextualOcrRegion,
    observations: Sequence[OcrText],
    anchors: Sequence[TextAnchor],
) -> TranslationContextGroup:
    """Classify current OCR results as targets and old nearby tracks as context."""
    anchor_by_id = {anchor.track_id: anchor for anchor in anchors}
    target_zones = [ContextualRoiPlanner._roi_edges(roi) for roi in region.change_rois]
    target_zones.extend(
        anchor_by_id[track_id].bounds
        for track_id in region.affected_track_ids
        if track_id in anchor_by_id
    )
    affected_anchors = tuple(
        anchor_by_id[track_id]
        for track_id in region.affected_track_ids
        if track_id in anchor_by_id
    )

    unchanged_affected = {
        anchor.track_id
        for item in observations
        for anchor in (_unchanged_anchor_for(item, affected_anchors),)
        if anchor is not None
    }

    targets = tuple(
        sorted(
            (
                item
                for item in observations
                if any(
                    ContextualRoiPlanner._intersects(item.bounds, zone)
                    for zone in target_zones
                )
                and _unchanged_anchor_for(item, affected_anchors) is None
            ),
            key=lambda item: (item.bounds[1], item.bounds[0]),
        )
    )

    before_ids = list(region.context_before_ids)
    after_ids = list(region.context_after_ids)
    if targets:
        target_center_y = (
            min(item.bounds[1] for item in targets)
            + max(item.bounds[3] for item in targets)
        ) / 2
        for track_id in unchanged_affected:
            anchor = anchor_by_id[track_id]
            anchor_center_y = (anchor.bounds[1] + anchor.bounds[3]) / 2
            destination = before_ids if anchor_center_y <= target_center_y else after_ids
            if track_id not in destination:
                destination.append(track_id)

    def context_items(track_ids: Sequence[str]) -> tuple[ContextText, ...]:
        resolved = tuple(
            anchor_by_id[track_id]
            for track_id in dict.fromkeys(track_ids)
            if track_id in anchor_by_id
        )
        return tuple(
            ContextText(anchor.track_id, anchor.text)
            for anchor in sorted(resolved, key=lambda item: (item.bounds[1], item.bounds[0]))
        )

    return TranslationContextGroup(
        region.roi,
        targets,
        region.affected_track_ids,
        context_items(before_ids),
        context_items(after_ids),
    )


def build_contextual_ocr_update(
    plan: ContextualRoiPlan,
    observations: Sequence[OcrText],
    anchors: Sequence[TextAnchor],
) -> ContextualOcrUpdate:
    """Select the local OCR results that may update the global text map.

    OCR padding deliberately includes nearby stable lines so they can provide
    translation context. Those lines must not become duplicate tracker input.
    Only newly changed targets and OCR-confirmed versions of affected tracks
    are returned. A full-frame fallback replaces the complete old map.
    """
    groups = tuple(
        build_translation_context_group(region, observations, anchors)
        for region in plan.regions
    )
    replace_track_ids = tuple(
        dict.fromkeys(
            track_id
            for region in plan.regions
            for track_id in region.affected_track_ids
        )
    )
    if plan.fallback_full_frame:
        return ContextualOcrUpdate(
            tuple(
                sorted(
                    observations,
                    key=lambda item: (item.bounds[1], item.bounds[0]),
                )
            ),
            replace_track_ids,
            groups,
        )

    affected_id_set = set(replace_track_ids)
    affected_anchors = tuple(
        anchor for anchor in anchors if anchor.track_id in affected_id_set
    )
    targets = {item for group in groups for item in group.targets}
    selected = tuple(
        sorted(
            (
                item
                for item in observations
                if item in targets
                or _unchanged_anchor_for(item, affected_anchors) is not None
            ),
            key=lambda item: (item.bounds[1], item.bounds[0]),
        )
    )
    return ContextualOcrUpdate(selected, replace_track_ids, groups)

from __future__ import annotations

import unicodedata
from collections import deque
from dataclasses import dataclass
from typing import Iterable, Literal, Protocol, Sequence

from game_screen_translator.ocr.types import OcrText


Bounds = tuple[int, int, int, int]
Orientation = Literal["single", "horizontal", "vertical"]
HorizontalAmbiguityKind = Literal[
    "partial_chain",
    "candidate_margin",
    "menu_sentence_conflict",
]
HorizontalPartition = tuple[tuple[int, ...], ...]

_JAPANESE_LANGUAGES = {"ja", "japan", "japanese"}
_ENGLISH_LANGUAGES = {"en", "english"}
_KOREAN_LANGUAGES = {"ko", "korean"}
_CHINESE_LANGUAGES = {"ch", "chinese", "zh", "zh-cn", "zh-tw"}
_HARD_SENTENCE_ENDINGS = ("。", "！", "？", "!", "?", "」", "』")
_SENTENCE_ENDINGS = _HARD_SENTENCE_ENDINGS + ("…",)
_CLOSING_BRACKETS = (")", "]", "）", "】")
_CONTINUATION_ENDINGS = (
    "、",
    ",",
    "，",
    "・",
    "-",
    "‐",
    "‑",
    "—",
    "（",
    "(",
    "「",
    "『",
)
_HORIZONTAL_MERGE_MIN_SCORE = 0.68
_HORIZONTAL_MERGE_MIN_MARGIN = 0.06
_COMPACT_LABEL_MAX_VISUAL_SPAN = 12.0
_DENSE_PROSE_MIN_VISUAL_SPAN = 10.0
_MENU_SHORT_MAX_VISUAL_SPAN = 12.0
_MENU_REGULAR_MAX_VISUAL_SPAN = 18.0


class OcrLineLike(Protocol):
    track_id: str
    text: str
    confidence: float
    bounds: Bounds


@dataclass(frozen=True, slots=True)
class TranslationGroupMember:
    track_id: str
    text: str
    confidence: float
    bounds: Bounds

    @classmethod
    def from_line(cls, line: OcrLineLike) -> TranslationGroupMember:
        return cls(line.track_id, line.text, line.confidence, line.bounds)


@dataclass(frozen=True, slots=True)
class TranslationGroup:
    """A translation unit whose atomic OCR-line identities remain intact."""

    members: tuple[TranslationGroupMember, ...]
    orientation: Orientation
    row_breaks: tuple[int, ...] = ()
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.members:
            raise ValueError("翻译分组至少需要一个 OCR 行")
        member_ids = tuple(member.track_id for member in self.members)
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("翻译分组中存在重复 OCR 行")
        if any(index <= 0 or index >= len(self.members) for index in self.row_breaks):
            raise ValueError("翻译分组换行位置越界")
        if tuple(sorted(set(self.row_breaks))) != self.row_breaks:
            raise ValueError("翻译分组换行位置必须递增且唯一")
        if not 0 <= self.confidence <= 1:
            raise ValueError("翻译分组置信度必须在 0 到 1 之间")

    @property
    def member_ids(self) -> tuple[str, ...]:
        return tuple(member.track_id for member in self.members)

    @property
    def bounds(self) -> Bounds:
        return _union_bounds(tuple(member.bounds for member in self.members))

    @property
    def text(self) -> str:
        rows: list[str] = []
        start = 0
        for end in self.row_breaks + (len(self.members),):
            rows.append(_join_inline(member.text for member in self.members[start:end]))
            start = end
        return "\n".join(row for row in rows if row)

    @property
    def observation(self) -> OcrText:
        left, top, right, bottom = self.bounds
        return OcrText(
            self.text,
            self.confidence,
            ((left, top), (right, top), (right, bottom), (left, bottom)),
            self.member_ids,
        )


@dataclass(frozen=True, slots=True)
class HorizontalMergeDiagnostic:
    """Explain why two visual rows were merged or kept independent."""

    upper_member_ids: tuple[str, ...]
    lower_member_ids: tuple[str, ...]
    upper_text: str
    lower_text: str
    score: float | None
    merged: bool
    reason: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HorizontalMergeAmbiguity:
    """A bounded horizontal row block whose rule topology needs arbitration."""

    row_member_ids: tuple[tuple[str, ...], ...]
    row_texts: tuple[str, ...]
    row_bounds: tuple[Bounds, ...]
    kinds: tuple[HorizontalAmbiguityKind, ...]
    rule_partition: HorizontalPartition
    allowed_edges: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        row_count = len(self.row_member_ids)
        if row_count < 2:
            raise ValueError("歧义文字块至少需要两行")
        if len(self.row_texts) != row_count or len(self.row_bounds) != row_count:
            raise ValueError("歧义文字块的行信息数量不一致")
        member_ids = tuple(
            member_id
            for row_member_ids in self.row_member_ids
            for member_id in row_member_ids
        )
        if not member_ids or len(set(member_ids)) != len(member_ids):
            raise ValueError("歧义文字块成员为空或重复")
        if not self.kinds or len(set(self.kinds)) != len(self.kinds):
            raise ValueError("歧义文字块必须包含唯一的触发类型")
        validate_horizontal_partition(
            self.rule_partition,
            row_count=row_count,
            allowed_edges=self.allowed_edges,
        )

    @property
    def member_ids(self) -> tuple[str, ...]:
        return tuple(
            member_id
            for row_member_ids in self.row_member_ids
            for member_id in row_member_ids
        )


@dataclass(frozen=True, slots=True)
class _HorizontalPairEvaluation:
    score: float | None
    reason: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _TextRow:
    members: tuple[TranslationGroupMember, ...]

    @property
    def bounds(self) -> Bounds:
        return _union_bounds(tuple(member.bounds for member in self.members))

    @property
    def text(self) -> str:
        return _join_inline(member.text for member in self.members)

    @property
    def confidence(self) -> float:
        return min(member.confidence for member in self.members)


def build_translation_groups(
    lines: Iterable[OcrLineLike],
    *,
    source_language: str,
    merge_enabled: bool = True,
    diagnostics: list[HorizontalMergeDiagnostic] | None = None,
    ambiguities: list[HorizontalMergeAmbiguity] | None = None,
) -> tuple[TranslationGroup, ...]:
    """Build conservative translation groups without destroying OCR-line identity.

    Horizontal fragments are first consolidated into visual rows. Cross-row
    wrapping then uses one-to-one, mutual-best adjacency rather than an
    unrestricted connected component, so one ambiguous row cannot bridge two
    independent paragraphs. Japanese vertical grouping is enabled only for a
    Japanese OCR language and requires at least one clearly tall fragment.
    """

    members = tuple(
        sorted(
            (TranslationGroupMember.from_line(line) for line in lines),
            key=lambda member: (member.bounds[1], member.bounds[0], member.track_id),
        )
    )
    if not members:
        return ()
    if len({member.track_id for member in members}) != len(members):
        raise ValueError("OCR 行中存在重复 track_id")
    if not merge_enabled:
        return tuple(_single_group(member) for member in members)

    remaining = set(range(len(members)))
    groups: list[TranslationGroup] = []
    language = source_language.strip().lower()

    if language in _JAPANESE_LANGUAGES:
        for columns in _vertical_blocks(members):
            indices = tuple(index for column in columns for index in column)
            if len(indices) < 2:
                continue
            ordered_members = tuple(members[index] for index in indices)
            breaks: list[int] = []
            offset = 0
            for column in columns[:-1]:
                offset += len(column)
                breaks.append(offset)
            groups.append(
                TranslationGroup(
                    ordered_members,
                    "vertical",
                    tuple(breaks),
                    min(member.confidence for member in ordered_members),
                )
            )
            remaining.difference_update(indices)

    rows = _horizontal_rows(tuple(sorted(remaining)), members)
    menu_rows = _menu_like_rows(rows)
    margin_ambiguities: list[tuple[int, ...]] | None = (
        [] if ambiguities is not None else None
    )
    edges = _mutual_horizontal_edges(
        rows,
        language,
        menu_rows,
        diagnostics=diagnostics,
        margin_ambiguities=margin_ambiguities,
    )
    if ambiguities is not None:
        ambiguities.extend(
            _horizontal_merge_ambiguities(
                rows,
                language,
                edges,
                tuple(margin_ambiguities or ()),
            )
        )
    incoming = {lower: upper for upper, lower in edges.items()}
    consumed_rows: set[int] = set()
    for start in range(len(rows)):
        if start in incoming or start in consumed_rows:
            continue
        chain = [start]
        while chain[-1] in edges:
            next_row = edges[chain[-1]]
            if next_row in chain:
                break
            chain.append(next_row)
        consumed_rows.update(chain)
        groups.append(_horizontal_group(tuple(rows[index] for index in chain)))

    for index, row in enumerate(rows):
        if index not in consumed_rows:
            groups.append(_horizontal_group((row,)))

    return tuple(sorted(groups, key=lambda group: (group.bounds[1], group.bounds[0])))


class TranslationGroupStabilizer:
    """Confirm topology changes while refreshing text inside stable memberships."""

    def __init__(self, confirmations: int = 2) -> None:
        if confirmations < 1:
            raise ValueError("分组确认次数必须至少为 1")
        self.confirmations = confirmations
        self._confirmed: tuple[TranslationGroup, ...] | None = None
        self._candidate_key: tuple | None = None
        self._candidate_count = 0

    @property
    def has_pending(self) -> bool:
        return self._candidate_key is not None

    @property
    def confirmed(self) -> tuple[TranslationGroup, ...]:
        return () if self._confirmed is None else self._confirmed

    def reset(self) -> None:
        self._confirmed = None
        self._candidate_key = None
        self._candidate_count = 0

    def accept(self, groups: Sequence[TranslationGroup]) -> tuple[TranslationGroup, ...]:
        """Accept an externally arbitrated topology without another scan delay."""

        current = tuple(groups)
        self._confirmed = current
        self._candidate_key = None
        self._candidate_count = 0
        return current

    def update(
        self,
        groups: Sequence[TranslationGroup],
    ) -> tuple[TranslationGroup, ...]:
        current = tuple(groups)
        current_key = _topology_key(current)
        if self._confirmed is None:
            self._confirmed = current
            return current

        confirmed_key = _topology_key(self._confirmed)
        if current_key == confirmed_key:
            self._confirmed = current
            self._candidate_key = None
            self._candidate_count = 0
            return current

        if self.confirmations == 1:
            self._confirmed = current
            self._candidate_key = None
            self._candidate_count = 0
            return current

        if self._candidate_key == current_key:
            self._candidate_count += 1
        else:
            self._candidate_key = current_key
            self._candidate_count = 1

        if self._candidate_count >= self.confirmations:
            self._confirmed = current
            self._candidate_key = None
            self._candidate_count = 0
            return current

        # Keep the confirmed topology for one more observation, but never
        # resurrect members that are absent from the current atomic-line
        # snapshot.  A continuously scrolling page changes membership every
        # scan; mutating ``_confirmed`` here used to keep those departed lines
        # alive indefinitely and prevented the ordinary disappearance path
        # from ever running.
        return _refresh_confirmed_groups(self._confirmed, current)


def _single_group(member: TranslationGroupMember) -> TranslationGroup:
    return TranslationGroup((member,), "single", (), member.confidence)


def _vertical_blocks(
    members: Sequence[TranslationGroupMember],
) -> tuple[tuple[tuple[int, ...], ...], ...]:
    candidates = tuple(
        index
        for index, member in enumerate(members)
        if _width(member.bounds) <= _height(member.bounds) * 1.25
    )
    components = _components(
        candidates,
        lambda first, second: _same_vertical_column(
            members[first].bounds,
            members[second].bounds,
        ),
    )
    columns: list[tuple[int, ...]] = []
    for component in components:
        if len(component) < 2:
            continue
        # Three stacked square menu labels are not evidence of vertical text.
        if not any(
            _height(members[index].bounds) >= _width(members[index].bounds) * 1.6
            for index in component
        ):
            continue
        columns.append(
            tuple(
                sorted(
                    component,
                    key=lambda index: (
                        members[index].bounds[1],
                        members[index].bounds[0],
                    ),
                )
            )
        )

    if not columns:
        return ()
    column_bounds = tuple(
        _union_bounds(tuple(members[index].bounds for index in column))
        for column in columns
    )
    blocks = _components(
        tuple(range(len(columns))),
        lambda first, second: _neighboring_vertical_columns(
            column_bounds[first],
            column_bounds[second],
        ),
    )
    return tuple(
        tuple(
            columns[index]
            for index in sorted(
                component,
                key=lambda index: (-_center_x(column_bounds[index]), column_bounds[index][1]),
            )
        )
        for component in blocks
    )


def _same_vertical_column(first: Bounds, second: Bounds) -> bool:
    overlap = _axis_overlap(first[0], first[2], second[0], second[2])
    overlap_ratio = overlap / max(1, min(_width(first), _width(second)))
    center_distance = abs(_center_x(first) - _center_x(second))
    aligned = overlap_ratio >= 0.45 or center_distance <= max(
        _width(first), _width(second)
    ) * 0.40
    glyph_size = max(
        min(_width(first), _height(first)),
        min(_width(second), _height(second)),
    )
    return aligned and _vertical_gap(first, second) <= glyph_size * 1.15


def _neighboring_vertical_columns(first: Bounds, second: Bounds) -> bool:
    height_ratio = min(_height(first), _height(second)) / max(
        1, max(_height(first), _height(second))
    )
    if height_ratio < 0.45:
        return False
    vertical_overlap = _axis_overlap(first[1], first[3], second[1], second[3])
    overlap_ratio = vertical_overlap / max(1, min(_height(first), _height(second)))
    top_alignment = abs(first[1] - second[1])
    vertically_related = overlap_ratio >= 0.40 or top_alignment <= max(
        _width(first), _width(second)
    ) * 1.5
    horizontal_gap = _horizontal_gap(first, second)
    return vertically_related and horizontal_gap <= max(
        _width(first), _width(second)
    ) * 1.5


def _horizontal_rows(
    indices: Sequence[int],
    members: Sequence[TranslationGroupMember],
) -> tuple[_TextRow, ...]:
    components = _components(
        indices,
        lambda first, second: _same_visual_row(
            members[first],
            members[second],
        ),
    )
    rows = tuple(
        _TextRow(
            tuple(
                members[index]
                for index in sorted(
                    component,
                    key=lambda index: members[index].bounds[0],
                )
            )
        )
        for component in components
    )
    return tuple(sorted(rows, key=lambda row: (row.bounds[1], row.bounds[0])))


def _same_visual_row(
    first_member: TranslationGroupMember,
    second_member: TranslationGroupMember,
) -> bool:
    if not _has_letter(first_member.text) or not _has_letter(second_member.text):
        return False
    first = first_member.bounds
    second = second_member.bounds
    first_height = _height(first)
    second_height = _height(second)
    height_ratio = min(first_height, second_height) / max(first_height, second_height)
    if height_ratio < 0.55:
        return False
    overlap = _axis_overlap(first[1], first[3], second[1], second[3])
    overlap_ratio = overlap / max(1, min(first_height, second_height))
    return overlap_ratio >= 0.65 and _horizontal_gap(first, second) <= max(
        first_height, second_height
    ) * 0.75


def _mutual_horizontal_edges(
    rows: Sequence[_TextRow],
    language: str,
    menu_rows: set[int],
    *,
    diagnostics: list[HorizontalMergeDiagnostic] | None = None,
    margin_ambiguities: list[tuple[int, ...]] | None = None,
) -> dict[int, int]:
    candidates: list[tuple[int, int, float]] = []
    scored_candidates: list[tuple[int, int, float]] = []
    evaluations: list[tuple[int, int, _HorizontalPairEvaluation]] = []
    for upper_index, upper in enumerate(rows):
        for lower_index in range(upper_index + 1, len(rows)):
            lower = rows[lower_index]
            if upper_index in menu_rows or lower_index in menu_rows:
                if diagnostics is not None and lower_index == upper_index + 1:
                    diagnostics.append(
                        _horizontal_diagnostic(
                            upper,
                            lower,
                            score=None,
                            merged=False,
                            reason="规则短标签栈保持独立",
                        )
                    )
                continue
            evaluation = _horizontal_pair_evaluation(upper, lower, language)
            if evaluation.score is None:
                if diagnostics is not None and lower_index == upper_index + 1:
                    diagnostics.append(
                        _horizontal_diagnostic(
                            upper,
                            lower,
                            score=None,
                            merged=False,
                            reason=evaluation.reason,
                            evidence=evaluation.evidence,
                        )
                    )
                continue
            scored_candidates.append((upper_index, lower_index, evaluation.score))
            if _has_intervening_row(upper_index, lower_index, rows):
                if diagnostics is not None:
                    diagnostics.append(
                        _horizontal_diagnostic(
                            upper,
                            lower,
                            score=evaluation.score,
                            merged=False,
                            reason="两行之间存在其他文字行",
                            evidence=evaluation.evidence,
                        )
                    )
                continue
            candidates.append((upper_index, lower_index, evaluation.score))
            evaluations.append((upper_index, lower_index, evaluation))

    if margin_ambiguities is not None:
        scored_outgoing: dict[int, list[tuple[float, int]]] = {}
        scored_incoming: dict[int, list[tuple[float, int]]] = {}
        for upper, lower, score in scored_candidates:
            scored_outgoing.setdefault(upper, []).append((score, lower))
            scored_incoming.setdefault(lower, []).append((score, upper))
        for upper, choices in scored_outgoing.items():
            choices.sort(reverse=True)
            if (
                len(choices) > 1
                and choices[0][0] >= _HORIZONTAL_MERGE_MIN_SCORE
                and choices[0][0] - choices[1][0] < _HORIZONTAL_MERGE_MIN_MARGIN
            ):
                margin_ambiguities.append(
                    tuple(sorted({upper, choices[0][1], choices[1][1]}))
                )
        for lower, choices in scored_incoming.items():
            choices.sort(reverse=True)
            if (
                len(choices) > 1
                and choices[0][0] >= _HORIZONTAL_MERGE_MIN_SCORE
                and choices[0][0] - choices[1][0] < _HORIZONTAL_MERGE_MIN_MARGIN
            ):
                margin_ambiguities.append(
                    tuple(sorted({lower, choices[0][1], choices[1][1]}))
                )

    outgoing: dict[int, list[tuple[float, int]]] = {}
    incoming: dict[int, list[tuple[float, int]]] = {}
    for upper, lower, score in candidates:
        outgoing.setdefault(upper, []).append((score, lower))
        incoming.setdefault(lower, []).append((score, upper))
    for choices in outgoing.values():
        choices.sort(reverse=True)
    for choices in incoming.values():
        choices.sort(reverse=True)

    edges: dict[int, int] = {}
    candidate_reasons = {
        (upper, lower): "不是上行的最佳候选"
        for upper, lower, _score in candidates
    }
    for upper, choices in outgoing.items():
        best_score, lower = choices[0]
        incoming_choices = incoming.get(lower, ())
        if not incoming_choices or incoming_choices[0][1] != upper:
            candidate_reasons[(upper, lower)] = "不是下行的互选最佳候选"
            continue
        outgoing_margin = (
            best_score - choices[1][0] if len(choices) > 1 else 1.0
        )
        incoming_margin = (
            best_score - incoming_choices[1][0]
            if len(incoming_choices) > 1
            else 1.0
        )
        if best_score < _HORIZONTAL_MERGE_MIN_SCORE:
            candidate_reasons[(upper, lower)] = "合并分低于阈值"
            continue
        if outgoing_margin < _HORIZONTAL_MERGE_MIN_MARGIN:
            candidate_reasons[(upper, lower)] = "上行候选差距不足"
            if margin_ambiguities is not None:
                margin_ambiguities.append(
                    tuple(sorted({upper, lower, choices[1][1]}))
                )
            continue
        if incoming_margin < _HORIZONTAL_MERGE_MIN_MARGIN:
            candidate_reasons[(upper, lower)] = "下行候选差距不足"
            if margin_ambiguities is not None:
                margin_ambiguities.append(
                    tuple(sorted({upper, lower, incoming_choices[1][1]}))
                )
            continue
        edges[upper] = lower
        candidate_reasons[(upper, lower)] = "分数与互选边际均通过"

    if diagnostics is not None:
        for upper_index, lower_index, evaluation in evaluations:
            merged = edges.get(upper_index) == lower_index
            diagnostics.append(
                _horizontal_diagnostic(
                    rows[upper_index],
                    rows[lower_index],
                    score=evaluation.score,
                    merged=merged,
                    reason=candidate_reasons[(upper_index, lower_index)],
                    evidence=evaluation.evidence,
                )
            )
    return edges


def _horizontal_pair_score(
    upper: _TextRow,
    lower: _TextRow,
    language: str,
) -> float | None:
    return _horizontal_pair_evaluation(upper, lower, language).score


def _horizontal_pair_evaluation(
    upper: _TextRow,
    lower: _TextRow,
    language: str,
) -> _HorizontalPairEvaluation:
    if not _has_letter(upper.text) or not _has_letter(lower.text):
        return _HorizontalPairEvaluation(None, "缺少可合并的文字字符")
    if _has_hard_sentence_ending(upper.text):
        return _HorizontalPairEvaluation(None, "上一行已有明确句末")
    if not _scripts_compatible(upper.text, lower.text, language):
        return _HorizontalPairEvaluation(None, "上下行文字系统不兼容")

    upper_bounds = upper.bounds
    lower_bounds = lower.bounds
    if lower_bounds[1] <= upper_bounds[1]:
        return _HorizontalPairEvaluation(None, "下行不在上行下方")
    upper_height = _height(upper_bounds)
    lower_height = _height(lower_bounds)
    line_height = max(upper_height, lower_height)
    height_ratio = min(upper_height, lower_height) / line_height
    if height_ratio < 0.72:
        return _HorizontalPairEvaluation(None, "上下行字号差异过大")
    gap = _vertical_gap(upper_bounds, lower_bounds)
    if gap > line_height * 0.85:
        return _HorizontalPairEvaluation(None, "上下行间距过大")

    upper_width = _width(upper_bounds)
    lower_width = _width(lower_bounds)
    upper_visual_span = upper_width / max(1.0, line_height)
    lower_visual_span = lower_width / max(1.0, line_height)
    if upper_visual_span < 3.5:
        return _HorizontalPairEvaluation(None, "上一行视觉长度过短")

    left_distance = abs(upper_bounds[0] - lower_bounds[0])
    center_distance = abs(_center_x(upper_bounds) - _center_x(lower_bounds))
    left_quality = max(0.0, 1.0 - left_distance / max(1.0, line_height * 1.25))
    center_quality = max(0.0, 1.0 - center_distance / max(1.0, line_height * 1.25))
    alignment_quality = max(left_quality, center_quality)
    if alignment_quality <= 0:
        return _HorizontalPairEvaluation(None, "上下行未形成左对齐或居中关系")

    overlap = _axis_overlap(
        upper_bounds[0],
        upper_bounds[2],
        lower_bounds[0],
        lower_bounds[2],
    )
    overlap_ratio = overlap / max(1, min(upper_width, lower_width))
    if overlap_ratio < 0.35 and left_quality < 0.35:
        return _HorizontalPairEvaluation(None, "上下行水平重叠不足")

    upper_continues = upper.text.rstrip().endswith(_CONTINUATION_ENDINGS)
    lower_completes = _has_sentence_ending(lower.text)
    upper_is_longer = upper_width >= lower_width * 1.10
    dense_prose = (
        upper_visual_span >= _DENSE_PROSE_MIN_VISUAL_SPAN
        and lower_visual_span >= _DENSE_PROSE_MIN_VISUAL_SPAN
    )
    if _looks_like_compact_label_pair(
        upper,
        lower,
        upper_visual_span=upper_visual_span,
        lower_visual_span=lower_visual_span,
        height_ratio=height_ratio,
        gap=gap,
        line_height=line_height,
        alignment_quality=alignment_quality,
    ):
        return _HorizontalPairEvaluation(None, "两行更像独立的紧凑标签")
    evidence: list[str] = []
    if upper_continues:
        evidence.append("上一行续接标点")
    if lower_completes:
        evidence.append("下一行句末")
    if dense_prose:
        evidence.append("长行正文")
    if upper_is_longer:
        evidence.append("上一行较宽")
    if not (upper_continues or lower_completes or dense_prose):
        return _HorizontalPairEvaluation(
            None,
            "缺少续接标点、下一行句末或长正文证据",
            tuple(evidence),
        )
    if lower_width > upper_width * 1.25 and not upper_continues:
        return _HorizontalPairEvaluation(
            None,
            "下一行明显宽于上一行",
            tuple(evidence),
        )
    if upper_visual_span + lower_visual_span < 5.0 and not lower_completes:
        return _HorizontalPairEvaluation(
            None,
            "组合视觉长度过短",
            tuple(evidence),
        )

    gap_quality = max(0.0, 1.0 - gap / max(1.0, line_height * 0.85))
    overlap_quality = min(1.0, overlap_ratio)
    if upper_is_longer:
        width_quality = min(1.0, (upper_width / max(1, lower_width) - 1.0) / 0.35)
    else:
        width_quality = 0.35 if upper_continues or dense_prose else 0.15
    if upper_continues:
        ending_quality = 1.0
    elif lower_completes:
        ending_quality = 0.85
    else:
        ending_quality = 0.55
    length_quality = min(
        1.0,
        (upper_visual_span + lower_visual_span) / 20,
    )
    score = (
        gap_quality * 0.23
        + height_ratio * 0.20
        + alignment_quality * 0.20
        + overlap_quality * 0.14
        + width_quality * 0.10
        + ending_quality * 0.07
        + length_quality * 0.06
    )
    return _HorizontalPairEvaluation(
        score,
        "候选续行",
        tuple(evidence),
    )


def _looks_like_compact_label_pair(
    upper: _TextRow,
    lower: _TextRow,
    *,
    upper_visual_span: float,
    lower_visual_span: float,
    height_ratio: float,
    gap: int,
    line_height: int,
    alignment_quality: float,
) -> bool:
    if (
        _has_sentence_ending(upper.text)
        or _has_sentence_ending(lower.text)
        or upper.text.rstrip().endswith(_CONTINUATION_ENDINGS)
        or lower.text.rstrip().endswith(_CONTINUATION_ENDINGS)
    ):
        return False
    return (
        max(upper_visual_span, lower_visual_span)
        <= _COMPACT_LABEL_MAX_VISUAL_SPAN
        and height_ratio >= 0.80
        and gap <= line_height * 0.55
        and alignment_quality >= 0.65
    )


def _horizontal_diagnostic(
    upper: _TextRow,
    lower: _TextRow,
    *,
    score: float | None,
    merged: bool,
    reason: str,
    evidence: tuple[str, ...] = (),
) -> HorizontalMergeDiagnostic:
    return HorizontalMergeDiagnostic(
        tuple(member.track_id for member in upper.members),
        tuple(member.track_id for member in lower.members),
        upper.text,
        lower.text,
        score,
        merged,
        reason,
        evidence,
    )


def _has_intervening_row(
    upper_index: int,
    lower_index: int,
    rows: Sequence[_TextRow],
) -> bool:
    if lower_index == upper_index + 1:
        return False
    upper = rows[upper_index].bounds
    lower = rows[lower_index].bounds
    corridor_left = min(upper[0], lower[0])
    corridor_right = max(upper[2], lower[2])
    for row in rows[upper_index + 1 : lower_index]:
        bounds = row.bounds
        overlap = _axis_overlap(corridor_left, corridor_right, bounds[0], bounds[2])
        if overlap / max(1, min(corridor_right - corridor_left, _width(bounds))) >= 0.25:
            return True
    return False


def _regular_label_geometry_runs(
    rows: Sequence[_TextRow],
) -> tuple[tuple[int, ...], ...]:
    """Return regular 3+ row stacks without interpreting their punctuation."""

    runs: list[tuple[int, ...]] = []
    for start in range(len(rows)):
        run = [start]
        for index in range(start + 1, len(rows)):
            previous = rows[run[-1]].bounds
            current = rows[index].bounds
            line_height = max(_height(previous), _height(current))
            if _vertical_gap(previous, current) > line_height * 1.1:
                break
            height_ratio = min(_height(previous), _height(current)) / max(
                _height(previous), _height(current)
            )
            left_aligned = abs(previous[0] - current[0]) <= line_height * 1.25
            center_aligned = abs(_center_x(previous) - _center_x(current)) <= line_height * 1.25
            if height_ratio < 0.72 or not (left_aligned or center_aligned):
                break
            run.append(index)
        if len(run) < 3:
            continue
        widths = tuple(_width(rows[index].bounds) for index in run)
        visual_spans = tuple(
            _width(rows[index].bounds) / max(1, _height(rows[index].bounds))
            for index in run
        )
        short_labels = all(
            span <= _MENU_SHORT_MAX_VISUAL_SPAN
            for span in visual_spans
        )
        regular_widths = max(widths) / max(1, min(widths)) <= 1.55
        compact_regular_labels = regular_widths and all(
            span <= _MENU_REGULAR_MAX_VISUAL_SPAN
            for span in visual_spans
        )
        if short_labels or compact_regular_labels:
            candidate = tuple(run)
            if candidate not in runs:
                runs.append(candidate)
    return tuple(runs)


def _menu_like_rows(rows: Sequence[_TextRow]) -> set[int]:
    """Conservatively isolate regular stacks of short UI labels."""

    menu_rows: set[int] = set()
    for run in _regular_label_geometry_runs(rows):
        texts = tuple(rows[index].text.strip() for index in run)
        if any(
            _has_sentence_ending(text)
            or text.endswith(_CONTINUATION_ENDINGS)
            for text in texts
        ):
            continue
        menu_rows.update(run)
    return menu_rows


def _horizontal_geometry_edge(
    rows: Sequence[_TextRow],
    upper_index: int,
    lower_index: int,
    language: str,
    *,
    allow_intervening: bool = False,
) -> bool:
    """Return whether an arbiter may join two rows across rule-only evidence gates."""

    upper = rows[upper_index]
    lower = rows[lower_index]
    if not _has_letter(upper.text) or not _has_letter(lower.text):
        return False
    if _has_hard_sentence_ending(upper.text):
        return False
    if not _scripts_compatible(upper.text, lower.text, language):
        return False
    upper_bounds = upper.bounds
    lower_bounds = lower.bounds
    if lower_bounds[1] <= upper_bounds[1]:
        return False
    line_height = max(_height(upper_bounds), _height(lower_bounds))
    height_ratio = min(_height(upper_bounds), _height(lower_bounds)) / line_height
    if height_ratio < 0.72:
        return False
    if _vertical_gap(upper_bounds, lower_bounds) > line_height * 0.85:
        return False
    if _width(upper_bounds) / max(1.0, line_height) < 3.5:
        return False
    left_distance = abs(upper_bounds[0] - lower_bounds[0])
    center_distance = abs(_center_x(upper_bounds) - _center_x(lower_bounds))
    left_quality = max(0.0, 1.0 - left_distance / max(1.0, line_height * 1.25))
    center_quality = max(
        0.0,
        1.0 - center_distance / max(1.0, line_height * 1.25),
    )
    if max(left_quality, center_quality) <= 0:
        return False
    overlap = _axis_overlap(
        upper_bounds[0],
        upper_bounds[2],
        lower_bounds[0],
        lower_bounds[2],
    )
    overlap_ratio = overlap / max(1, min(_width(upper_bounds), _width(lower_bounds)))
    if overlap_ratio < 0.35 and left_quality < 0.35:
        return False
    return allow_intervening or not _has_intervening_row(
        upper_index,
        lower_index,
        rows,
    )


def _coherent_horizontal_runs(
    rows: Sequence[_TextRow],
    language: str,
) -> tuple[tuple[int, ...], ...]:
    runs: list[tuple[int, ...]] = []
    start = 0
    for upper_index in range(max(0, len(rows) - 1)):
        if _horizontal_geometry_edge(rows, upper_index, upper_index + 1, language):
            continue
        if upper_index + 1 - start >= 2:
            runs.append(tuple(range(start, upper_index + 1)))
        start = upper_index + 1
    if len(rows) - start >= 2:
        runs.append(tuple(range(start, len(rows))))
    return tuple(runs)


def _horizontal_merge_ambiguities(
    rows: Sequence[_TextRow],
    language: str,
    edges: dict[int, int],
    margin_ambiguities: Sequence[tuple[int, ...]],
) -> tuple[HorizontalMergeAmbiguity, ...]:
    triggers: list[tuple[set[int], HorizontalAmbiguityKind]] = []

    for run in _coherent_horizontal_runs(rows, language):
        if len(run) < 3:
            continue
        linked = tuple(edges.get(upper) == lower for upper, lower in zip(run, run[1:]))
        if any(linked) and not all(linked):
            triggers.append((set(run), "partial_chain"))

    for competing_rows in margin_ambiguities:
        if len(competing_rows) >= 3:
            triggers.append((set(competing_rows), "candidate_margin"))

    for run in _regular_label_geometry_runs(rows):
        sentence_conflict = any(
            not _has_hard_sentence_ending(rows[upper].text)
            and (
                rows[upper].text.rstrip().endswith(_CONTINUATION_ENDINGS)
                or _has_sentence_ending(rows[lower].text)
            )
            and _horizontal_geometry_edge(rows, upper, lower, language)
            for upper, lower in zip(run, run[1:])
        )
        fully_linked = all(
            edges.get(upper) == lower for upper, lower in zip(run, run[1:])
        )
        if sentence_conflict and not fully_linked:
            triggers.append((set(run), "menu_sentence_conflict"))

    if not triggers:
        return ()

    # A current rule chain must never be split between two independent requests.
    expanded: list[tuple[set[int], set[HorizontalAmbiguityKind]]] = []
    for indices, kind in triggers:
        changed = True
        while changed:
            changed = False
            for upper, lower in edges.items():
                if (upper in indices or lower in indices) and not {upper, lower} <= indices:
                    indices.update((upper, lower))
                    changed = True
        expanded.append((indices, {kind}))

    merged: list[tuple[set[int], set[HorizontalAmbiguityKind]]] = []
    for indices, kinds in expanded:
        overlap_indices = [
            index
            for index, (existing, _existing_kinds) in enumerate(merged)
            if existing & indices
        ]
        if not overlap_indices:
            merged.append((set(indices), set(kinds)))
            continue
        combined_indices = set(indices)
        combined_kinds = set(kinds)
        for index in reversed(overlap_indices):
            existing, existing_kinds = merged.pop(index)
            combined_indices.update(existing)
            combined_kinds.update(existing_kinds)
        merged.append((combined_indices, combined_kinds))

    kind_order: tuple[HorizontalAmbiguityKind, ...] = (
        "partial_chain",
        "candidate_margin",
        "menu_sentence_conflict",
    )
    result: list[HorizontalMergeAmbiguity] = []
    for global_indices, kinds in merged:
        ordered_indices = tuple(sorted(global_indices))
        if len(ordered_indices) < 2:
            continue
        local_index = {
            global_index: index for index, global_index in enumerate(ordered_indices)
        }
        allowed_edges = tuple(
            sorted(
                (local_index[upper], local_index[lower])
                for upper in ordered_indices
                for lower in ordered_indices
                if upper < lower
                and _horizontal_geometry_edge(
                    rows,
                    upper,
                    lower,
                    language,
                    allow_intervening="candidate_margin" in kinds,
                )
            )
        )
        rule_partition = _partition_from_edges(
            ordered_indices,
            edges,
            local_index,
        )
        result.append(
            HorizontalMergeAmbiguity(
                tuple(
                    tuple(member.track_id for member in rows[index].members)
                    for index in ordered_indices
                ),
                tuple(rows[index].text for index in ordered_indices),
                tuple(rows[index].bounds for index in ordered_indices),
                tuple(kind for kind in kind_order if kind in kinds),
                rule_partition,
                allowed_edges,
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda item: (item.row_bounds[0][1], item.row_bounds[0][0]),
        )
    )


def _partition_from_edges(
    ordered_indices: Sequence[int],
    edges: dict[int, int],
    local_index: dict[int, int],
) -> HorizontalPartition:
    included = set(ordered_indices)
    incoming = {
        lower
        for upper, lower in edges.items()
        if upper in included and lower in included
    }
    consumed: set[int] = set()
    groups: list[tuple[int, ...]] = []
    for start in ordered_indices:
        if start in incoming or start in consumed:
            continue
        chain = [start]
        while chain[-1] in edges and edges[chain[-1]] in included:
            lower = edges[chain[-1]]
            if lower in chain:
                break
            chain.append(lower)
        consumed.update(chain)
        groups.append(tuple(local_index[index] for index in chain))
    for index in ordered_indices:
        if index not in consumed:
            groups.append((local_index[index],))
    return tuple(sorted(groups, key=lambda group: group[0]))


def validate_horizontal_partition(
    partition: Sequence[Sequence[int]],
    *,
    row_count: int,
    allowed_edges: Sequence[tuple[int, int]],
) -> HorizontalPartition:
    """Validate an exact, ordered partition over a bounded ambiguity block."""

    if row_count < 1 or not partition:
        raise ValueError("分段结果不能为空")
    normalized = tuple(tuple(group) for group in partition)
    if any(not group for group in normalized):
        raise ValueError("分段结果中存在空组")
    flattened = tuple(index for group in normalized for index in group)
    if any(
        type(index) is not int or index < 0 or index >= row_count
        for index in flattened
    ):
        raise ValueError("分段结果包含越界行号")
    if len(flattened) != row_count or set(flattened) != set(range(row_count)):
        raise ValueError("分段结果必须不重不漏地覆盖全部行")
    if any(tuple(sorted(group)) != group for group in normalized):
        raise ValueError("每个分组内的行号必须按画面顺序递增")
    if tuple(sorted(normalized, key=lambda group: group[0])) != normalized:
        raise ValueError("分组必须按画面顺序排列")
    allowed = set(allowed_edges)
    for group in normalized:
        for upper, lower in zip(group, group[1:]):
            if (upper, lower) not in allowed:
                raise ValueError("分段结果跨越了不允许合并的明确边界")
    return normalized


def apply_horizontal_arbitration(
    groups: Sequence[TranslationGroup],
    ambiguity: HorizontalMergeAmbiguity,
    partition: Sequence[Sequence[int]],
) -> tuple[TranslationGroup, ...]:
    """Replace only one ambiguity block while preserving all atomic OCR identities."""

    normalized = validate_horizontal_partition(
        partition,
        row_count=len(ambiguity.row_member_ids),
        allowed_edges=ambiguity.allowed_edges,
    )
    affected = set(ambiguity.member_ids)
    members_by_id = {
        member.track_id: member
        for group in groups
        for member in group.members
    }
    if not affected <= members_by_id.keys():
        raise ValueError("仲裁文字块已经不属于当前分组快照")
    remaining: list[TranslationGroup] = []
    for group in groups:
        group_ids = set(group.member_ids)
        overlap = group_ids & affected
        if overlap and not group_ids <= affected:
            raise ValueError("仲裁文字块切断了现有规则分组")
        if not overlap:
            remaining.append(group)
    rows = tuple(
        _TextRow(tuple(members_by_id[member_id] for member_id in member_ids))
        for member_ids in ambiguity.row_member_ids
    )
    resolved = [
        _horizontal_group(tuple(rows[index] for index in row_group))
        for row_group in normalized
    ]
    return tuple(
        sorted(
            (*remaining, *resolved),
            key=lambda group: (group.bounds[1], group.bounds[0]),
        )
    )


def _horizontal_group(rows: Sequence[_TextRow]) -> TranslationGroup:
    members: list[TranslationGroupMember] = []
    row_breaks: list[int] = []
    for row in rows:
        if members:
            row_breaks.append(len(members))
        members.extend(row.members)
    orientation: Orientation = "single" if len(members) == 1 else "horizontal"
    return TranslationGroup(
        tuple(members),
        orientation,
        tuple(row_breaks),
        min(member.confidence for member in members),
    )


def _scripts_compatible(first: str, second: str, language: str) -> bool:
    first_scripts = _scripts(first)
    second_scripts = _scripts(second)
    if language in _JAPANESE_LANGUAGES:
        first_japanese = bool(first_scripts & {"kana", "han"})
        second_japanese = bool(second_scripts & {"kana", "han"})
        return (first_japanese and second_japanese) or (
            "latin" in first_scripts and "latin" in second_scripts
        )
    if language in _ENGLISH_LANGUAGES:
        return "latin" in first_scripts and "latin" in second_scripts
    if language in _KOREAN_LANGUAGES:
        return "hangul" in first_scripts and "hangul" in second_scripts
    if language in _CHINESE_LANGUAGES:
        return "han" in first_scripts and "han" in second_scripts
    return bool(first_scripts & second_scripts)


def _scripts(text: str) -> set[str]:
    result: set[str] = set()
    for character in text:
        codepoint = ord(character)
        if (
            0x3040 <= codepoint <= 0x30FF
            or 0x31F0 <= codepoint <= 0x31FF
            or 0xFF65 <= codepoint <= 0xFF9F
            or 0x1B000 <= codepoint <= 0x1B16F
        ):
            result.add("kana")
        elif (
            0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF
            or 0xF900 <= codepoint <= 0xFAFF
            or 0x20000 <= codepoint <= 0x323AF
        ):
            result.add("han")
        elif (
            0x1100 <= codepoint <= 0x11FF
            or 0x3130 <= codepoint <= 0x318F
            or 0xAC00 <= codepoint <= 0xD7AF
        ):
            result.add("hangul")
        elif "LATIN" in unicodedata.name(character, ""):
            result.add("latin")
    return result


def _refresh_confirmed_groups(
    confirmed: Sequence[TranslationGroup],
    current: Sequence[TranslationGroup],
) -> tuple[TranslationGroup, ...]:
    current_members = {
        member.track_id: member
        for group in current
        for member in group.members
    }
    refreshed: list[TranslationGroup] = []
    for group in confirmed:
        if any(member.track_id not in current_members for member in group.members):
            continue
        members = tuple(
            current_members[member.track_id]
            for member in group.members
        )
        refreshed.append(
            TranslationGroup(
                members,
                group.orientation,
                group.row_breaks,
                min(member.confidence for member in members),
            )
        )
    return tuple(sorted(refreshed, key=lambda group: (group.bounds[1], group.bounds[0])))


def _topology_key(groups: Sequence[TranslationGroup]) -> tuple:
    return tuple(
        sorted(
            (
                group.orientation,
                group.member_ids,
                group.row_breaks,
            )
            for group in groups
        )
    )


def _components(values: Sequence[int], related) -> tuple[tuple[int, ...], ...]:
    pending = set(values)
    components: list[tuple[int, ...]] = []
    while pending:
        root = min(pending)
        pending.remove(root)
        queue = deque((root,))
        component = [root]
        while queue:
            current = queue.popleft()
            neighbors = tuple(
                candidate for candidate in pending if related(current, candidate)
            )
            for candidate in neighbors:
                pending.remove(candidate)
                queue.append(candidate)
                component.append(candidate)
        components.append(tuple(component))
    return tuple(components)


def _join_inline(parts: Iterable[str]) -> str:
    result = ""
    for raw_part in parts:
        part = raw_part.strip()
        if not part:
            continue
        if result and _needs_space(result[-1], part[0]):
            result += " "
        result += part
    return result


def _needs_space(left: str, right: str) -> bool:
    return left.isascii() and right.isascii() and left.isalnum() and right.isalnum()


def _has_letter(text: str) -> bool:
    return any(unicodedata.category(character).startswith("L") for character in text)


def _has_hard_sentence_ending(text: str) -> bool:
    return _without_closing_brackets(text).endswith(_HARD_SENTENCE_ENDINGS)


def _has_sentence_ending(text: str) -> bool:
    return _without_closing_brackets(text).endswith(_SENTENCE_ENDINGS)


def _without_closing_brackets(text: str) -> str:
    stripped = text.rstrip()
    while stripped.endswith(_CLOSING_BRACKETS):
        stripped = stripped[:-1].rstrip()
    return stripped


def _union_bounds(bounds: Sequence[Bounds]) -> Bounds:
    return (
        min(item[0] for item in bounds),
        min(item[1] for item in bounds),
        max(item[2] for item in bounds),
        max(item[3] for item in bounds),
    )


def _width(bounds: Bounds) -> int:
    return max(1, bounds[2] - bounds[0])


def _height(bounds: Bounds) -> int:
    return max(1, bounds[3] - bounds[1])


def _center_x(bounds: Bounds) -> float:
    return (bounds[0] + bounds[2]) / 2


def _axis_overlap(
    first_start: int,
    first_end: int,
    second_start: int,
    second_end: int,
) -> int:
    return max(0, min(first_end, second_end) - max(first_start, second_start))


def _horizontal_gap(first: Bounds, second: Bounds) -> int:
    if first[2] < second[0]:
        return second[0] - first[2]
    if second[2] < first[0]:
        return first[0] - second[2]
    return 0


def _vertical_gap(first: Bounds, second: Bounds) -> int:
    if first[3] < second[1]:
        return second[1] - first[3]
    if second[3] < first[1]:
        return first[1] - second[3]
    return 0

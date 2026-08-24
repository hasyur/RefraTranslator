from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from game_screen_translator.ocr.grouping import (
    HorizontalMergeAmbiguity,
    HorizontalPartition,
    validate_horizontal_partition,
)


LayoutArbitrationKey = tuple[
    tuple[tuple[tuple[str, int], ...], ...],
    tuple[str, ...],
    HorizontalPartition,
    tuple[tuple[int, int], ...],
]
_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$",
    re.IGNORECASE | re.DOTALL,
)
_KIND_LABELS = {
    "partial_chain": "规则只合并了连续文字块的一部分",
    "candidate_margin": "一个连接候选与次优候选的分差不足",
    "menu_sentence_conflict": "规则同时看到了菜单排列与跨行句子证据",
}


class RevisionedOcrLineLike(Protocol):
    track_id: str
    revision: int
    text: str


class LayoutArbitrationProtocolError(ValueError):
    """Raised when a layout-arbitration response violates the closed schema."""


@dataclass(frozen=True, slots=True)
class LayoutArbitrationRequest:
    ambiguity: HorizontalMergeAmbiguity
    member_revisions: tuple[tuple[int, ...], ...]
    source_language: str

    def __post_init__(self) -> None:
        if len(self.member_revisions) != len(self.ambiguity.row_member_ids):
            raise ValueError("仲裁请求的 revision 行数不一致")
        for member_ids, revisions in zip(
            self.ambiguity.row_member_ids,
            self.member_revisions,
            strict=True,
        ):
            if len(member_ids) != len(revisions) or any(revision < 0 for revision in revisions):
                raise ValueError("仲裁请求的成员与 revision 不一致")

    @classmethod
    def from_ambiguity(
        cls,
        ambiguity: HorizontalMergeAmbiguity,
        lines: Sequence[RevisionedOcrLineLike],
        *,
        source_language: str,
    ) -> LayoutArbitrationRequest:
        revisions_by_id = {line.track_id: line.revision for line in lines}
        if len(revisions_by_id) != len(lines):
            raise ValueError("当前 OCR 行中存在重复 track_id")
        try:
            revisions = tuple(
                tuple(revisions_by_id[member_id] for member_id in member_ids)
                for member_ids in ambiguity.row_member_ids
            )
        except KeyError as exc:
            raise ValueError("歧义文字块已经不属于当前 OCR 行快照") from exc
        return cls(ambiguity, revisions, source_language.strip().lower())

    @property
    def member_versions(self) -> tuple[tuple[tuple[str, int], ...], ...]:
        return tuple(
            tuple(zip(member_ids, revisions, strict=True))
            for member_ids, revisions in zip(
                self.ambiguity.row_member_ids,
                self.member_revisions,
                strict=True,
            )
        )

    @property
    def key(self) -> LayoutArbitrationKey:
        return (
            self.member_versions,
            self.ambiguity.kinds,
            self.ambiguity.rule_partition,
            self.ambiguity.allowed_edges,
        )

    @property
    def member_ids(self) -> tuple[str, ...]:
        return self.ambiguity.member_ids

    def is_current(self, lines: Sequence[RevisionedOcrLineLike]) -> bool:
        current = {line.track_id: line.revision for line in lines}
        return all(
            current.get(member_id) == revision
            for row in self.member_versions
            for member_id, revision in row
        )


def build_layout_arbitration_prompt(request: LayoutArbitrationRequest) -> str:
    """Build a small closed-world segmentation prompt; no dialogue history is sent."""

    ambiguity = request.ambiguity
    heights = tuple(max(1, bounds[3] - bounds[1]) for bounds in ambiguity.row_bounds)
    scale = max(1.0, float(statistics.median(heights)))
    origin_left = min(bounds[0] for bounds in ambiguity.row_bounds)
    origin_top = min(bounds[1] for bounds in ambiguity.row_bounds)
    rows = []
    for index, (text, bounds) in enumerate(
        zip(ambiguity.row_texts, ambiguity.row_bounds, strict=True),
        start=1,
    ):
        rows.append(
            {
                "row": index,
                "text": text,
                "x": round((bounds[0] - origin_left) / scale, 2),
                "y": round((bounds[1] - origin_top) / scale, 2),
                "w": round((bounds[2] - bounds[0]) / scale, 2),
                "h": round((bounds[3] - bounds[1]) / scale, 2),
            }
        )
    rule_groups = [
        [index + 1 for index in group] for group in ambiguity.rule_partition
    ]
    allowed_edges = [
        [upper + 1, lower + 1] for upper, lower in ambiguity.allowed_edges
    ]
    trigger_labels = [_KIND_LABELS[kind] for kind in ambiguity.kinds]
    payload = json.dumps(
        {
            "source_language": request.source_language,
            "triggers": trigger_labels,
            "rows": rows,
            "rule_groups": rule_groups,
            "allowed_joins": allowed_edges,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        "你是游戏画面 OCR 文字分段仲裁器。只判断哪些视觉行属于同一个完整翻译单元，"
        "不要翻译、改写、补字或删字。结合语义、标点和归一化几何；菜单项、按钮和不同说话人的独立句子应分开，"
        "同一句的自动换行应合并。每一行必须且只能出现一次；组内相邻行只能使用 allowed_joins。"
        "有把握时只输出 JSON：{\"groups\":[[1,2],[3]]}。无法可靠判断时只输出 "
        "{\"decision\":\"UNSURE\"}。\n输入："
        + payload
    )


def parse_layout_arbitration_response(
    content: str,
    request: LayoutArbitrationRequest,
) -> HorizontalPartition | None:
    """Parse and validate an exact partition; ``None`` means explicit UNSURE."""

    body = content.strip()
    fence = _CODE_FENCE_RE.fullmatch(body)
    if fence is not None:
        body = fence.group("body").strip()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LayoutArbitrationProtocolError("仲裁响应不是有效 JSON") from exc
    if not isinstance(payload, Mapping):
        raise LayoutArbitrationProtocolError("仲裁响应根节点必须是对象")
    if payload.get("decision") == "UNSURE":
        if set(payload) != {"decision"}:
            raise LayoutArbitrationProtocolError("UNSURE 响应不能包含其他字段")
        return None
    if set(payload) != {"groups"}:
        raise LayoutArbitrationProtocolError("仲裁响应只能包含 groups")
    groups = payload.get("groups")
    if not isinstance(groups, list) or not groups:
        raise LayoutArbitrationProtocolError("groups 必须是非空数组")
    normalized: list[tuple[int, ...]] = []
    for group in groups:
        if not isinstance(group, list) or not group:
            raise LayoutArbitrationProtocolError("每个 groups 项必须是非空数组")
        if any(type(row_number) is not int for row_number in group):
            raise LayoutArbitrationProtocolError("groups 行号必须是整数")
        normalized.append(tuple(row_number - 1 for row_number in group))
    try:
        return validate_horizontal_partition(
            normalized,
            row_count=len(request.ambiguity.row_member_ids),
            allowed_edges=request.ambiguity.allowed_edges,
        )
    except ValueError as exc:
        raise LayoutArbitrationProtocolError(str(exc)) from exc

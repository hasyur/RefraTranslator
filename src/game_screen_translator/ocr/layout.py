from __future__ import annotations

import unicodedata
from collections import deque
from typing import Iterable, Sequence

from game_screen_translator.ocr.types import OcrText


Bounds = tuple[int, int, int, int]


def merge_ocr_text_blocks(observations: Iterable[OcrText]) -> tuple[OcrText, ...]:
    """Merge only strongly related OCR fragments into translation-sized blocks.

    Paddle returns recognition lines, not paragraphs. Keeping every detected line
    as an independent translation unit loses words split by wrapping and also
    interleaves fragments from adjacent Japanese vertical columns. This function
    uses conservative geometry only: vertical columns need narrow aligned boxes,
    while horizontal wrapping needs long, closely aligned rows.
    """

    items = tuple(observations)
    if len(items) < 2:
        return items

    remaining = set(range(len(items)))
    merged: list[OcrText] = []

    vertical_columns = _vertical_columns(items)
    for block in _vertical_blocks(vertical_columns, items):
        indices = tuple(index for column in block for index in column)
        if len(indices) < 2:
            continue
        merged.append(_merge_vertical_block(block, items))
        remaining.difference_update(indices)

    horizontal_components = _horizontal_components(
        tuple(sorted(remaining)),
        items,
    )
    for component in horizontal_components:
        if len(component) < 2 or not _has_horizontal_continuation(component, items):
            continue
        merged.append(_merge_horizontal_block(component, items))
        remaining.difference_update(component)

    merged.extend(items[index] for index in remaining)
    return tuple(sorted(merged, key=lambda item: (item.bounds[1], item.bounds[0])))


def _vertical_columns(items: Sequence[OcrText]) -> tuple[tuple[int, ...], ...]:
    candidates = tuple(
        index
        for index, item in enumerate(items)
        if _width(item.bounds) <= _height(item.bounds) * 1.25
    )
    components = _components(
        candidates,
        lambda first, second: _same_vertical_column(
            items[first].bounds,
            items[second].bounds,
        ),
    )
    columns: list[tuple[int, ...]] = []
    for component in components:
        has_tall_seed = any(
            _height(items[index].bounds) >= _width(items[index].bounds) * 1.6
            for index in component
        )
        if not has_tall_seed and len(component) < 3:
            continue
        columns.append(
            tuple(
                sorted(
                    component,
                    key=lambda index: (
                        items[index].bounds[1],
                        items[index].bounds[0],
                    ),
                )
            )
        )
    return tuple(columns)


def _vertical_blocks(
    columns: Sequence[tuple[int, ...]],
    items: Sequence[OcrText],
) -> tuple[tuple[tuple[int, ...], ...], ...]:
    column_bounds = tuple(
        _union_bounds(tuple(items[index].bounds for index in column))
        for column in columns
    )
    components = _components(
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
                key=lambda index: (
                    -_center_x(column_bounds[index]),
                    column_bounds[index][1],
                ),
            )
        )
        for component in components
    )


def _same_vertical_column(first: Bounds, second: Bounds) -> bool:
    overlap = _axis_overlap(first[0], first[2], second[0], second[2])
    overlap_ratio = overlap / max(1, min(_width(first), _width(second)))
    center_distance = abs(_center_x(first) - _center_x(second))
    aligned = overlap_ratio >= 0.35 or center_distance <= max(
        _width(first), _width(second)
    ) * 0.45
    glyph_size = max(
        min(_width(first), _height(first)),
        min(_width(second), _height(second)),
    )
    return aligned and _vertical_gap(first, second) <= glyph_size * 1.25


def _neighboring_vertical_columns(first: Bounds, second: Bounds) -> bool:
    vertical_overlap = _axis_overlap(first[1], first[3], second[1], second[3])
    overlap_ratio = vertical_overlap / max(1, min(_height(first), _height(second)))
    vertical_near = overlap_ratio >= 0.25 or _vertical_gap(first, second) <= max(
        _width(first), _width(second)
    )
    horizontal_gap = _horizontal_gap(first, second)
    return vertical_near and horizontal_gap <= max(_width(first), _width(second)) * 1.5


def _horizontal_components(
    indices: Sequence[int],
    items: Sequence[OcrText],
) -> tuple[tuple[int, ...], ...]:
    components = _components(
        indices,
        lambda first, second: _same_horizontal_block(
            items[first],
            items[second],
        ),
    )
    return tuple(
        tuple(
            sorted(
                component,
                key=lambda index: (
                    items[index].bounds[1],
                    items[index].bounds[0],
                ),
            )
        )
        for component in components
    )


def _same_horizontal_block(first_item: OcrText, second_item: OcrText) -> bool:
    if not _has_letter(first_item.text) or not _has_letter(second_item.text):
        return False
    first = first_item.bounds
    second = second_item.bounds
    first_height = _height(first)
    second_height = _height(second)
    line_height = max(first_height, second_height)
    vertical_overlap = _axis_overlap(first[1], first[3], second[1], second[3])
    row_overlap_ratio = vertical_overlap / max(1, min(first_height, second_height))
    if row_overlap_ratio >= 0.65:
        return _horizontal_gap(first, second) <= line_height * 0.75

    if _vertical_gap(first, second) > line_height * 0.70:
        return False
    first_width = _width(first)
    second_width = _width(second)
    if min(first_width, second_width) < line_height * 4.0:
        return False
    width_ratio = min(first_width, second_width) / max(first_width, second_width)
    if width_ratio < 0.55:
        return False
    horizontal_overlap = _axis_overlap(first[0], first[2], second[0], second[2])
    if horizontal_overlap / max(1, min(first_width, second_width)) < 0.55:
        return False
    left_aligned = abs(first[0] - second[0]) <= line_height * 1.25
    center_aligned = abs(_center_x(first) - _center_x(second)) <= line_height * 1.25
    return left_aligned or center_aligned


def _has_horizontal_continuation(
    component: Sequence[int],
    items: Sequence[OcrText],
) -> bool:
    rows = _horizontal_rows(component, items)
    if len(rows) < 2:
        # Multiple fragments on one row are safe to combine only when their
        # gap is small enough for _same_horizontal_block to connect them.
        return len(component) >= 2
    text_length = sum(len(items[index].text.strip()) for index in component)
    final_text = _join_inline(items[index].text for index in rows[-1]).rstrip()
    sentence_endings = ("。", "！", "？", "!", "?", "…", "」", "』", ")", "]")
    return text_length >= 14 or final_text.endswith(sentence_endings)


def _merge_vertical_block(
    columns: Sequence[Sequence[int]],
    items: Sequence[OcrText],
) -> OcrText:
    column_texts = [
        _join_inline(items[index].text for index in column)
        for column in columns
    ]
    indices = tuple(index for column in columns for index in column)
    return _merged_observation("\n".join(column_texts), indices, items)


def _merge_horizontal_block(
    component: Sequence[int],
    items: Sequence[OcrText],
) -> OcrText:
    rows = _horizontal_rows(component, items)
    text = "\n".join(
        _join_inline(items[index].text for index in row)
        for row in rows
    )
    return _merged_observation(text, component, items)


def _horizontal_rows(
    component: Sequence[int],
    items: Sequence[OcrText],
) -> tuple[tuple[int, ...], ...]:
    rows: list[list[int]] = []
    for index in sorted(
        component,
        key=lambda value: (items[value].bounds[1], items[value].bounds[0]),
    ):
        bounds = items[index].bounds
        destination = next(
            (
                row
                for row in rows
                if any(
                    _axis_overlap(
                        bounds[1],
                        bounds[3],
                        items[other].bounds[1],
                        items[other].bounds[3],
                    )
                    / max(1, min(_height(bounds), _height(items[other].bounds)))
                    >= 0.55
                    for other in row
                )
            ),
            None,
        )
        if destination is None:
            rows.append([index])
        else:
            destination.append(index)
    return tuple(
        tuple(sorted(row, key=lambda index: items[index].bounds[0]))
        for row in rows
    )


def _merged_observation(
    text: str,
    indices: Sequence[int],
    items: Sequence[OcrText],
) -> OcrText:
    bounds = _union_bounds(tuple(items[index].bounds for index in indices))
    left, top, right, bottom = bounds
    return OcrText(
        text,
        min(items[index].confidence for index in indices),
        ((left, top), (right, top), (right, bottom), (left, bottom)),
    )


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


def _components(
    values: Sequence[int],
    related,
) -> tuple[tuple[int, ...], ...]:
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


def _axis_overlap(first_start: int, first_end: int, second_start: int, second_end: int) -> int:
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

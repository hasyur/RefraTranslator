from dataclasses import dataclass

import pytest

from game_screen_translator.ocr.arbitration import (
    LayoutArbitrationProtocolError,
    LayoutArbitrationRequest,
    build_layout_arbitration_prompt,
    parse_layout_arbitration_response,
)
from game_screen_translator.ocr.grouping import HorizontalMergeAmbiguity


@dataclass(frozen=True, slots=True)
class _Line:
    track_id: str
    revision: int
    text: str


def _request() -> LayoutArbitrationRequest:
    ambiguity = HorizontalMergeAmbiguity(
        (("line-a",), ("line-b",), ("line-c",)),
        ("静かな夜に僕たちは", "古い約束の意味を探し", "歩き続けていた。"),
        ((40, 40, 400, 80), (40, 86, 400, 126), (40, 132, 360, 172)),
        ("partial_chain", "menu_sentence_conflict"),
        ((0,), (1, 2)),
        ((0, 1), (1, 2)),
    )
    return LayoutArbitrationRequest.from_ambiguity(
        ambiguity,
        (
            _Line("line-a", 3, "静かな夜に僕たちは"),
            _Line("line-b", 5, "古い約束の意味を探し"),
            _Line("line-c", 2, "歩き続けていた。"),
        ),
        source_language="japan",
    )


def test_layout_arbitration_prompt_is_closed_to_the_candidate_block() -> None:
    prompt = build_layout_arbitration_prompt(_request())

    assert "古い約束の意味を探し" in prompt
    assert '"rule_groups":[[1],[2,3]]' in prompt
    assert '"allowed_joins":[[1,2],[2,3]]' in prompt
    assert "不要翻译、改写、补字或删字" in prompt


def test_layout_arbitration_parser_accepts_exact_partition_and_unsure() -> None:
    request = _request()

    assert parse_layout_arbitration_response(
        '```json\n{"groups":[[1,2,3]]}\n```',
        request,
    ) == ((0, 1, 2),)
    assert (
        parse_layout_arbitration_response('{"decision":"UNSURE"}', request)
        is None
    )


@pytest.mark.parametrize(
    "response",
    (
        '{"groups":[[1,2],[2,3]]}',
        '{"groups":[[1,3],[2]]}',
        '{"groups":[[1],[2]]}',
        '{"groups":[[1,2,3]],"note":"ok"}',
        '{"decision":"UNSURE","groups":[[1],[2],[3]]}',
    ),
)
def test_layout_arbitration_parser_rejects_non_exact_or_cross_boundary_output(
    response: str,
) -> None:
    with pytest.raises(LayoutArbitrationProtocolError):
        parse_layout_arbitration_response(response, _request())


def test_layout_arbitration_request_detects_stale_revisions() -> None:
    request = _request()

    assert request.is_current(
        (
            _Line("line-a", 3, "same"),
            _Line("line-b", 5, "same"),
            _Line("line-c", 2, "same"),
        )
    )
    assert not request.is_current(
        (
            _Line("line-a", 4, "changed"),
            _Line("line-b", 5, "same"),
            _Line("line-c", 2, "same"),
        )
    )

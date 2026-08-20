from dataclasses import dataclass

from game_screen_translator.ocr.contextual_roi import (
    ContextualRoiPlanner,
    build_contextual_ocr_update,
    build_translation_context_group,
)
from game_screen_translator.ocr.dynamic_roi import DynamicRoiProposal
from game_screen_translator.ocr.types import OcrText


@dataclass(frozen=True)
class Anchor:
    track_id: str
    text: str
    bounds: tuple[int, int, int, int]


def _ocr(text: str, bounds: tuple[int, int, int, int]) -> OcrText:
    left, top, right, bottom = bounds
    return OcrText(
        text,
        0.99,
        ((left, top), (right, top), (right, bottom), (left, bottom)),
    )


def test_typewriter_suffix_absorbs_old_line_and_keeps_speaker_as_context() -> None:
    anchors = (
        Anchor("speaker", "旅人", (100, 250, 180, 280)),
        Anchor("line", "門は真夜中に", (100, 300, 340, 340)),
    )
    planner = ContextualRoiPlanner()

    plan = planner.plan(((335, 294, 120, 52),), anchors, frame_size=(1000, 600))

    assert not plan.fallback_full_frame
    assert len(plan.regions) == 1
    region = plan.regions[0]
    assert region.affected_track_ids == ("line",)
    assert region.context_before_ids == ("speaker",)
    left, top, width, height = region.roi
    assert left <= 100
    assert left + width >= 455
    assert top <= 294
    assert top + height >= 346


def test_same_row_fragments_chain_but_distant_label_does_not_stick() -> None:
    anchors = (
        Anchor("part-1", "The gate", (100, 300, 250, 340)),
        Anchor("part-2", "opens", (265, 300, 360, 340)),
        Anchor("part-3", "at midnight", (375, 300, 560, 340)),
        Anchor("unrelated", "OPTIONS", (850, 300, 980, 340)),
    )

    region = ContextualRoiPlanner().plan(
        ((545, 294, 80, 52),), anchors, frame_size=(1200, 700)
    ).regions[0]

    assert region.affected_track_ids == ("part-1", "part-2", "part-3")
    assert "unrelated" not in region.affected_track_ids


def test_new_wrapped_row_uses_previous_line_only_as_context() -> None:
    anchors = (
        Anchor("line-1", "川岸に沿って進み、", (120, 200, 500, 240)),
        Anchor("other-column", "INVENTORY", (850, 200, 1050, 240)),
    )

    region = ContextualRoiPlanner().plan(
        ((120, 280, 360, 56),), anchors, frame_size=(1200, 700)
    ).regions[0]

    assert region.affected_track_ids == ()
    assert region.context_before_ids == ("line-1",)
    assert "other-column" not in region.context_before_ids


def test_translation_group_selects_current_full_line_not_static_crop_text() -> None:
    anchors = (
        Anchor("speaker", "旅人", (100, 250, 180, 280)),
        Anchor("line", "門は真夜中に", (100, 300, 340, 340)),
    )
    region = ContextualRoiPlanner().plan(
        ((335, 294, 120, 52),), anchors, frame_size=(1000, 600)
    ).regions[0]
    observations = (
        _ocr("旅人", (100, 250, 180, 280)),
        _ocr("門は真夜中に開く。", (100, 300, 455, 340)),
        _ocr("OPTIONS", (500, 300, 620, 340)),
    )

    group = build_translation_context_group(region, observations, anchors)

    assert [item.text for item in group.targets] == ["門は真夜中に開く。"]
    assert [(item.track_id, item.text) for item in group.context_before] == [
        ("speaker", "旅人")
    ]
    assert group.context_after == ()


def test_unchanged_text_over_animated_background_is_not_sent_to_llm_again() -> None:
    anchors = (Anchor("line", "門は閉ざされている。", (100, 300, 440, 340)),)
    region = ContextualRoiPlanner().plan(
        ((220, 300, 80, 40),), anchors, frame_size=(1000, 600)
    ).regions[0]

    group = build_translation_context_group(
        region,
        (_ocr("門は閉ざされている。", (100, 300, 440, 340)),),
        anchors,
    )

    assert region.affected_track_ids == ("line",)
    assert group.targets == ()


def test_full_frame_background_fallback_does_not_retranslate_unchanged_text() -> None:
    anchors = (
        Anchor("speaker", "案内人", (100, 250, 180, 280)),
        Anchor("line", "この扉は固く閉ざされている。", (100, 300, 560, 340)),
    )
    proposal = DynamicRoiProposal(
        ((0, 0, 1000, 600),),
        0.4,
        1.0,
        True,
        "widespread-change",
        ((0, 0, 1000, 600),),
    )
    region = ContextualRoiPlanner().plan_proposal(
        proposal, anchors, frame_size=(1000, 600)
    ).regions[0]

    group = build_translation_context_group(
        region,
        (
            _ocr("案内人", (100, 250, 180, 280)),
            _ocr("この扉は固く閉ざされている。", (100, 300, 560, 340)),
        ),
        anchors,
    )

    assert group.targets == ()


def test_unchanged_affected_previous_row_becomes_translation_context() -> None:
    anchors = (
        Anchor("line-1", "川岸に沿って進み、", (100, 260, 440, 300)),
        Anchor("line-2-old", "失われた", (100, 320, 260, 360)),
    )
    region = ContextualRoiPlanner().plan(
        ((240, 318, 180, 48),), anchors, frame_size=(1000, 600)
    ).regions[0]
    observations = (
        _ocr("川岸に沿って進み、", (100, 260, 440, 300)),
        _ocr("失われた鍵を探す。", (100, 320, 440, 360)),
    )

    group = build_translation_context_group(region, observations, anchors)

    assert [item.text for item in group.targets] == ["失われた鍵を探す。"]
    assert "川岸に沿って進み、" in [item.text for item in group.context_before]


def test_upstream_fallback_rebuilds_full_screen_and_affects_all_tracks() -> None:
    anchors = (
        Anchor("one", "one", (10, 10, 100, 40)),
        Anchor("two", "two", (300, 200, 380, 240)),
    )
    proposal = DynamicRoiProposal(
        ((0, 0, 800, 600),),
        0.5,
        1.0,
        True,
        "widespread-change",
        ((0, 0, 800, 600),),
    )

    plan = ContextualRoiPlanner().plan_proposal(
        proposal, anchors, frame_size=(800, 600)
    )

    assert plan.fallback_full_frame
    assert plan.reason == "widespread-change"
    assert plan.regions[0].roi == (0, 0, 800, 600)
    assert plan.regions[0].affected_track_ids == ("one", "two")


def test_contextual_expansion_falls_back_when_coverage_is_too_large() -> None:
    planner = ContextualRoiPlanner(
        min_roi_size=(600, 400), max_coverage_fraction=0.25
    )

    plan = planner.plan(((300, 250, 20, 20),), (), frame_size=(800, 600))

    assert plan.fallback_full_frame
    assert plan.reason == "contextual-coverage-too-large"
    assert plan.regions[0].roi == (0, 0, 800, 600)


def test_neighboring_contextual_regions_merge_without_duplicate_track_ids() -> None:
    anchors = (
        Anchor("left", "A", (100, 300, 180, 340)),
        Anchor("right", "B", (310, 300, 390, 340)),
    )
    planner = ContextualRoiPlanner(min_roi_size=(120, 80), ocr_padding=(10, 10))

    plan = planner.plan(
        ((170, 300, 30, 40), (290, 300, 30, 40)),
        anchors,
        frame_size=(800, 600),
    )

    assert len(plan.regions) == 1
    assert set(plan.regions[0].affected_track_ids) == {"left", "right"}


def test_contextual_update_keeps_padding_context_out_of_tracker_input() -> None:
    anchors = (
        Anchor("speaker", "旅人", (100, 250, 180, 280)),
        Anchor("line", "門は真夜中に", (100, 300, 340, 340)),
    )
    plan = ContextualRoiPlanner().plan(
        ((335, 294, 120, 52),),
        anchors,
        frame_size=(1000, 600),
    )
    changed = _ocr("門は真夜中に開く。", (100, 300, 455, 340))
    padding_context = _ocr("旅人", (100, 250, 180, 280))

    update = build_contextual_ocr_update(
        plan,
        (padding_context, changed),
        anchors,
    )

    assert update.replace_track_ids == ("line",)
    assert update.observations == (changed,)
    assert [item.text for item in update.context_groups[0].context_before] == [
        "旅人"
    ]


def test_full_frame_contextual_update_returns_complete_ocr_map() -> None:
    anchors = (
        Anchor("one", "待って。", (10, 10, 160, 40)),
        Anchor("two", "進め。", (10, 80, 160, 110)),
    )
    proposal = DynamicRoiProposal(
        ((0, 0, 800, 600),),
        0.5,
        1.0,
        True,
        "widespread-change",
        ((0, 0, 800, 600),),
    )
    plan = ContextualRoiPlanner().plan_proposal(
        proposal,
        anchors,
        frame_size=(800, 600),
    )
    current = (
        _ocr("止まれ。", (10, 10, 160, 40)),
        _ocr("進め。", (10, 80, 160, 110)),
    )

    update = build_contextual_ocr_update(plan, current, anchors)

    assert update.observations == current
    assert update.replace_track_ids == ("one", "two")

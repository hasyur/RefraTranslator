from dataclasses import dataclass

from game_screen_translator.ocr.grouping import (
    TranslationGroupStabilizer,
    build_translation_groups,
)
from game_screen_translator.ocr.layout import merge_ocr_text_blocks
from game_screen_translator.ocr.text_filter import OcrTextFilter
from game_screen_translator.ocr.types import OcrText


def _ocr(text: str, bounds, confidence: float = 0.99) -> OcrText:
    left, top, right, bottom = bounds
    return OcrText(
        text,
        confidence,
        ((left, top), (right, top), (right, bottom), (left, bottom)),
    )


@dataclass(frozen=True, slots=True)
class _Line:
    track_id: str
    text: str
    confidence: float
    bounds: tuple[int, int, int, int]


def _line(track_id: str, text: str, bounds) -> _Line:
    return _Line(track_id, text, 0.99, bounds)


def test_merges_wrapped_horizontal_rows_into_one_translation_block() -> None:
    result = merge_ocr_text_blocks(
        (
            _ocr("この世界にはインター", (61, 75, 478, 124), 0.98),
            _ocr("ネットが存在する。", (56, 135, 412, 186), 0.96),
        )
    )

    assert len(result) == 1
    assert result[0].text == "この世界にはインター\nネットが存在する。"
    assert result[0].bounds == (56, 75, 478, 186)
    assert result[0].confidence == 0.96


def test_complete_horizontal_sentences_do_not_collapse_into_one_translation_id() -> None:
    observations = (
        _ocr("これは一つ目の完結した文章です。", (40, 40, 700, 80)),
        _ocr("これは二つ目の完結した文章です。", (40, 86, 700, 126)),
        _ocr("これは三つ目の完結した文章です。", (40, 132, 700, 172)),
    )

    assert merge_ocr_text_blocks(observations) == observations


def test_wrapped_sentence_merges_without_absorbing_the_next_complete_line() -> None:
    result = merge_ocr_text_blocks(
        (
            _ocr("この世界にはインター", (40, 40, 700, 80)),
            _ocr("ネットが存在する。", (40, 86, 620, 126)),
            _ocr("次の文章はここで完結する。", (40, 132, 700, 172)),
        )
    )

    assert [item.text for item in result] == [
        "この世界にはインター\nネットが存在する。",
        "次の文章はここで完結する。",
    ]


def test_ellipsis_can_continue_into_the_next_horizontal_row() -> None:
    result = merge_ocr_text_blocks(
        (
            _ocr("それは……", (40, 40, 700, 80)),
            _ocr("いや、何でもない。", (40, 86, 620, 126)),
        )
    )

    assert [item.text for item in result] == ["それは……\nいや、何でもない。"]


def test_orders_split_vertical_columns_right_to_left_before_merging() -> None:
    # This is the geometry emitted by PP-OCRv6 for a synthetic two-column
    # Japanese sample. Paddle's normal y/x order interleaves both columns.
    result = merge_ocr_text_blocks(
        (
            _ocr("希望はあ", (745, 256, 797, 469)),
            _ocr("こ", (820, 262, 856, 310)),
            _ocr("の世界に", (811, 300, 866, 515)),
            _ocr("る", (749, 460, 794, 512)),
        )
    )

    assert len(result) == 1
    assert result[0].text == "この世界に\n希望はある"
    assert result[0].bounds == (745, 256, 866, 515)


def test_merges_before_filtering_so_japanese_han_fragment_is_not_lost() -> None:
    merged = merge_ocr_text_blocks(
        (
            _ocr("希望", (800, 100, 840, 200)),
            _ocr("はある", (800, 195, 840, 330)),
        )
    )

    outcome = OcrTextFilter("japan").apply(merged)

    assert [item.text for item in outcome.accepted] == ["希望はある"]
    assert outcome.rejected == ()


def test_keeps_short_stacked_menu_entries_independent() -> None:
    observations = (
        _ocr("つづきから", (20, 20, 170, 60)),
        _ocr("設定", (20, 70, 100, 110)),
    )

    assert merge_ocr_text_blocks(observations) == observations


def test_keeps_two_long_menu_entries_independent() -> None:
    diagnostics = []
    groups = build_translation_groups(
        (
            _line("line-a", "はじめからつづける", (20, 20, 380, 60)),
            _line("line-b", "環境設定", (20, 66, 180, 106)),
        ),
        source_language="japan",
        diagnostics=diagnostics,
    )

    assert [group.text for group in groups] == [
        "はじめからつづける",
        "環境設定",
    ]
    assert len(diagnostics) == 1
    assert diagnostics[0].merged is False
    assert diagnostics[0].score is None
    assert diagnostics[0].reason == "两行更像独立的紧凑标签"


def test_upper_width_alone_does_not_merge_two_english_menu_entries() -> None:
    groups = build_translation_groups(
        (
            _line("line-a", "CONTINUE ADVENTURE", (20, 20, 660, 60)),
            _line("line-b", "OPTIONS", (20, 66, 300, 106)),
        ),
        source_language="english",
    )

    assert [group.text for group in groups] == [
        "CONTINUE ADVENTURE",
        "OPTIONS",
    ]


def test_menu_hotkey_suffix_is_not_treated_as_sentence_completion() -> None:
    diagnostics = []
    groups = build_translation_groups(
        (
            _line("line-a", "CONTINUE [A]", (20, 20, 380, 60)),
            _line("line-b", "OPTIONS [B]", (20, 66, 340, 106)),
        ),
        source_language="english",
        diagnostics=diagnostics,
    )

    assert [group.text for group in groups] == ["CONTINUE [A]", "OPTIONS [B]"]
    assert len(diagnostics) == 1
    assert diagnostics[0].reason == "两行更像独立的紧凑标签"


def test_merges_long_row_with_very_short_wrapped_tail() -> None:
    groups = build_translation_groups(
        (
            _line("line-a", "この世界にはまだ知られていない秘密が", (40, 40, 700, 80)),
            _line("line-b", "ある。", (40, 86, 180, 126)),
        ),
        source_language="japan",
    )

    assert len(groups) == 1
    assert groups[0].member_ids == ("line-a", "line-b")
    assert groups[0].text == "この世界にはまだ知られていない秘密が\nある。"


def test_merges_two_visually_long_prose_rows_without_terminal_punctuation() -> None:
    diagnostics = []
    groups = build_translation_groups(
        (
            _line(
                "line-a",
                "遠い街から来た旅人たちは古い記録を読みながら",
                (40, 40, 760, 80),
            ),
            _line(
                "line-b",
                "失われた答えを探して静かな道を歩き続ける",
                (40, 86, 720, 126),
            ),
        ),
        source_language="japan",
        diagnostics=diagnostics,
    )

    assert len(groups) == 1
    assert groups[0].member_ids == ("line-a", "line-b")
    assert len(diagnostics) == 1
    assert diagnostics[0].merged is True
    assert diagnostics[0].score is not None
    assert "长行正文" in diagnostics[0].evidence


def test_merges_dense_multiline_prose_before_the_final_punctuation() -> None:
    groups = build_translation_groups(
        (
            _line(
                "line-a",
                "この世界では誰も知らない出来事が静かに始まり",
                (40, 40, 760, 80),
            ),
            _line(
                "line-b",
                "遠い街から来た旅人たちは古い記録を読みながら",
                (40, 86, 760, 126),
            ),
            _line(
                "line-c",
                "失われた答えを探して歩き続けていた。",
                (40, 132, 650, 172),
            ),
        ),
        source_language="japan",
    )

    assert len(groups) == 1
    assert groups[0].member_ids == ("line-a", "line-b", "line-c")


def test_keeps_three_or_more_stacked_menu_entries_independent() -> None:
    observations = (
        _ocr("ロードしたデータ", (20, 20, 310, 60)),
        _ocr("新しいゲーム", (20, 68, 270, 108)),
        _ocr("環境設定", (20, 116, 230, 156)),
        _ocr("タイトルへ戻る", (20, 164, 300, 204)),
    )

    assert merge_ocr_text_blocks(observations) == observations


def test_square_stacked_labels_are_not_mistaken_for_vertical_japanese() -> None:
    observations = (
        _ocr("技", (100, 20, 140, 60)),
        _ocr("具", (100, 66, 140, 106)),
        _ocr("戻", (100, 112, 140, 152)),
    )

    assert merge_ocr_text_blocks(observations) == observations


def test_vertical_grouping_is_disabled_for_non_japanese_language() -> None:
    groups = build_translation_groups(
        (
            _line("line-a", "HEL", (100, 20, 140, 150)),
            _line("line-b", "LO", (100, 145, 140, 260)),
        ),
        source_language="english",
    )

    assert [group.text for group in groups] == ["HEL", "LO"]


def test_japanese_layout_does_not_merge_unrelated_latin_and_hangul_rows() -> None:
    groups = build_translation_groups(
        (
            _line("line-a", "Continue reading this passage", (40, 40, 600, 80)),
            _line("line-b", "다음 문장을 읽으세요", (40, 86, 500, 126)),
        ),
        source_language="japan",
    )

    assert [group.text for group in groups] == [
        "Continue reading this passage",
        "다음 문장을 읽으세요",
    ]


def test_group_topology_change_requires_two_matching_scans() -> None:
    stabilizer = TranslationGroupStabilizer(confirmations=2)
    initial = build_translation_groups(
        (
            _line("line-a", "これは別々の一行目", (40, 40, 500, 80)),
            _line("line-b", "離れた二行目。", (40, 180, 300, 220)),
        ),
        source_language="japan",
    )
    candidate = build_translation_groups(
        (
            _line("line-a", "これは別々の一行目", (40, 40, 500, 80)),
            _line("line-b", "離れた二行目。", (40, 86, 300, 126)),
        ),
        source_language="japan",
    )

    assert len(stabilizer.update(initial)) == 2
    assert len(stabilizer.update(candidate)) == 2
    assert stabilizer.has_pending
    assert len(stabilizer.update(candidate)) == 1
    assert not stabilizer.has_pending


def test_scrolling_membership_churn_never_resurrects_departed_lines() -> None:
    stabilizer = TranslationGroupStabilizer(confirmations=2)
    initial = build_translation_groups(
        (
            _line("line-a", "最初の行です。", (40, 40, 360, 80)),
            _line("line-b", "次の行です。", (40, 100, 360, 140)),
        ),
        source_language="japan",
    )
    second = build_translation_groups(
        (
            _line("line-b", "次の行です。", (40, 40, 360, 80)),
            _line("line-c", "新しい行です。", (40, 100, 360, 140)),
        ),
        source_language="japan",
    )
    third = build_translation_groups(
        (
            _line("line-c", "新しい行です。", (40, 40, 360, 80)),
            _line("line-d", "最後の行です。", (40, 100, 360, 140)),
        ),
        source_language="japan",
    )

    assert {member for group in stabilizer.update(initial) for member in group.member_ids} == {
        "line-a",
        "line-b",
    }
    after_second = stabilizer.update(second)
    after_third = stabilizer.update(third)

    assert {member for group in after_second for member in group.member_ids} == {"line-b"}
    assert after_third == ()
    assert stabilizer.has_pending
    assert {member for group in stabilizer.update(third) for member in group.member_ids} == {
        "line-c",
        "line-d",
    }
    assert not stabilizer.has_pending


def test_coordinate_jitter_refreshes_bounds_without_changing_topology() -> None:
    stabilizer = TranslationGroupStabilizer(confirmations=2)
    first = build_translation_groups(
        (
            _line("line-a", "この世界にはインター", (40, 40, 700, 80)),
            _line("line-b", "ネットが存在する。", (40, 86, 620, 126)),
        ),
        source_language="japan",
    )
    jittered = build_translation_groups(
        (
            _line("line-a", "この世界にはインター", (42, 42, 702, 82)),
            _line("line-b", "ネットが存在する。", (41, 88, 621, 128)),
        ),
        source_language="japan",
    )

    stabilizer.update(first)
    result = stabilizer.update(jittered)

    assert not stabilizer.has_pending
    assert len(result) == 1
    assert result[0].bounds == (41, 42, 702, 128)


def test_keeps_distant_paragraph_rows_independent() -> None:
    observations = (
        _ocr("これは一つ目の長い文章です。", (20, 20, 520, 60)),
        _ocr("これは別の場所にある文章です。", (20, 180, 520, 220)),
    )

    assert merge_ocr_text_blocks(observations) == observations

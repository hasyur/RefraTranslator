from dataclasses import dataclass

from game_screen_translator.ocr.grouping import (
    TranslationGroupStabilizer,
    apply_horizontal_arbitration,
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
    groups = build_translation_groups(
        (
            _line("line-a", "はじめからつづける", (20, 20, 380, 60)),
            _line("line-b", "環境設定", (20, 66, 180, 106)),
        ),
        source_language="japan",
    )

    assert [group.text for group in groups] == [
        "はじめからつづける",
        "環境設定",
    ]


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
    groups = build_translation_groups(
        (
            _line("line-a", "CONTINUE [A]", (20, 20, 380, 60)),
            _line("line-b", "OPTIONS [B]", (20, 66, 340, 106)),
        ),
        source_language="english",
    )

    assert [group.text for group in groups] == ["CONTINUE [A]", "OPTIONS [B]"]


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
    )

    assert len(groups) == 1
    assert groups[0].member_ids == ("line-a", "line-b")


def test_merges_dense_multiline_prose_before_the_final_punctuation() -> None:
    ambiguities = []
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
        ambiguities=ambiguities,
    )

    assert len(groups) == 1
    assert groups[0].member_ids == ("line-a", "line-b", "line-c")
    assert ambiguities == []


def test_merges_final_short_japanese_prose_line_without_merging_table_rows() -> None:
    # Captured geometry from the fixed crop: the final paragraph line contains
    # the sentence ending and footnote, but OCR gives it a taller box than the
    # preceding 22 px lines. Table entries occupy a separate right-hand column.
    raw_observations = (
        _ocr(
            "長期の保管に適していないため、自国における生産消費が大部分であり、貿易量は、世",
            (5, 8, 784, 30),
        ),
        _ocr("–, 1J50JJ", (1016, 1, 1105, 11), 0.6508),
        _ocr("1.9%0", (1132, 0, 1185, 13), 0.9049),
        _ocr("アンゴラ", (842, 25, 930, 53)),
        _ocr("1,680,146", (1013, 28, 1108, 52)),
        _ocr("1.8%", (1130, 25, 1186, 51)),
        _ocr(
            "界総計で年間30万トン程度・総生産に対して約0.3%程度と極めて少ない[65]。主要な輸",
            (4, 37, 784, 63),
        ),
        _ocr(
            "出国は、アメリカ合衆国、ベトナム、ラオス、エジプトなどで、特に米国は総輸出量の",
            (6, 73, 783, 95),
        ),
        _ocr("アメリカ合衆国", (843, 70, 990, 93)),
        _ocr("1,450,250", (1012, 69, 1109, 96)),
        _ocr("1.6%", (1131, 69, 1186, 95)),
        _ocr(
            "2/3程度を占めている。ー方主要な輸入国は、英国、オランダ、カナダ、フランス、日",
            (4, 106, 775, 128),
        ),
        _ocr("ベトナム", (843, 108, 931, 137)),
        _ocr("1,402,350", (1012, 109, 1109, 138)),
        _ocr("1.5%", (1130, 109, 1186, 136)),
        _ocr("本である[66]。", (1, 131, 125, 163)),
        _ocr("世界計", (837, 150, 904, 178)),
        _ocr("91,820,929", (1001, 151, 1108, 178)),
    )

    selected = OcrTextFilter("japan").select_layout_candidates(
        raw_observations,
        merge_enabled=True,
    )
    groups = build_translation_groups(
        tuple(
            _line(f"line-{index}", item.text, item.bounds)
            for index, item in enumerate(selected.accepted)
        ),
        source_language="japan",
    )

    paragraphs = [group for group in groups if "長期の保管" in group.text]
    assert len(paragraphs) == 1
    assert paragraphs[0].text.endswith("本である[66]。")
    assert paragraphs[0].member_ids == tuple(
        f"line-{index}"
        for index, item in enumerate(selected.accepted)
        if item.text in {
            "長期の保管に適していないため、自国における生産消費が大部分であり、貿易量は、世",
            "界総計で年間30万トン程度・総生産に対して約0.3%程度と極めて少ない[65]。主要な輸",
            "出国は、アメリカ合衆国、ベトナム、ラオス、エジプトなどで、特に米国は総輸出量の",
            "2/3程度を占めている。ー方主要な輸入国は、英国、オランダ、カナダ、フランス、日",
            "本である[66]。",
        }
    )
    assert {
        group.text for group in groups if group.text in {"アンゴラ", "アメリカ合衆国", "ベトナム"}
    } == {"アンゴラ", "アメリカ合衆国", "ベトナム"}


def test_merges_scaled_short_footnote_tail_by_relative_geometry() -> None:
    upper_text = "2/3程度を占めている。ー方主要な輸入国は、英国、オランダ、カナダ、フランス、日"
    lower_text = "本である[67]。"

    for scale in (1, 2):
        groups = build_translation_groups(
            (
                _line(
                    "upper",
                    upper_text,
                    tuple(value * scale for value in (4, 106, 775, 128)),
                ),
                _line(
                    "tail",
                    lower_text,
                    tuple(value * scale for value in (1, 131, 125, 163)),
                ),
            ),
            source_language="japan",
        )

        assert len(groups) == 1
        assert groups[0].member_ids == ("upper", "tail")
        assert groups[0].text == f"{upper_text}\n{lower_text}"


def test_reports_partial_chain_and_menu_sentence_conflict_as_one_block() -> None:
    ambiguities = []
    groups = build_translation_groups(
        (
            _line("line-a", "静かな夜に僕たちは", (40, 40, 400, 80)),
            _line("line-b", "古い約束の意味を探し", (40, 86, 400, 126)),
            _line("line-c", "歩き続けていた。", (40, 132, 360, 172)),
        ),
        source_language="japan",
        ambiguities=ambiguities,
    )

    assert [group.member_ids for group in groups] == [
        ("line-a",),
        ("line-b", "line-c"),
    ]
    assert len(ambiguities) == 1
    ambiguity = ambiguities[0]
    assert ambiguity.kinds == ("partial_chain", "menu_sentence_conflict")
    assert ambiguity.rule_partition == ((0,), (1, 2))
    assert ambiguity.allowed_edges == ((0, 1), (1, 2))

    resolved = apply_horizontal_arbitration(groups, ambiguity, ((0, 1, 2),))

    assert [group.member_ids for group in resolved] == [
        ("line-a", "line-b", "line-c"),
    ]


def test_reports_nearly_tied_branch_candidates_for_arbitration() -> None:
    ambiguities = []
    groups = build_translation_groups(
        (
            _line(
                "upper",
                "遠い街から来た旅人たちは記録を読む",
                (0, 20, 300, 60),
            ),
            _line("lower-a", "一つの答え。", (0, 66, 20, 106)),
            _line("lower-b", "別の答え。", (51, 66, 251, 106)),
        ),
        source_language="japan",
        ambiguities=ambiguities,
    )

    assert [group.member_ids for group in groups] == [
        ("upper", "lower-a"),
        ("lower-b",),
    ]
    assert len(ambiguities) == 1
    assert ambiguities[0].kinds == ("candidate_margin",)
    assert ambiguities[0].allowed_edges == ((0, 1), (0, 2))


def test_obvious_menu_stack_does_not_request_llm_arbitration() -> None:
    ambiguities = []
    groups = build_translation_groups(
        (
            _line("line-a", "はじめから", (40, 40, 320, 80)),
            _line("line-b", "つづきから", (40, 86, 320, 126)),
            _line("line-c", "設定", (40, 132, 260, 172)),
        ),
        source_language="japan",
        ambiguities=ambiguities,
    )

    assert [group.member_ids for group in groups] == [
        ("line-a",),
        ("line-b",),
        ("line-c",),
    ]
    assert ambiguities == []


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

from game_screen_translator.ocr.text_filter import OcrTextFilter
from game_screen_translator.ocr.types import OcrText


def _observation(
    text: str,
    *,
    confidence: float = 0.99,
    bounds: tuple[int, int, int, int] = (0, 0, 100, 30),
) -> OcrText:
    left, top, right, bottom = bounds
    return OcrText(
        text,
        confidence,
        ((left, top), (right, top), (right, bottom), (left, bottom)),
    )


def test_japanese_filter_keeps_kana_and_latin_sentences() -> None:
    outcome = OcrTextFilter("japan").apply(
        (_observation("待ってください。"), _observation("New Game"))
    )

    assert [item.text for item in outcome.accepted] == ["待ってください。", "New Game"]
    assert outcome.rejected == ()


def test_japanese_filter_drops_chinese_icons_numbers_and_status_codes() -> None:
    outcome = OcrTextFilter("japan").apply(
        (
            _observation("系统设置菜单"),
            _observation("⚙"),
            _observation("12:34"),
            _observation("A"),
            _observation("ESC"),
            _observation("GPU 99"),
        )
    )

    assert outcome.accepted == ()
    assert outcome.reason_counts == {
        "纯汉字/中文": 1,
        "图标/符号": 1,
        "纯数字": 1,
        "按键/短标签": 2,
        "状态缩写": 1,
    }


def test_han_only_and_latin_can_be_configured_independently() -> None:
    observations = (_observation("開始"), _observation("Continue"))

    outcome = OcrTextFilter(
        "japan",
        translate_han_only=True,
        translate_latin=False,
    ).apply(observations)

    assert [item.text for item in outcome.accepted] == ["開始"]
    assert [(item.observation.text, item.reason) for item in outcome.rejected] == [
        ("Continue", "英文已关闭")
    ]


def test_filter_can_be_disabled_without_changing_observations() -> None:
    observations = (_observation("中文"), _observation("⚙"))

    outcome = OcrTextFilter("japan", enabled=False).apply(observations)

    assert outcome.accepted == observations
    assert outcome.rejected == ()


def test_layout_candidate_filter_retains_recoverable_fragments_only() -> None:
    observations = (
        _observation("希望"),
        _observation("はある"),
        _observation("A"),
        _observation("⚙"),
        _observation("12:34"),
    )

    outcome = OcrTextFilter("japan").select_layout_candidates(
        observations,
        merge_enabled=True,
    )

    assert [item.text for item in outcome.accepted] == ["希望", "はある", "A"]
    assert [(item.observation.text, item.reason) for item in outcome.rejected] == [
        ("⚙", "图标/符号"),
        ("12:34", "纯数字"),
    ]


def test_layout_candidate_filter_is_strict_when_merging_is_disabled() -> None:
    outcome = OcrTextFilter("japan").select_layout_candidates(
        (_observation("希望"), _observation("A")),
        merge_enabled=False,
    )

    assert outcome.accepted == ()
    assert outcome.reason_counts == {"纯汉字/中文": 1, "按键/短标签": 1}


def test_drops_only_low_confidence_fragmented_alphanumeric_noise_at_top_edge() -> None:
    noise = _observation(
        "–, 1J50JJ",
        confidence=0.6508,
        bounds=(1016, 1, 1105, 11),
    )
    fragmented_noise = _observation(
        "7K22RR",
        confidence=0.65,
        bounds=(1016, 1, 1105, 11),
    )
    retained = tuple(
        _observation(
            text,
            confidence=0.6508,
            bounds=(20, 1, 140, 24),
        )
        for text in ("RTX4090", "Windows11", "3DMark", "H2O", "A100")
    )

    outcome = OcrTextFilter("japan").select_layout_candidates(
        (noise, fragmented_noise, *retained),
        merge_enabled=True,
    )

    assert outcome.accepted == retained
    assert [(item.observation.text, item.reason) for item in outcome.rejected] == [
        ("–, 1J50JJ", "边缘疑似 OCR 噪声"),
        ("7K22RR", "边缘疑似 OCR 噪声"),
    ]


def test_edge_noise_heuristic_requires_low_confidence_and_the_top_edge() -> None:
    observations = (
        _observation("–, 1J50JJ", confidence=0.91, bounds=(20, 1, 109, 11)),
        _observation("–, 1J50JJ", confidence=0.6508, bounds=(20, 3, 109, 13)),
        _observation("アンゴラ", confidence=0.6508, bounds=(20, 1, 109, 28)),
        _observation("スキル1A2B3", confidence=0.65, bounds=(20, 1, 109, 20)),
        _observation("製品1A2B3", confidence=0.65, bounds=(20, 1, 109, 20)),
    )

    outcome = OcrTextFilter("japan").select_layout_candidates(
        observations,
        merge_enabled=True,
    )

    assert outcome.accepted == observations
    assert outcome.rejected == ()


def test_disabled_filter_keeps_edge_alphanumeric_noise_unchanged() -> None:
    noise = _observation(
        "–, 1J50JJ",
        confidence=0.6508,
        bounds=(1016, 1, 1105, 11),
    )

    outcome = OcrTextFilter("japan", enabled=False).select_layout_candidates(
        (noise,),
        merge_enabled=True,
    )

    assert outcome.accepted == (noise,)
    assert outcome.rejected == ()

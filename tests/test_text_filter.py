from game_screen_translator.ocr.text_filter import OcrTextFilter
from game_screen_translator.ocr.types import OcrText


def _observation(text: str) -> OcrText:
    return OcrText(text, 0.99, ((0, 0), (100, 0), (100, 30), (0, 30)))


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

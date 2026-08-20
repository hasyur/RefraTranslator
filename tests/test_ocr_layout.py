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


def test_keeps_distant_paragraph_rows_independent() -> None:
    observations = (
        _ocr("これは一つ目の長い文章です。", (20, 20, 520, 60)),
        _ocr("これは別の場所にある文章です。", (20, 180, 520, 220)),
    )

    assert merge_ocr_text_blocks(observations) == observations

import pytest

from game_screen_translator.domain import (
    ContextPair,
    GlossaryEntry,
    SourceText,
    TranslationBatch,
)
from game_screen_translator.translation.hy_mt import (
    HyMtPromptBuilder,
    HyMtResponseParser,
    TranslationProtocolError,
)


def _batch() -> TranslationBatch:
    return TranslationBatch(
        (
            SourceText("dialogue", "a", 1, 'A < B & "quoted"'),
            SourceText("dialogue", "b", 4, "急げ。"),
        )
    )


def test_prompt_uses_native_tags_and_escapes_source() -> None:
    batch = _batch()
    prompt = HyMtPromptBuilder().build(
        batch,
        glossary=(GlossaryEntry("フィクサー", "中间人"),),
        context=(ContextPair("仕事は片付いた。", "活儿已经处理完了。"),),
    )

    assert "フィクサー 翻译成 中间人" in prompt
    assert "仕事は片付いた。" in prompt
    assert "A &lt; B &amp; &quot;quoted&quot;" in prompt
    assert '<sn id="1">' in prompt
    assert '<sn id="2">' in prompt
    assert batch.items[0].wire_id not in prompt
    assert batch.items[1].wire_id not in prompt
    assert "<target>" in prompt


def test_parser_accepts_code_fence_and_preserves_requested_order() -> None:
    batch = _batch()
    first, second = (item.wire_id for item in batch.items)
    response = f"""```xml
<target>
  <sn id="2">快点。</sn>
  <sn id="1">A 小于 B。</sn>
</target>
```"""

    parsed = HyMtResponseParser().parse(response, (first, second))

    assert list(parsed) == [first, second]
    assert parsed == {first: "A 小于 B。", second: "快点。"}


def test_parser_accepts_sn_fragments_with_surrounding_prose() -> None:
    batch = _batch()
    first, second = (item.wire_id for item in batch.items)
    response = '结果如下：<sn id="1">甲</sn><sn id="2">乙</sn>完毕'

    assert HyMtResponseParser().parse(response, (first, second)) == {
        first: "甲",
        second: "乙",
    }


def test_parser_repairs_only_missing_closing_id_quote() -> None:
    batch = _batch()
    first, second = (item.wire_id for item in batch.items)
    response = (
        '<target><sn id="1>甲</sn>'
        '<sn id="2>乙</sn></target>'
    )

    assert HyMtResponseParser().parse(response, (first, second)) == {
        first: "甲",
        second: "乙",
    }


def test_parser_accepts_plain_translation_for_single_item_only() -> None:
    batch = TranslationBatch((SourceText("dialogue", "a", 1, "待って。"),))
    wire_id = batch.items[0].wire_id

    assert HyMtResponseParser().parse("等等。", (wire_id,)) == {wire_id: "等等。"}
    assert HyMtResponseParser().parse("<target>等等。</target>", (wire_id,)) == {
        wire_id: "等等。"
    }

    with pytest.raises(TranslationProtocolError, match="没有"):
        HyMtResponseParser().parse("甲\n乙", ("first", "second"))


def test_parser_accepts_single_sn_without_id() -> None:
    batch = TranslationBatch((SourceText("dialogue", "a", 1, "待って。"),))
    wire_id = batch.items[0].wire_id

    assert HyMtResponseParser().parse("<sn>等等。</sn>", (wire_id,)) == {
        wire_id: "等等。"
    }


@pytest.mark.parametrize(
    "response",
    [
        '<target><sn id="bad">甲</sn><sn id="bad">乙</sn></target>',
        '<target><sn>甲</sn><sn>乙</sn></target>',
        '<target><sn id="screen-text">甲</sn><sn id="other-text">乙</sn></target>',
    ],
)
def test_parser_falls_back_to_order_when_ids_are_unusable(response: str) -> None:
    batch = _batch()
    first, second = (item.wire_id for item in batch.items)

    assert HyMtResponseParser().parse(response, (first, second)) == {
        first: "甲",
        second: "乙",
    }


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ('<target><sn id="1">甲</sn></target>', "数量"),
        (
            '<target><sn id="1">甲</sn><sn id="2">乙</sn>'
            '<sn id="3">丙</sn></target>',
            "数量",
        ),
        ('<target><sn id="1"></sn><sn id="2">乙</sn></target>', "为空"),
    ],
)
def test_parser_rejects_unsafe_positional_fallback(response: str, message: str) -> None:
    batch = _batch()
    expected = tuple(item.wire_id for item in batch.items)

    with pytest.raises(TranslationProtocolError, match=message):
        HyMtResponseParser().parse(response, expected)


def test_parser_repairs_unquoted_ids_and_bare_ampersands() -> None:
    batch = _batch()
    first, second = (item.wire_id for item in batch.items)
    response = '<target><sn id=1>甲 & 乙</sn><sn id=2>丙</sn></target>'

    assert HyMtResponseParser().parse(response, (first, second)) == {
        first: "甲 & 乙",
        second: "丙",
    }


def test_parser_salvages_complete_items_from_malformed_target_wrapper() -> None:
    batch = _batch()
    first, second = (item.wire_id for item in batch.items)
    response = (
        '<target broken><sn id="1">甲</sn>'
        '<sn id="2">乙</sn></target>'
    )

    assert HyMtResponseParser().parse(response, (first, second)) == {
        first: "甲",
        second: "乙",
    }

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
    assert f'<sn id="{batch.items[0].wire_id}">' in prompt
    assert "<target>" in prompt


def test_parser_accepts_code_fence_and_preserves_requested_order() -> None:
    batch = _batch()
    first, second = (item.wire_id for item in batch.items)
    response = f"""```xml
<target>
  <sn id="{second}">快点。</sn>
  <sn id="{first}">A 小于 B。</sn>
</target>
```"""

    parsed = HyMtResponseParser().parse(response, (first, second))

    assert list(parsed) == [first, second]
    assert parsed == {first: "A 小于 B。", second: "快点。"}


def test_parser_accepts_sn_fragments_with_surrounding_prose() -> None:
    batch = _batch()
    first, second = (item.wire_id for item in batch.items)
    response = f'结果如下：<sn id="{first}">甲</sn><sn id="{second}">乙</sn>完毕'

    assert HyMtResponseParser().parse(response, (first, second)) == {
        first: "甲",
        second: "乙",
    }


def test_parser_repairs_only_missing_closing_id_quote() -> None:
    batch = _batch()
    first, second = (item.wire_id for item in batch.items)
    response = (
        f'<target><sn id="{first}>甲</sn>'
        f'<sn id="{second}>乙</sn></target>'
    )

    assert HyMtResponseParser().parse(response, (first, second)) == {
        first: "甲",
        second: "乙",
    }


@pytest.mark.parametrize(
    ("response_factory", "message"),
    [
        (lambda first, second: f'<target><sn id="{first}">甲</sn></target>', "缺少"),
        (
            lambda first, second: (
                f'<target><sn id="{first}">甲</sn>'
                f'<sn id="{second}">乙</sn><sn id="extra">丙</sn></target>'
            ),
            "未知",
        ),
        (
            lambda first, second: (
                f'<target><sn id="{first}">甲</sn><sn id="{first}">乙</sn>'
                f'<sn id="{second}">丙</sn></target>'
            ),
            "重复",
        ),
    ],
)
def test_parser_rejects_invalid_id_sets(response_factory, message: str) -> None:
    batch = _batch()
    first, second = (item.wire_id for item in batch.items)

    with pytest.raises(TranslationProtocolError, match=message):
        HyMtResponseParser().parse(response_factory(first, second), (first, second))

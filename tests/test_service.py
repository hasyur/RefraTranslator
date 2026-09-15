import asyncio

import pytest

from game_screen_translator.domain import GlossaryEntry, SourceText, TranslationBatch
from game_screen_translator.translation.hy_mt import HyMtPromptBuilder
from game_screen_translator.translation.service import (
    TranslationService,
    is_suspected_untranslated,
)


class ControlledTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, asyncio.Future[str]]] = []

    async def complete(self, prompt: str) -> str:
        future = asyncio.get_running_loop().create_future()
        self.calls.append((prompt, future))
        return await future


class ScriptedTransport:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


async def _wait_for_calls(transport: ControlledTransport, count: int) -> None:
    for _ in range(100):
        if len(transport.calls) >= count:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"只观察到 {len(transport.calls)} 次调用，预期 {count} 次")


@pytest.mark.asyncio
async def test_late_old_revision_is_discarded() -> None:
    transport = ControlledTransport()
    service = TranslationService(transport, prompt_builder=HyMtPromptBuilder())
    old = SourceText("dialogue", "track-1", 1, "古い")
    new = SourceText("dialogue", "track-1", 2, "新しい")

    old_task = asyncio.create_task(service.translate(TranslationBatch((old,))))
    await _wait_for_calls(transport, 1)
    new_task = asyncio.create_task(service.translate(TranslationBatch((new,))))
    await _wait_for_calls(transport, 2)

    transport.calls[1][1].set_result(
        f'<target><sn id="{new.wire_id}">新的</sn></target>'
    )
    new_outcome = await new_task
    transport.calls[0][1].set_result(
        f'<target><sn id="{old.wire_id}">旧的</sn></target>'
    )
    old_outcome = await old_task

    assert [result.translated_text for result in new_outcome.results] == ["新的"]
    assert old_outcome.results == ()
    assert old_outcome.discarded_stale == (old,)


@pytest.mark.parametrize(
    ("source", "translated", "suspected"),
    [
        ("Please wait.", "Please wait.", True),
        ("ここで待って。", "ここで待って。", True),
        ("解消すること。", "消除すること。", True),
        ("12時にはき", "12时にはき", True),
        ("かな", "かな", True),
        ("カナ", "カナ", True),
        ("ｶﾅ", "ｶﾅ", True),
        ("\U0001B001", "\U0001B001", True),
        ("中文", "中文かな", True),
        ("中文", "中文カナ", True),
        ("初音ミクの消失", "初音ミク的消失", True),
        ("日本語では「入る」", "在日语中称为「入る」。", True),
        ("用语", "用语「かな」", True),
        ("Please wait.", "请稍等。", False),
        ("这是中文。", "这是中文。", False),
        ("FPS", "FPS", False),
        ("E2M3", "E2M3", False),
        ("RefraTranslator", "RefraTranslator", False),
        ("https://example.com", "https://example.com", False),
    ],
)
def test_suspected_untranslated_detection_uses_kana_and_latin_exemptions(
    source: str,
    translated: str,
    suspected: bool,
) -> None:
    assert is_suspected_untranslated(source, translated) is suspected


@pytest.mark.asyncio
async def test_only_source_equal_items_receive_one_correction_retry() -> None:
    english = SourceText("dialogue", "english", 1, "Please wait.")
    japanese = SourceText("dialogue", "japanese", 1, "急げ。")
    transport = ScriptedTransport(
        '<target><sn id="1">Please wait.</sn><sn id="2">快点。</sn></target>',
        '<target><sn id="1">请稍等。</sn></target>',
    )
    service = TranslationService(transport, prompt_builder=HyMtPromptBuilder())

    outcome = await service.translate(TranslationBatch((english, japanese)))

    assert [item.translated_text for item in outcome.results] == ["请稍等。", "快点。"]
    assert outcome.suspected_untranslated == ()
    assert len(transport.prompts) == 2
    assert "这是纠正重试" not in transport.prompts[0]
    assert "这是纠正重试" in transport.prompts[1]
    assert "Please wait." in transport.prompts[1]
    assert "急げ。" not in transport.prompts[1]


@pytest.mark.asyncio
async def test_partial_japanese_copy_receives_one_correction_retry() -> None:
    source = SourceText("dialogue", "partial", 1, "解消すること。")
    transport = ScriptedTransport(
        '<target><sn id="1">消除すること。</sn></target>',
        '<target><sn id="1">消除すること。</sn></target>',
    )
    service = TranslationService(transport, prompt_builder=HyMtPromptBuilder())

    outcome = await service.translate(TranslationBatch((source,)))

    assert [item.translated_text for item in outcome.results] == ["消除すること。"]
    assert outcome.suspected_untranslated == (source,)
    assert len(transport.prompts) == 2
    assert "这是纠正重试" in transport.prompts[1]


@pytest.mark.asyncio
async def test_second_source_equal_result_is_returned_but_marked_uncacheable() -> None:
    source = SourceText("dialogue", "line", 1, "ここで待って。")
    response = '<target><sn id="1">ここで待って。</sn></target>'
    transport = ScriptedTransport(response, response)
    service = TranslationService(transport, prompt_builder=HyMtPromptBuilder())

    outcome = await service.translate(TranslationBatch((source,)))

    assert [item.translated_text for item in outcome.results] == ["ここで待って。"]
    assert outcome.suspected_untranslated == (source,)
    assert len(transport.prompts) == 2


@pytest.mark.asyncio
async def test_existing_latin_brand_is_not_suspected() -> None:
    source = SourceText("credits", "brand", 1, "RefraTranslator")
    response = '<target><sn id="1">RefraTranslator</sn></target>'
    transport = ScriptedTransport(response)
    service = TranslationService(transport, prompt_builder=HyMtPromptBuilder())

    outcome = await service.translate(TranslationBatch((source,)))

    assert [item.translated_text for item in outcome.results] == ["RefraTranslator"]
    assert outcome.suspected_untranslated == ()
    assert len(transport.prompts) == 1


@pytest.mark.asyncio
async def test_glossary_does_not_exempt_a_kana_automatic_result() -> None:
    source = SourceText("credits", "name", 1, "初音ミク")
    response = '<target><sn id="1">初音ミク</sn></target>'
    transport = ScriptedTransport(response, response)
    service = TranslationService(transport, prompt_builder=HyMtPromptBuilder())

    outcome = await service.translate(
        TranslationBatch((source,)),
        glossary=(GlossaryEntry("初音ミク", "初音ミク"),),
    )

    assert [item.translated_text for item in outcome.results] == ["初音ミク"]
    assert outcome.suspected_untranslated == (source,)
    assert len(transport.prompts) == 2
    assert "初音ミク 翻译成 初音ミク" in transport.prompts[0]

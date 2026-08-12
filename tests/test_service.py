import asyncio

import pytest

from game_screen_translator.domain import SourceText, TranslationBatch
from game_screen_translator.translation.hy_mt import HyMtPromptBuilder
from game_screen_translator.translation.service import TranslationService


class ControlledTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, asyncio.Future[str]]] = []

    async def complete(self, prompt: str) -> str:
        future = asyncio.get_running_loop().create_future()
        self.calls.append((prompt, future))
        return await future


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

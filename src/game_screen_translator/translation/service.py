from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from game_screen_translator.domain import (
    ContextPair,
    GlossaryEntry,
    RevisionRegistry,
    SourceText,
    TranslationBatch,
    TranslationResult,
)
from game_screen_translator.translation.hy_mt import HyMtPromptBuilder, HyMtResponseParser


class CompletionTransport(Protocol):
    async def complete(self, prompt: str) -> str: ...


@dataclass(frozen=True, slots=True)
class TranslationOutcome:
    results: tuple[TranslationResult, ...]
    discarded_stale: tuple[SourceText, ...]


class TranslationService:
    def __init__(
        self,
        transport: CompletionTransport,
        *,
        prompt_builder: HyMtPromptBuilder,
        response_parser: HyMtResponseParser | None = None,
        revisions: RevisionRegistry | None = None,
    ) -> None:
        self._transport = transport
        self._prompt_builder = prompt_builder
        self._response_parser = response_parser or HyMtResponseParser()
        self.revisions = revisions or RevisionRegistry()

    async def translate(
        self,
        batch: TranslationBatch,
        *,
        glossary: Sequence[GlossaryEntry] = (),
        context: Sequence[ContextPair] = (),
    ) -> TranslationOutcome:
        self.revisions.observe_batch(batch)
        prompt = self._prompt_builder.build(batch, glossary=glossary, context=context)
        raw_response = await self._transport.complete(prompt)
        translated_by_id = self._response_parser.parse(
            raw_response,
            (item.wire_id for item in batch.items),
        )

        results: list[TranslationResult] = []
        discarded: list[SourceText] = []
        for source in batch.items:
            if not self.revisions.is_current(source):
                discarded.append(source)
                continue
            results.append(
                TranslationResult(
                    source=source,
                    translated_text=translated_by_id[source.wire_id],
                )
            )
        return TranslationOutcome(tuple(results), tuple(discarded))

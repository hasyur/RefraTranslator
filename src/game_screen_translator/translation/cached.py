from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from game_screen_translator.domain import (
    ContextPair,
    SourceText,
    TranslationBatch,
    TranslationResult,
)
from game_screen_translator.profiles import GameProfile
from game_screen_translator.translation.cache import CacheEnvironment
from game_screen_translator.translation.service import TranslationOutcome, TranslationService


TranslationOrigin = Literal["manual", "automatic", "model"]


@dataclass(frozen=True, slots=True)
class CachedTranslationOutcome:
    outcome: TranslationOutcome
    origins: tuple[TranslationOrigin, ...]

    def __post_init__(self) -> None:
        if len(self.outcome.results) != len(self.origins):
            raise ValueError("译文来源数量与翻译结果数量不一致")


class CachedTranslationService:
    """Adds an optional per-game glossary and cache around TranslationService."""

    def __init__(
        self,
        service: TranslationService,
        *,
        profile: GameProfile | None,
        source_language: str,
        target_language: str,
        model: str,
        prompt_version: str,
    ) -> None:
        self._service = service
        self._profile = profile
        self._source_language = source_language
        self._target_language = target_language
        self._model = model
        self._prompt_version = prompt_version

    async def translate(
        self,
        batch: TranslationBatch,
        *,
        context: Sequence[ContextPair] = (),
    ) -> CachedTranslationOutcome:
        profile = self._profile
        if profile is None:
            outcome = await self._service.translate(batch, context=context)
            return CachedTranslationOutcome(
                outcome,
                tuple("model" for _ in outcome.results),
            )

        self._service.revisions.observe_batch(batch)
        environment = CacheEnvironment(
            profile_id=profile.profile_id,
            source_language=self._source_language,
            target_language=self._target_language,
            model=self._model,
            prompt_version=self._prompt_version,
            glossary_revision=profile.glossary_revision,
        )
        cached: dict[str, tuple[TranslationResult, TranslationOrigin]] = {}
        missing: list[SourceText] = []
        for source in batch.items:
            hit = profile.cache.lookup(source.text, environment, context)
            if hit is None:
                missing.append(source)
                continue
            cached[source.wire_id] = (
                TranslationResult(source, hit.translated_text),
                hit.origin,
            )

        model_results: dict[str, TranslationResult] = {}
        model_discarded: tuple[SourceText, ...] = ()
        if missing:
            model_outcome = await self._service.translate(
                TranslationBatch(tuple(missing)),
                glossary=profile.glossary,
                context=context,
            )
            model_discarded = model_outcome.discarded_stale
            for result in model_outcome.results:
                profile.cache.store_automatic(
                    result.source.text,
                    result.translated_text,
                    environment,
                    context,
                )
                model_results[result.source.wire_id] = result

        results: list[TranslationResult] = []
        origins: list[TranslationOrigin] = []
        discarded = list(model_discarded)
        discarded_keys = {source.wire_id for source in discarded}
        for source in batch.items:
            if source.wire_id in discarded_keys:
                continue
            if not self._service.revisions.is_current(source):
                discarded.append(source)
                continue
            cached_result = cached.get(source.wire_id)
            if cached_result is not None:
                result, origin = cached_result
                results.append(result)
                origins.append(origin)
                continue
            model_result = model_results.get(source.wire_id)
            if model_result is not None:
                results.append(model_result)
                origins.append("model")

        return CachedTranslationOutcome(
            TranslationOutcome(tuple(results), tuple(discarded)),
            tuple(origins),
        )

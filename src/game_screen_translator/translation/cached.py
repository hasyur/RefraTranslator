from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal, Sequence

from game_screen_translator.domain import (
    ContextPair,
    SourceText,
    TranslationBatch,
    TranslationResult,
)
from game_screen_translator.profiles import GameProfile
from game_screen_translator.translation.cache import (
    CacheEnvironment,
    InFlightCacheClaim,
    TranslationCacheError,
)
from game_screen_translator.translation.service import TranslationOutcome, TranslationService


TranslationOrigin = Literal["manual", "automatic", "inflight", "model"]


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
        model_results: dict[str, TranslationResult] = {}
        owners: list[SourceText] = []
        owner_claims: dict[str, InFlightCacheClaim] = {}
        waiters: list[tuple[SourceText, InFlightCacheClaim]] = []
        try:
            for source in batch.items:
                hit = profile.cache.lookup(source.text, environment, context)
                if hit is not None:
                    cached[source.wire_id] = (
                        TranslationResult(source, hit.translated_text),
                        hit.origin,
                    )
                    continue

                claim = profile.cache.claim_inflight(
                    source.text,
                    environment,
                    context,
                )
                if not claim.is_owner:
                    waiters.append((source, claim))
                    continue

                owner_claims[source.wire_id] = claim
                # Close the lookup/claim race: another owner may have populated
                # SQLite immediately before this request acquired the key.
                hit = profile.cache.lookup(source.text, environment, context)
                if hit is not None:
                    profile.cache.complete_inflight(claim)
                    del owner_claims[source.wire_id]
                    cached[source.wire_id] = (
                        TranslationResult(source, hit.translated_text),
                        hit.origin,
                    )
                    continue
                owners.append(source)

            if owners:
                # Cache ownership is tied to text and context, not to a screen
                # track revision. Preserve parsed results here, then perform the
                # normal freshness check against each original source below.
                model_outcome = await self._service.translate(
                    TranslationBatch(tuple(owners)),
                    glossary=profile.glossary,
                    context=context,
                    discard_stale=False,
                )
                results_by_id = {
                    result.source.wire_id: result for result in model_outcome.results
                }
                missing_result_ids = [
                    source.wire_id
                    for source in owners
                    if source.wire_id not in results_by_id
                ]
                if missing_result_ids:
                    raise TranslationCacheError(
                        "在途翻译完成但缺少结果："
                        + ", ".join(missing_result_ids)
                    )

                for source in owners:
                    result = results_by_id[source.wire_id]
                    profile.cache.store_automatic(
                        source.text,
                        result.translated_text,
                        environment,
                        context,
                    )
                    model_results[source.wire_id] = result
                for source in owners:
                    profile.cache.complete_inflight(owner_claims.pop(source.wire_id))

            if waiters:
                await asyncio.gather(
                    *(
                        asyncio.shield(asyncio.wrap_future(claim.future))
                        for _, claim in waiters
                    )
                )
                for source, _ in waiters:
                    hit = profile.cache.lookup(source.text, environment, context)
                    if hit is None:
                        raise TranslationCacheError(
                            "在途翻译已结束，但缓存中缺少对应结果"
                        )
                    origin: TranslationOrigin = (
                        "manual" if hit.origin == "manual" else "inflight"
                    )
                    cached[source.wire_id] = (
                        TranslationResult(source, hit.translated_text),
                        origin,
                    )
        except BaseException as exc:
            for claim in tuple(owner_claims.values()):
                profile.cache.fail_inflight(claim, exc)
            raise

        results: list[TranslationResult] = []
        origins: list[TranslationOrigin] = []
        discarded: list[SourceText] = []
        for source in batch.items:
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

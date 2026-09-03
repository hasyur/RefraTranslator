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
    CacheHit,
    InFlightCacheClaim,
    TranslationCacheError,
)
from game_screen_translator.translation.service import (
    TranslationOutcome,
    TranslationService,
    is_suspected_untranslated,
)


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
        suspected_model_ids: set[str] = set()
        owners: list[SourceText] = []
        owner_claims: dict[str, InFlightCacheClaim] = {}
        waiters: list[tuple[SourceText, InFlightCacheClaim]] = []

        def lookup_cache(source: SourceText) -> CacheHit | None:
            hit = profile.cache.lookup(source.text, environment, context)
            if (
                hit is not None
                and hit.origin == "automatic"
                and is_suspected_untranslated(
                    source.text,
                    hit.translated_text,
                    glossary=profile.glossary,
                )
            ):
                profile.cache.delete_automatic(source.text, environment, context)
                return None
            return hit

        try:
            for source in batch.items:
                hit = lookup_cache(source)
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
                hit = lookup_cache(source)
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
                suspected_model_ids.update(
                    source.wire_id
                    for source in model_outcome.suspected_untranslated
                )
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
                    if source.wire_id not in suspected_model_ids:
                        profile.cache.store_automatic(
                            source.text,
                            result.translated_text,
                            environment,
                            context,
                        )
                    model_results[source.wire_id] = result
                for source in owners:
                    result = results_by_id[source.wire_id]
                    profile.cache.complete_inflight(
                        owner_claims.pop(source.wire_id),
                        transient_translation=(
                            result.translated_text
                            if source.wire_id in suspected_model_ids
                            else None
                        ),
                    )

            if waiters:
                shared_translations = await asyncio.gather(
                    *(
                        asyncio.shield(asyncio.wrap_future(claim.future))
                        for _, claim in waiters
                    )
                )
                for (source, _), transient_translation in zip(
                    waiters,
                    shared_translations,
                    strict=True,
                ):
                    hit = profile.cache.lookup(source.text, environment, context)
                    if hit is None:
                        if transient_translation is None:
                            raise TranslationCacheError(
                                "在途翻译已结束，但缓存中缺少对应结果"
                            )
                        cached[source.wire_id] = (
                            TranslationResult(source, transient_translation),
                            "inflight",
                        )
                        suspected_model_ids.add(source.wire_id)
                        continue
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
        suspected: list[SourceText] = []
        for source in batch.items:
            if not self._service.revisions.is_current(source):
                discarded.append(source)
                continue
            cached_result = cached.get(source.wire_id)
            if cached_result is not None:
                result, origin = cached_result
                results.append(result)
                origins.append(origin)
                if source.wire_id in suspected_model_ids:
                    suspected.append(source)
                continue
            model_result = model_results.get(source.wire_id)
            if model_result is not None:
                results.append(model_result)
                origins.append("model")
                if source.wire_id in suspected_model_ids:
                    suspected.append(source)

        return CachedTranslationOutcome(
            TranslationOutcome(tuple(results), tuple(discarded), tuple(suspected)),
            tuple(origins),
        )

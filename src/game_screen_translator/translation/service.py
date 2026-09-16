from __future__ import annotations

import re
import unicodedata
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
    suspected_untranslated: tuple[SourceText, ...] = ()


_LATIN_RE = re.compile(r"[A-Za-z]")
_SHORT_ACRONYM_RE = re.compile(r"[A-Z]{1,3}")
_DOTTED_ACRONYM_RE = re.compile(r"(?:[A-Z]\.){2,}[A-Z]?\.?")
_CODE_RE = re.compile(r"(?=.*\d)[A-Za-z0-9_.:/\\-]+")
_CAMEL_CASE_BRAND_RE = re.compile(r"[A-Z][a-z]+(?:[A-Z][A-Za-z0-9]*)+")
_URL_OR_EMAIL_RE = re.compile(r"(?:https?://\S+|www\.\S+|\S+@\S+)", re.IGNORECASE)


def _normalized_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _is_hiragana(character: str) -> bool:
    codepoint = ord(character)
    return 0x3040 <= codepoint <= 0x309F


def _is_katakana(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x30A0 <= codepoint <= 0x30FF
        or 0x31F0 <= codepoint <= 0x31FF
        or 0xFF65 <= codepoint <= 0xFF9F
    )


def _contains_kana(value: str) -> bool:
    return any(
        _is_hiragana(character)
        or _is_katakana(character)
        or 0x1B000 <= ord(character) <= 0x1B16F
        for character in value
    )


def _content_key_without_kana(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(
        character
        for character in normalized
        if character.isalnum()
        and not _is_hiragana(character)
        and not _is_katakana(character)
        and not 0x1B000 <= ord(character) <= 0x1B16F
    )


def _kana_count(value: str) -> int:
    normalized = unicodedata.normalize("NFKC", value)
    return sum(
        1
        for character in normalized
        if _is_hiragana(character)
        or _is_katakana(character)
        or 0x1B000 <= ord(character) <= 0x1B16F
    )


def _content_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(character for character in normalized if character.isalnum())


def _is_obvious_latin_exemption(value: str) -> bool:
    compact = value.strip()
    return bool(
        _SHORT_ACRONYM_RE.fullmatch(compact)
        or _DOTTED_ACRONYM_RE.fullmatch(compact)
        or _CODE_RE.fullmatch(compact)
        or _CAMEL_CASE_BRAND_RE.fullmatch(compact)
        or _URL_OR_EMAIL_RE.fullmatch(compact)
    )


def is_suspected_untranslated(
    source_text: str,
    translated_text: str,
) -> bool:
    """Return whether an automatic result should be corrected and withheld."""

    source = _normalized_text(source_text)
    translated = _normalized_text(translated_text)
    if not source or not translated:
        return False
    if _contains_kana(translated):
        return True
    if _contains_kana(source):
        source_without_kana = _content_key_without_kana(source)
        if (
            source_without_kana
            and _kana_count(source) > len(source_without_kana)
            and source_without_kana == _content_key(translated)
        ):
            return True
    if source == translated:
        return bool(_LATIN_RE.search(source)) and not _is_obvious_latin_exemption(source)
    return False


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
        discard_stale: bool = True,
    ) -> TranslationOutcome:
        self.revisions.observe_batch(batch)
        prompt = self._prompt_builder.build(batch, glossary=glossary, context=context)
        raw_response = await self._transport.complete(prompt)
        translated_by_id = self._response_parser.parse(
            raw_response,
            (item.wire_id for item in batch.items),
        )

        retry_sources: tuple[SourceText, ...] = ()
        for retry_count in (1, 2):
            retry_sources = tuple(
                source
                for source in batch.items
                if is_suspected_untranslated(
                    source.text,
                    translated_by_id[source.wire_id],
                )
            )
            if not retry_sources:
                break
            retry_batch = TranslationBatch(retry_sources)
            retry_prompt = self._prompt_builder.build(
                retry_batch,
                retry_count=retry_count,
            )
            retry_response = await self._transport.complete(retry_prompt)
            translated_by_id.update(
                self._response_parser.parse(
                    retry_response,
                    (item.wire_id for item in retry_sources),
                )
            )

        suspected_ids = {
            source.wire_id
            for source in batch.items
            if is_suspected_untranslated(
                source.text,
                translated_by_id[source.wire_id],
            )
        }

        results: list[TranslationResult] = []
        discarded: list[SourceText] = []
        suspected: list[SourceText] = []
        for source in batch.items:
            if discard_stale and not self.revisions.is_current(source):
                discarded.append(source)
                continue
            results.append(
                TranslationResult(
                    source=source,
                    translated_text=translated_by_id[source.wire_id],
                )
            )
            if source.wire_id in suspected_ids:
                suspected.append(source)
        return TranslationOutcome(tuple(results), tuple(discarded), tuple(suspected))

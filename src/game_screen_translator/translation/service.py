from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
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
_QUOTED_TEXT_RE = re.compile(
    r"(?:「[^」]*」|『[^』]*』|\u201c[^\u201d]*\u201d|\u2018[^\u2019]*\u2019|\"[^\"]*\")"
)

# These thresholds deliberately require several independent signs.  A single
# retained particle (or a short name) is not enough to reject a translation.
_MIN_RETAINED_HIRAGANA = 2
_MIN_RETAINED_HIRAGANA_RATIO = 0.35
_MIN_TRANSLATED_HIRAGANA_RATIO = 0.20
_MIN_OVERALL_SIMILARITY = 0.65
_MIN_JAPANESE_BODY_HIRAGANA_RATIO = 0.45

_JAPANESE_FUNCTION_SUFFIXES = (
    "では",
    "です",
    "ます",
    "する",
    "した",
    "して",
    "され",
    "れる",
    "られ",
    "ない",
    "たい",
    "って",
    "こと",
    "もの",
    "さん",
    "くん",
    "ちゃん",
)
_COMMON_KATAKANA_WORDS = {
    "ゲーム",
    "テスト",
    "メニュー",
    "タイトル",
    "スタート",
    "ストップ",
}


def _normalized_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _comparison_text(value: str) -> str:
    """Normalize away layout punctuation before comparing two model strings."""

    normalized = _normalized_text(value)
    return "".join(
        character
        for character in normalized
        if not character.isspace()
        and not unicodedata.category(character).startswith("P")
    )


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


def _is_short_japanese_name(value: str) -> bool:
    """Conservatively leave short name-shaped source text alone.

    This is intentionally narrow: sentence-like text with a common Japanese
    grammatical ending remains subject to the quality gate.  It only covers
    the ambiguous, short label/name case where deterministic text signals
    cannot tell a preserved proper name from an untranslated sentence.
    """

    compact = "".join(
        character
        for character in value
        if not character.isspace()
        and not unicodedata.category(character).startswith(("P", "S"))
    )
    if (
        not 2 <= len(compact) <= 8
        or any(character.isdigit() for character in compact)
    ):
        return False
    hiragana = sum(_is_hiragana(character) for character in compact)
    katakana = sum(_is_katakana(character) for character in compact)
    han = sum(
        "CJK UNIFIED IDEOGRAPH" in unicodedata.name(character, "")
        for character in compact
    )
    if not (hiragana or katakana):
        return False
    if katakana and not hiragana:
        if han:
            return True
        return len(compact) <= 4 and compact not in _COMMON_KATAKANA_WORDS
    if han < 2 or hiragana < 2:
        return False

    hiragana_runs = re.findall(r"[\u3040-\u309F]+", compact)
    if len(hiragana_runs) != 1 or not compact.endswith(hiragana_runs[0]):
        return False
    return not any(compact.endswith(suffix) for suffix in _JAPANESE_FUNCTION_SUFFIXES)


def _protected_mask(value: str, fragments: Sequence[str]) -> tuple[bool, ...]:
    """Mark explicitly preserved spans used by the kana-ratio check."""

    mask = [False] * len(value)
    normalized_fragments = tuple(
        fragment
        for fragment in (_normalized_text(item) for item in fragments)
        if fragment
    )
    for fragment in normalized_fragments:
        start = value.find(fragment)
        while start >= 0:
            end = start + len(fragment)
            mask[start:end] = [True] * (end - start)
            start = value.find(fragment, end)
    return tuple(mask)


def _quoted_spans(value: str) -> tuple[tuple[str, str], ...]:
    return tuple(
        (match.group(0), _comparison_text(match.group(0)[1:-1]))
        for match in _QUOTED_TEXT_RE.finditer(value)
        if len(match.group(0)) >= 2
    )


def _matching_quoted_fragments(source: str, translated: str) -> tuple[str, ...]:
    source_contents = {
        content for _, content in _quoted_spans(source) if content
    }
    return tuple(
        whole
        for whole, content in _quoted_spans(translated)
        if content and content in source_contents
    )


def _matching_glossary_targets(
    source: str,
    translated: str,
    glossary: Sequence[GlossaryEntry],
) -> tuple[str, ...]:
    fragments: list[str] = []
    for entry in glossary:
        source_fragment = _normalized_text(entry.source)
        target_fragment = _normalized_text(entry.target)
        if (
            source_fragment
            and source_fragment in source
            and target_fragment
            and target_fragment in translated
        ):
            fragments.append(target_fragment)
    return tuple(fragments)


def _unprotected_hiragana_ratio(value: str, mask: Sequence[bool]) -> float:
    letter_count = 0
    hiragana_count = 0
    for index, character in enumerate(value):
        if mask[index]:
            continue
        category = unicodedata.category(character)
        if not (category.startswith("L") or category.startswith("N")):
            continue
        letter_count += 1
        hiragana_count += _is_hiragana(character)
    return hiragana_count / letter_count if letter_count else 0.0


def _retained_hiragana(
    source: str,
    translated: str,
    source_mask: Sequence[bool],
    translated_mask: Sequence[bool],
) -> tuple[int, int]:
    source_hiragana = [
        character
        for index, character in enumerate(source)
        if not source_mask[index] and _is_hiragana(character)
    ]
    translated_hiragana = Counter(
        character
        for index, character in enumerate(translated)
        if not translated_mask[index] and _is_hiragana(character)
    )
    retained = sum(
        min(count, translated_hiragana[character])
        for character, count in Counter(source_hiragana).items()
    )
    return retained, len(source_hiragana)


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
    *,
    glossary: Sequence[GlossaryEntry] = (),
) -> bool:
    """Return whether a model result should be corrected and not cached.

    The check is intentionally deterministic and conservative.  Exact source
    copies remain the first, strongest signal; for Japanese text, a high
    source/translation similarity together with repeated source hiragana and
    a meaningful amount of unprotected hiragana in the result catches
    rewritten or partially translated copies without requiring another model
    to judge the output.
    """

    source = _normalized_text(source_text)
    translated = _normalized_text(translated_text)
    if not source or not translated:
        return False
    if any(
        _normalized_text(entry.source) == source
        and _normalized_text(entry.target) == translated
        for entry in glossary
    ):
        return False
    if source == translated:
        if _contains_kana(source):
            return not _is_short_japanese_name(source)
        return bool(_LATIN_RE.search(source)) and not _is_obvious_latin_exemption(source)

    source_hiragana_mask = _protected_mask(
        source,
        tuple(entry.source for entry in glossary)
        + tuple(whole for whole, _ in _quoted_spans(source)),
    )
    translated_hiragana_mask = _protected_mask(
        translated,
        _matching_glossary_targets(source, translated, glossary)
        + _matching_quoted_fragments(source, translated),
    )
    retained_count, source_count = _retained_hiragana(
        source,
        translated,
        source_hiragana_mask,
        translated_hiragana_mask,
    )
    if source_count < _MIN_RETAINED_HIRAGANA:
        return False

    similarity = SequenceMatcher(
        None,
        _comparison_text(source),
        _comparison_text(translated),
        autojunk=False,
    ).ratio()
    retained_ratio = retained_count / source_count
    translated_hiragana_ratio = _unprotected_hiragana_ratio(
        translated,
        translated_hiragana_mask,
    )

    shared_hiragana_copy = (
        retained_count >= _MIN_RETAINED_HIRAGANA
        and retained_ratio >= _MIN_RETAINED_HIRAGANA_RATIO
        and similarity >= _MIN_OVERALL_SIMILARITY
        and translated_hiragana_ratio >= _MIN_TRANSLATED_HIRAGANA_RATIO
    )
    japanese_body_copy = (
        similarity >= _MIN_OVERALL_SIMILARITY
        and translated_hiragana_ratio >= _MIN_JAPANESE_BODY_HIRAGANA_RATIO
    )
    return shared_hiragana_copy or japanese_body_copy


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

        retry_sources = tuple(
            source
            for source in batch.items
            if is_suspected_untranslated(
                source.text,
                translated_by_id[source.wire_id],
                glossary=glossary,
            )
        )
        if retry_sources:
            retry_batch = TranslationBatch(retry_sources)
            retry_prompt = self._prompt_builder.build(
                retry_batch,
                glossary=glossary,
                context=context,
                correction=True,
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
            for source in retry_sources
            if is_suspected_untranslated(
                source.text,
                translated_by_id[source.wire_id],
                glossary=glossary,
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

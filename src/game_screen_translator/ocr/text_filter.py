from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from game_screen_translator.ocr.types import OcrText


_JAPANESE_LANGUAGES = {"ja", "japan", "japanese"}
_ENGLISH_LANGUAGES = {"en", "english"}
_KOREAN_LANGUAGES = {"ko", "korean"}
_CHINESE_LANGUAGES = {"ch", "chinese", "zh", "zh-cn", "zh-tw"}
_UI_CODES = {
    "AP",
    "CPU",
    "EXP",
    "FPS",
    "GB",
    "GPU",
    "HP",
    "KB",
    "LV",
    "LVL",
    "MB",
    "MP",
    "MS",
    "RAM",
    "SP",
    "TB",
    "VRAM",
    "XP",
}
_KEY_NAMES = {
    "ALT",
    "BACKSPACE",
    "CTRL",
    "DEL",
    "ENTER",
    "ESC",
    "LB",
    "LMB",
    "LT",
    "RB",
    "RMB",
    "RT",
    "SHIFT",
    "SPACE",
    "TAB",
}
_NUMBER_ONLY_RE = re.compile(r"^[\d\s.,:/%+\-–—]+$")
_KEY_PROMPT_RE = re.compile(r"^[A-Z]\d{0,2}$")
_TOKEN_RE = re.compile(r"[A-Za-z]+|\d+")


@dataclass(frozen=True, slots=True)
class RejectedOcrText:
    observation: OcrText
    reason: str


@dataclass(frozen=True, slots=True)
class OcrFilterOutcome:
    accepted: tuple[OcrText, ...]
    rejected: tuple[RejectedOcrText, ...]

    @property
    def reason_counts(self) -> dict[str, int]:
        return dict(Counter(item.reason for item in self.rejected))


class OcrTextFilter:
    """Keep likely source-language text before tracking or LLM submission."""

    def __init__(
        self,
        source_language: str,
        *,
        enabled: bool = True,
        translate_latin: bool = True,
        translate_han_only: bool = False,
    ) -> None:
        self.source_language = source_language.strip().lower()
        self.enabled = enabled
        self.translate_latin = translate_latin
        self.translate_han_only = translate_han_only

    def apply(self, observations: Iterable[OcrText]) -> OcrFilterOutcome:
        accepted: list[OcrText] = []
        rejected: list[RejectedOcrText] = []
        for observation in observations:
            reason = None if not self.enabled else self._rejection_reason(observation.text)
            if reason is None:
                accepted.append(observation)
            else:
                rejected.append(RejectedOcrText(observation, reason))
        return OcrFilterOutcome(tuple(accepted), tuple(rejected))

    def _rejection_reason(self, raw_text: str) -> str | None:
        text = unicodedata.normalize("NFKC", raw_text).strip()
        if not text:
            return "空文本"

        letters = [character for character in text if unicodedata.category(character).startswith("L")]
        numbers = [character for character in text if unicodedata.category(character).startswith("N")]
        if not letters:
            return "纯数字" if numbers or _NUMBER_ONLY_RE.fullmatch(text) else "图标/符号"
        if _NUMBER_ONLY_RE.fullmatch(text):
            return "纯数字"

        has_kana = any(_is_kana(character) for character in letters)
        has_han = any(_is_han(character) for character in letters)
        has_hangul = any(_is_hangul(character) for character in letters)
        has_latin = any(_is_latin(character) for character in letters)

        if self.source_language in _JAPANESE_LANGUAGES:
            if has_kana:
                return None
            if has_han:
                return None if self.translate_han_only else "纯汉字/中文"
            if has_latin:
                return self._latin_rejection_reason(text)
            return "非日文文字"

        if self.source_language in _ENGLISH_LANGUAGES:
            if not has_latin or has_kana or has_han or has_hangul:
                return "非英文文字"
            return self._latin_rejection_reason(text)

        if self.source_language in _KOREAN_LANGUAGES:
            if has_hangul:
                return None
            if has_latin:
                return self._latin_rejection_reason(text)
            return "非韩文文字"

        if self.source_language in _CHINESE_LANGUAGES:
            if has_han:
                return None
            if has_latin:
                return self._latin_rejection_reason(text)
            return "非中文文字"

        if has_latin:
            latin_reason = self._latin_rejection_reason(text)
            if latin_reason is None:
                return None
        if has_kana or has_han or has_hangul:
            return None
        return "非源语言文字"

    def _latin_rejection_reason(self, text: str) -> str | None:
        if not self.translate_latin:
            return "英文已关闭"
        compact = "".join(_TOKEN_RE.findall(text))
        if (
            len(compact) <= 1
            or _KEY_PROMPT_RE.fullmatch(compact)
            or compact.upper() in _KEY_NAMES
        ):
            return "按键/短标签"
        tokens = _TOKEN_RE.findall(text)
        if tokens and tokens[0].upper() in _UI_CODES and all(
            token.isdigit() or token.upper() in _UI_CODES for token in tokens
        ):
            return "状态缩写"
        return None


def _is_kana(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3040 <= codepoint <= 0x30FF
        or 0x31F0 <= codepoint <= 0x31FF
        or 0xFF65 <= codepoint <= 0xFF9F
        or 0x1B000 <= codepoint <= 0x1B16F
    )


def _is_han(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x323AF
    )


def _is_hangul(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x1100 <= codepoint <= 0x11FF
        or 0x3130 <= codepoint <= 0x318F
        or 0xAC00 <= codepoint <= 0xD7AF
    )


def _is_latin(character: str) -> bool:
    return "LATIN" in unicodedata.name(character, "")

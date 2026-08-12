from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from html import escape
from typing import Iterable, Sequence

from game_screen_translator.domain import ContextPair, GlossaryEntry, TranslationBatch


PROMPT_VERSION = "hy-mt1.5-batch-v1"
_CODE_FENCE_RE = re.compile(r"^\s*```(?:xml)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)
_TARGET_RE = re.compile(r"<target(?:\s[^>]*)?>.*?</target\s*>", re.DOTALL | re.IGNORECASE)
_SN_RE = re.compile(r"<sn\b[^>]*>.*?</sn\s*>", re.DOTALL | re.IGNORECASE)
_MISSING_ID_QUOTE_RE = re.compile(
    r'(<sn\b[^>]*\bid\s*=\s*")([A-Za-z0-9_.:-]+)(\s*>)',
    re.IGNORECASE,
)


class TranslationProtocolError(ValueError):
    """Raised when an LLM response violates the batch translation contract."""


def _one_line(value: str) -> str:
    return " ".join(value.split())


@dataclass(frozen=True, slots=True)
class HyMtPromptBuilder:
    target_language: str = "简体中文"
    prompt_version: str = PROMPT_VERSION

    def build(
        self,
        batch: TranslationBatch,
        *,
        glossary: Sequence[GlossaryEntry] = (),
        context: Sequence[ContextPair] = (),
    ) -> str:
        sections: list[str] = []

        if glossary:
            terminology = ["参考下面的固定翻译，必须优先使用这些术语："]
            terminology.extend(
                f"{_one_line(entry.source)} 翻译成 {_one_line(entry.target)}"
                for entry in glossary
            )
            sections.append("\n".join(terminology))

        if context:
            context_lines = ["参考最近的翻译对照来保持称呼、语气和上下文一致："]
            context_lines.extend(
                f"原文：{_one_line(pair.source)}\n译文：{_one_line(pair.target)}"
                for pair in context
            )
            sections.append("\n".join(context_lines))

        source_lines = ["<source>"]
        source_lines.extend(
            f'  <sn id="{item.wire_id}">{escape(item.text, quote=True)}</sn>'
            for item in batch.items
        )
        source_lines.append("</source>")

        instruction = (
            f"参考上面的信息，把下面文本翻译成{self.target_language}。"
            "保留每个 <sn> 标签及其 id 属性和原有顺序，只翻译标签内的文字；"
            "逐字复制 id，并保留 id 值两侧的双引号；"
            "用一个 <target> 根标签包住全部结果。"
            "只输出 XML 结果，不要翻译参考信息，不要添加解释。"
        )
        sections.extend((instruction, "\n".join(source_lines)))
        return "\n\n".join(sections)


class HyMtResponseParser:
    def parse(self, response_text: str, expected_ids: Iterable[str]) -> dict[str, str]:
        expected = tuple(expected_ids)
        if not expected:
            raise ValueError("expected_ids 不能为空")
        if len(set(expected)) != len(expected):
            raise ValueError("expected_ids 不能重复")

        xml_text = self._extract_xml(response_text)
        # HY-MT occasionally emits `<sn id="r1>` while keeping the exact ID.
        # Repair only that narrow syntax error; the exact ID-set validation
        # below still rejects changed, missing, duplicated or invented IDs.
        xml_text = _MISSING_ID_QUOTE_RE.sub(r'\1\2"\3', xml_text)
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as exc:
            raise TranslationProtocolError(f"模型返回了无效 XML：{exc}") from exc

        parsed: dict[str, str] = {}
        for element in root.iter():
            if self._local_name(element.tag).lower() != "sn":
                continue
            wire_id = (element.attrib.get("id") or "").strip()
            if not wire_id:
                raise TranslationProtocolError("返回的 <sn> 缺少 id 属性")
            if wire_id in parsed:
                raise TranslationProtocolError(f"返回了重复 id：{wire_id}")
            translated = "".join(element.itertext()).strip()
            if not translated:
                raise TranslationProtocolError(f"id={wire_id} 的译文为空")
            parsed[wire_id] = translated

        expected_set = set(expected)
        parsed_set = set(parsed)
        missing = sorted(expected_set - parsed_set)
        unexpected = sorted(parsed_set - expected_set)
        if missing or unexpected:
            details: list[str] = []
            if missing:
                details.append(f"缺少 id={missing}")
            if unexpected:
                details.append(f"包含未知 id={unexpected}")
            raise TranslationProtocolError("；".join(details))

        return {wire_id: parsed[wire_id] for wire_id in expected}

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @staticmethod
    def _extract_xml(response_text: str) -> str:
        candidate = response_text.strip()
        if not candidate:
            raise TranslationProtocolError("模型返回为空")

        fenced = _CODE_FENCE_RE.match(candidate)
        if fenced:
            candidate = fenced.group(1).strip()

        target = _TARGET_RE.search(candidate)
        if target:
            return target.group(0)

        fragments = _SN_RE.findall(candidate)
        if fragments:
            return "<target>" + "".join(fragments) + "</target>"

        raise TranslationProtocolError("模型返回中没有 <target> 或 <sn> 标签")

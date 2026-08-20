from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from html import escape
from typing import Iterable, Sequence

from game_screen_translator.domain import ContextPair, GlossaryEntry, TranslationBatch


PROMPT_VERSION = "hy-mt1.5-batch-v2-short-ids"
_CODE_FENCE_RE = re.compile(r"^\s*```(?:xml)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)
_TARGET_RE = re.compile(r"<target(?:\s[^>]*)?>.*?</target\s*>", re.DOTALL | re.IGNORECASE)
_SN_RE = re.compile(r"<sn\b[^>]*>.*?</sn\s*>", re.DOTALL | re.IGNORECASE)
_MISSING_ID_QUOTE_RE = re.compile(
    r'(<sn\b[^>]*\bid\s*=\s*")([A-Za-z0-9_.:-]+)(\s*>)',
    re.IGNORECASE,
)
_UNQUOTED_ID_RE = re.compile(
    r'(<sn\b[^>]*\bid\s*=\s*)([A-Za-z0-9_.:-]+)(?=\s|>)',
    re.IGNORECASE,
)
_BARE_AMPERSAND_RE = re.compile(
    r"&(?!amp;|lt;|gt;|apos;|quot;|#\d+;|#x[0-9A-Fa-f]+;)"
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
            f'  <sn id="{request_id}">{escape(item.text, quote=True)}</sn>'
            for request_id, item in enumerate(batch.items, start=1)
        )
        source_lines.append("</source>")

        instruction = (
            f"参考上面的信息，把下面文本翻译成{self.target_language}。"
            "保留每个 <sn> 标签及其 id 属性和原有顺序，只翻译标签内的文字；"
            "id 是从 1 开始的连续短编号，请原样保留数字和两侧的双引号；"
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

        try:
            xml_text = self._extract_xml(response_text)
        except TranslationProtocolError:
            if len(expected) == 1:
                translated = self._plain_single_translation(response_text)
                if translated:
                    return {expected[0]: translated}
            raise
        xml_text = self._repair_common_xml_errors(xml_text)
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as exc:
            # A malformed <target> wrapper should not discard otherwise complete
            # <sn> entries. Re-wrap only complete fragments, then validate their
            # exact count before accepting them positionally.
            fragments = _SN_RE.findall(xml_text)
            if not fragments:
                raise TranslationProtocolError(f"模型返回了无效 XML：{exc}") from exc
            fragment_xml = "<target>" + "".join(fragments) + "</target>"
            try:
                root = ElementTree.fromstring(fragment_xml)
            except ElementTree.ParseError:
                raise TranslationProtocolError(f"模型返回了无效 XML：{exc}") from exc

        sn_elements = tuple(
            element
            for element in root.iter()
            if self._local_name(element.tag).lower() == "sn"
        )
        if not sn_elements and len(expected) == 1:
            translated = "".join(root.itertext()).strip()
            if translated:
                return {expected[0]: translated}

        if len(sn_elements) != len(expected):
            raise TranslationProtocolError(
                f"返回的 <sn> 数量为 {len(sn_elements)}，预期为 {len(expected)}"
            )

        entries: list[tuple[str, str]] = []
        for position, element in enumerate(sn_elements, start=1):
            response_id = (element.attrib.get("id") or "").strip()
            translated = "".join(element.itertext()).strip()
            if not translated:
                raise TranslationProtocolError(f"第 {position} 个 <sn> 的译文为空")
            entries.append((response_id, translated))

        request_ids = tuple(str(index) for index in range(1, len(expected) + 1))
        response_ids = tuple(response_id for response_id, _ in entries)
        if len(set(response_ids)) == len(response_ids) and set(response_ids) == set(
            request_ids
        ):
            translated_by_request_id = dict(entries)
            return {
                wire_id: translated_by_request_id[request_id]
                for wire_id, request_id in zip(expected, request_ids, strict=True)
            }

        # IDs are redundant routing hints. If the model corrupts them but still
        # returns the exact number of non-empty entries, preserve the prompt's
        # explicit ordering contract instead of issuing another LLM request.
        return {
            wire_id: translated
            for wire_id, (_, translated) in zip(expected, entries, strict=True)
        }

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @staticmethod
    def _repair_common_xml_errors(xml_text: str) -> str:
        # HY-MT can omit one or both quotes around a short id. It can also emit
        # a literal ampersand in translated text, which is invalid XML.
        repaired = _MISSING_ID_QUOTE_RE.sub(r'\1\2"\3', xml_text)
        repaired = _UNQUOTED_ID_RE.sub(r'\1"\2"', repaired)
        return _BARE_AMPERSAND_RE.sub("&amp;", repaired)

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

    @staticmethod
    def _plain_single_translation(response_text: str) -> str:
        candidate = response_text.strip()
        fenced = _CODE_FENCE_RE.match(candidate)
        if fenced:
            candidate = fenced.group(1).strip()
        return candidate

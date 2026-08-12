from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceText:
    zone_id: str
    track_id: str
    revision: int
    text: str

    def __post_init__(self) -> None:
        if not self.zone_id.strip():
            raise ValueError("zone_id 不能为空")
        if not self.track_id.strip():
            raise ValueError("track_id 不能为空")
        if self.revision < 0:
            raise ValueError("revision 不能为负数")
        if not self.text.strip():
            raise ValueError("待翻译文本不能为空")

    @property
    def track_key(self) -> tuple[str, str]:
        return self.zone_id, self.track_id

    @property
    def wire_id(self) -> str:
        identity = f"{self.zone_id}\0{self.track_id}\0{self.revision}".encode("utf-8")
        digest = hashlib.blake2s(identity, digest_size=8).hexdigest()
        return f"sn_{digest}_r{self.revision}"


@dataclass(frozen=True, slots=True)
class TranslationBatch:
    items: tuple[SourceText, ...]

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("翻译批次不能为空")
        wire_ids = [item.wire_id for item in self.items]
        if len(set(wire_ids)) != len(wire_ids):
            raise ValueError("翻译批次中存在重复的 track/revision")


@dataclass(frozen=True, slots=True)
class TranslationResult:
    source: SourceText
    translated_text: str


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    source: str
    target: str

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.target.strip():
            raise ValueError("术语原文和译文均不能为空")


@dataclass(frozen=True, slots=True)
class ContextPair:
    source: str
    target: str

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.target.strip():
            raise ValueError("上下文原文和译文均不能为空")


class RevisionRegistry:
    """Tracks the latest OCR revision and rejects late translation responses."""

    def __init__(self) -> None:
        self._latest: dict[tuple[str, str], int] = {}
        self._lock = threading.RLock()

    def observe(self, source: SourceText) -> bool:
        with self._lock:
            current = self._latest.get(source.track_key)
            if current is None or source.revision > current:
                self._latest[source.track_key] = source.revision
                return True
            return source.revision == current

    def observe_batch(self, batch: TranslationBatch) -> None:
        for source in batch.items:
            self.observe(source)

    def is_current(self, source: SourceText) -> bool:
        with self._lock:
            return self._latest.get(source.track_key) == source.revision

    def latest_revision(self, zone_id: str, track_id: str) -> int | None:
        with self._lock:
            return self._latest.get((zone_id, track_id))

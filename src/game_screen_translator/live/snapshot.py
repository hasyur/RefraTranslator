"""Bounded, replace-in-place snapshots of the last successful live run."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


SNAPSHOT_VERSION = 1
SNAPSHOT_FILENAME = "last_run_snapshot.json"
MAX_SNAPSHOT_ENTRIES = 128
MAX_CACHE_RANKING = 5
MAX_TEXT_LENGTH = 4_000


class SnapshotError(ValueError):
    """Raised when a last-run snapshot does not satisfy its bounded schema."""


Bounds = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class SnapshotEntry:
    track_id: str
    revision: int
    source_text: str
    translated_text: str
    confidence: float
    bounds: Bounds

    def __post_init__(self) -> None:
        if type(self.track_id) is not str or not self.track_id.strip():
            raise SnapshotError("快照 track_id 不能为空")
        if type(self.revision) is not int or self.revision < 0:
            raise SnapshotError("快照 revision 不能为负数")
        for label, value in (
            ("source_text", self.source_text),
            ("translated_text", self.translated_text),
        ):
            if not isinstance(value, str) or not value.strip():
                raise SnapshotError(f"快照 {label} 不能为空")
            if len(value) > MAX_TEXT_LENGTH:
                raise SnapshotError(f"快照 {label} 超过长度上限")
        if (
            type(self.confidence) not in {int, float}
            or isinstance(self.confidence, bool)
            or not math.isfinite(self.confidence)
            or not 0 <= self.confidence <= 1
        ):
            raise SnapshotError("快照 confidence 必须在 0 到 1 之间")
        if (
            type(self.bounds) is not tuple
            or len(self.bounds) != 4
            or any(type(value) is not int for value in self.bounds)
            or any(value < 0 for value in self.bounds)
            or self.bounds[2] <= self.bounds[0]
            or self.bounds[3] <= self.bounds[1]
        ):
            raise SnapshotError("快照 bounds 必须是有效的非负矩形")


@dataclass(frozen=True, slots=True)
class CacheHit:
    source_text: str
    hits: int

    def __post_init__(self) -> None:
        if type(self.source_text) is not str or not self.source_text.strip():
            raise SnapshotError("缓存排行原文不能为空")
        if len(self.source_text) > MAX_TEXT_LENGTH:
            raise SnapshotError("缓存排行原文超过长度上限")
        if type(self.hits) is not int or self.hits < 1:
            raise SnapshotError("缓存排行次数必须是正整数")


@dataclass(frozen=True, slots=True)
class LastRunSnapshot:
    entries: tuple[SnapshotEntry, ...]
    cache_hits: tuple[CacheHit, ...]
    ocr_peak_seconds: float | None
    llm_peak_seconds: float | None
    canvas_size: tuple[int, int] | None
    created_at: str
    version: int = SNAPSHOT_VERSION

    def __post_init__(self) -> None:
        if self.version != SNAPSHOT_VERSION:
            raise SnapshotError(f"不支持的快照版本：{self.version!r}")
        if not self.entries or len(self.entries) > MAX_SNAPSHOT_ENTRIES:
            raise SnapshotError("快照 OCR 条目数量超出范围")
        if len(self.cache_hits) > MAX_CACHE_RANKING:
            raise SnapshotError("快照缓存排行数量超出范围")
        for label, value in (
            ("ocr_peak_seconds", self.ocr_peak_seconds),
            ("llm_peak_seconds", self.llm_peak_seconds),
        ):
            if value is not None and (
                type(value) not in {int, float}
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0
            ):
                raise SnapshotError(f"快照 {label} 必须是非负有限数")
        if type(self.created_at) is not str or not self.created_at.strip():
            raise SnapshotError("快照 created_at 不能为空")
        if self.canvas_size is not None and (
            type(self.canvas_size) is not tuple
            or len(self.canvas_size) != 2
            or any(type(value) is not int for value in self.canvas_size)
            or any(value <= 0 for value in self.canvas_size)
        ):
            raise SnapshotError("快照 canvas_size 必须是正整数宽高")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "entries": [
                {
                    "track_id": entry.track_id,
                    "revision": entry.revision,
                    "source_text": entry.source_text,
                    "translated_text": entry.translated_text,
                    "confidence": entry.confidence,
                    "bounds": list(entry.bounds),
                }
                for entry in self.entries
            ],
            "cache_hits": [
                {"source_text": item.source_text, "hits": item.hits}
                for item in self.cache_hits
            ],
            "peaks": {
                "ocr_seconds": self.ocr_peak_seconds,
                "llm_seconds": self.llm_peak_seconds,
            },
            "canvas_size": (
                list(self.canvas_size) if self.canvas_size is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LastRunSnapshot":
        if set(payload) != {
            "version", "created_at", "entries", "cache_hits", "peaks", "canvas_size"
        }:
            raise SnapshotError("快照包含未知或缺失字段")
        version = payload["version"]
        created_at = payload["created_at"]
        raw_entries = payload["entries"]
        raw_cache_hits = payload["cache_hits"]
        peaks = payload["peaks"]
        canvas_size = payload["canvas_size"]
        if type(version) is not int or not isinstance(raw_entries, list):
            raise SnapshotError("快照根字段类型无效")
        if not isinstance(raw_cache_hits, list) or not isinstance(peaks, Mapping):
            raise SnapshotError("快照排行或峰值字段类型无效")
        if len(raw_entries) > MAX_SNAPSHOT_ENTRIES:
            raise SnapshotError("快照 OCR 条目数量超出范围")
        if len(raw_cache_hits) > MAX_CACHE_RANKING:
            raise SnapshotError("快照缓存排行数量超出范围")
        if set(peaks) != {"ocr_seconds", "llm_seconds"}:
            raise SnapshotError("快照峰值包含未知字段")
        if canvas_size is not None:
            if not isinstance(canvas_size, list):
                raise SnapshotError("快照 canvas_size 类型无效")
            canvas_size = tuple(canvas_size)
        entries = tuple(_entry_from_dict(item) for item in raw_entries)
        cache_hits = tuple(_cache_hit_from_dict(item) for item in raw_cache_hits)
        return cls(
            entries=entries,
            cache_hits=cache_hits,
            ocr_peak_seconds=_optional_float(peaks["ocr_seconds"], "ocr_seconds"),
            llm_peak_seconds=_optional_float(peaks["llm_seconds"], "llm_seconds"),
            canvas_size=canvas_size,
            created_at=created_at,
            version=version,
        )


def snapshot_path(profile_directory: Path) -> Path:
    """Return the only snapshot path owned by one Profile directory."""

    directory = profile_directory.resolve()
    return directory / SNAPSHOT_FILENAME


def save_snapshot(profile_directory: Path, snapshot: LastRunSnapshot) -> Path:
    """Atomically replace the Profile's one last-run snapshot."""

    path = snapshot_path(profile_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        snapshot.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return path


def load_snapshot(profile_directory: Path) -> LastRunSnapshot | None:
    """Load a valid snapshot; malformed or missing data is unavailable."""

    path = snapshot_path(profile_directory)
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, Mapping):
            raise SnapshotError("快照根节点必须是对象")
        return LastRunSnapshot.from_dict(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, SnapshotError, TypeError):
        return None


def new_snapshot(
    entries: Sequence[SnapshotEntry],
    cache_hits: Sequence[CacheHit],
    *,
    ocr_peak_seconds: float | None,
    llm_peak_seconds: float | None,
    canvas_size: tuple[int, int] | None = None,
) -> LastRunSnapshot:
    """Build a bounded snapshot with a UTC completion timestamp."""

    return LastRunSnapshot(
        entries=tuple(entries),
        cache_hits=tuple(cache_hits),
        ocr_peak_seconds=ocr_peak_seconds,
        llm_peak_seconds=llm_peak_seconds,
        canvas_size=canvas_size,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def _entry_from_dict(payload: Any) -> SnapshotEntry:
    if not isinstance(payload, Mapping) or set(payload) != {
        "track_id", "revision", "source_text", "translated_text", "confidence", "bounds"
    }:
        raise SnapshotError("快照条目字段无效")
    bounds = payload["bounds"]
    if not isinstance(bounds, list):
        raise SnapshotError("快照条目 bounds 类型无效")
    return SnapshotEntry(
        track_id=payload["track_id"],
        revision=payload["revision"],
        source_text=payload["source_text"],
        translated_text=payload["translated_text"],
        confidence=payload["confidence"],
        bounds=tuple(bounds),
    )


def _cache_hit_from_dict(payload: Any) -> CacheHit:
    if not isinstance(payload, Mapping) or set(payload) != {"source_text", "hits"}:
        raise SnapshotError("缓存排行字段无效")
    return CacheHit(source_text=payload["source_text"], hits=payload["hits"])


def _optional_float(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if type(value) not in {int, float}:
        raise SnapshotError(f"快照 {label} 类型无效")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise SnapshotError(f"快照 {label} 必须是非负有限数")
    return result

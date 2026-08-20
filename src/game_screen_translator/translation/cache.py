from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import unicodedata
from concurrent.futures import Future
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator, Literal, Sequence

from game_screen_translator.domain import ContextPair


_SCHEMA_VERSION = 1
_AUTOMATIC_KEY_POLICY = "stable-source-v1"
_SPACE_RE = re.compile(r"\s+")
CacheOrigin = Literal["manual", "automatic"]


class TranslationCacheError(RuntimeError):
    """Raised when a profile cache cannot be opened or queried safely."""


def normalize_source_text(text: str) -> str:
    return _SPACE_RE.sub(" ", unicodedata.normalize("NFKC", text)).strip()


def context_fingerprint(context: Sequence[ContextPair]) -> str:
    payload = [
        [normalize_source_text(pair.source), normalize_source_text(pair.target)]
        for pair in context
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CacheEnvironment:
    profile_id: str
    source_language: str
    target_language: str
    model: str
    prompt_version: str
    glossary_revision: str

    def __post_init__(self) -> None:
        values = (
            self.profile_id,
            self.source_language,
            self.target_language,
            self.model,
            self.prompt_version,
            self.glossary_revision,
        )
        if any(not value.strip() for value in values):
            raise ValueError("缓存环境字段均不能为空")

    def automatic_key(
        self,
        source_text: str,
        context: Sequence[ContextPair],
    ) -> tuple[str, str, str]:
        normalized = normalize_source_text(source_text)
        if not normalized:
            raise ValueError("缓存原文不能为空")
        # Context still records how the first translation was produced, but it
        # is deliberately not part of this per-profile translation identity.
        context_revision = context_fingerprint(context)
        payload = {
            "schema": _SCHEMA_VERSION,
            "key_policy": _AUTOMATIC_KEY_POLICY,
            "profile": self.profile_id,
            "source": normalized,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "glossary_revision": self.glossary_revision,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest(), normalized, context_revision


@dataclass(frozen=True, slots=True)
class CacheHit:
    translated_text: str
    origin: CacheOrigin


@dataclass(frozen=True, slots=True)
class InFlightCacheClaim:
    cache_key: str
    future: Future[None]
    is_owner: bool


@dataclass(frozen=True, slots=True)
class CacheStats:
    automatic_entries: int
    manual_corrections: int
    automatic_hits: int
    manual_hits: int


@dataclass(frozen=True, slots=True)
class ManualCorrection:
    source_text: str
    translated_text: str
    updated_at: str
    hit_count: int


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class TranslationCache:
    """Thread-safe-by-connection SQLite cache scoped to one game profile."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        if not self.database_path.parent.is_dir():
            raise TranslationCacheError(
                f"缓存目录不存在：{self.database_path.parent}"
            )
        self._inflight_lock = threading.Lock()
        self._inflight: dict[str, Future[None]] = {}
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path), timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        try:
            with self._connection() as connection:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version not in {0, _SCHEMA_VERSION}:
                    raise TranslationCacheError(
                        f"不支持的缓存数据库版本：{version}"
                    )
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS automatic_translations (
                        cache_key TEXT PRIMARY KEY,
                        source_key TEXT NOT NULL,
                        source_text TEXT NOT NULL,
                        translated_text TEXT NOT NULL,
                        source_language TEXT NOT NULL,
                        target_language TEXT NOT NULL,
                        model TEXT NOT NULL,
                        prompt_version TEXT NOT NULL,
                        glossary_revision TEXT NOT NULL,
                        context_fingerprint TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        last_used_at TEXT,
                        hit_count INTEGER NOT NULL DEFAULT 0
                    );

                    CREATE INDEX IF NOT EXISTS idx_automatic_source
                    ON automatic_translations(source_key);

                    CREATE TABLE IF NOT EXISTS manual_corrections (
                        source_key TEXT NOT NULL,
                        source_language TEXT NOT NULL,
                        target_language TEXT NOT NULL,
                        source_text TEXT NOT NULL,
                        translated_text TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        last_used_at TEXT,
                        hit_count INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (source_key, source_language, target_language)
                    );
                    """
                )
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
        except sqlite3.Error as exc:
            raise TranslationCacheError(f"无法初始化翻译缓存：{exc}") from exc

    def lookup(
        self,
        source_text: str,
        environment: CacheEnvironment,
        context: Sequence[ContextPair],
    ) -> CacheHit | None:
        cache_key, source_key, _ = environment.automatic_key(source_text, context)
        now = _utc_now()
        try:
            with self._connection() as connection:
                manual = connection.execute(
                    """
                    SELECT translated_text
                    FROM manual_corrections
                    WHERE source_key = ? AND source_language = ? AND target_language = ?
                    """,
                    (
                        source_key,
                        environment.source_language,
                        environment.target_language,
                    ),
                ).fetchone()
                if manual is not None:
                    connection.execute(
                        """
                        UPDATE manual_corrections
                        SET hit_count = hit_count + 1, last_used_at = ?
                        WHERE source_key = ? AND source_language = ? AND target_language = ?
                        """,
                        (
                            now,
                            source_key,
                            environment.source_language,
                            environment.target_language,
                        ),
                    )
                    return CacheHit(str(manual["translated_text"]), "manual")

                automatic = connection.execute(
                    """
                    SELECT translated_text
                    FROM automatic_translations
                    WHERE cache_key = ?
                    """,
                    (cache_key,),
                ).fetchone()
                if automatic is None:
                    return None
                connection.execute(
                    """
                    UPDATE automatic_translations
                    SET hit_count = hit_count + 1, last_used_at = ?
                    WHERE cache_key = ?
                    """,
                    (now, cache_key),
                )
                return CacheHit(str(automatic["translated_text"]), "automatic")
        except sqlite3.Error as exc:
            raise TranslationCacheError(f"读取翻译缓存失败：{exc}") from exc

    def claim_inflight(
        self,
        source_text: str,
        environment: CacheEnvironment,
        context: Sequence[ContextPair],
    ) -> InFlightCacheClaim:
        cache_key, _, _ = environment.automatic_key(source_text, context)
        with self._inflight_lock:
            future = self._inflight.get(cache_key)
            if future is not None:
                return InFlightCacheClaim(cache_key, future, False)
            future = Future()
            future.set_running_or_notify_cancel()
            self._inflight[cache_key] = future
            return InFlightCacheClaim(cache_key, future, True)

    def complete_inflight(self, claim: InFlightCacheClaim) -> None:
        self._settle_inflight(claim, error=None)

    def fail_inflight(
        self,
        claim: InFlightCacheClaim,
        error: BaseException,
    ) -> None:
        self._settle_inflight(claim, error=error)

    @property
    def inflight_count(self) -> int:
        with self._inflight_lock:
            return len(self._inflight)

    def _settle_inflight(
        self,
        claim: InFlightCacheClaim,
        *,
        error: BaseException | None,
    ) -> None:
        if not claim.is_owner:
            raise ValueError("只有在途翻译所有者可以结束请求")
        with self._inflight_lock:
            current = self._inflight.get(claim.cache_key)
            if current is not claim.future:
                return
            del self._inflight[claim.cache_key]
        if claim.future.done():
            return
        if error is None:
            claim.future.set_result(None)
        else:
            claim.future.set_exception(error)

    def store_automatic(
        self,
        source_text: str,
        translated_text: str,
        environment: CacheEnvironment,
        context: Sequence[ContextPair],
    ) -> None:
        translated = translated_text.strip()
        if not translated:
            raise ValueError("缓存译文不能为空")
        cache_key, source_key, context_revision = environment.automatic_key(
            source_text,
            context,
        )
        now = _utc_now()
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO automatic_translations (
                        cache_key, source_key, source_text, translated_text,
                        source_language, target_language, model, prompt_version,
                        glossary_revision, context_fingerprint, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        source_text = excluded.source_text,
                        translated_text = excluded.translated_text,
                        updated_at = excluded.updated_at
                    """,
                    (
                        cache_key,
                        source_key,
                        source_text.strip(),
                        translated,
                        environment.source_language,
                        environment.target_language,
                        environment.model,
                        environment.prompt_version,
                        environment.glossary_revision,
                        context_revision,
                        now,
                        now,
                    ),
                )
        except sqlite3.Error as exc:
            raise TranslationCacheError(f"写入翻译缓存失败：{exc}") from exc

    def set_manual_correction(
        self,
        source_text: str,
        translated_text: str,
        *,
        source_language: str,
        target_language: str,
    ) -> None:
        source_key = normalize_source_text(source_text)
        translated = translated_text.strip()
        if not source_key or not translated:
            raise ValueError("人工修订的原文和译文均不能为空")
        now = _utc_now()
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO manual_corrections (
                        source_key, source_language, target_language,
                        source_text, translated_text, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_key, source_language, target_language)
                    DO UPDATE SET
                        source_text = excluded.source_text,
                        translated_text = excluded.translated_text,
                        updated_at = excluded.updated_at
                    """,
                    (
                        source_key,
                        source_language,
                        target_language,
                        source_text.strip(),
                        translated,
                        now,
                    ),
                )
        except sqlite3.Error as exc:
            raise TranslationCacheError(f"写入人工修订失败：{exc}") from exc

    def delete_manual_correction(
        self,
        source_text: str,
        *,
        source_language: str,
        target_language: str,
    ) -> bool:
        source_key = normalize_source_text(source_text)
        if not source_key:
            raise ValueError("人工修订的原文不能为空")
        try:
            with self._connection() as connection:
                cursor = connection.execute(
                    """
                    DELETE FROM manual_corrections
                    WHERE source_key = ? AND source_language = ? AND target_language = ?
                    """,
                    (source_key, source_language, target_language),
                )
                return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise TranslationCacheError(f"删除人工修订失败：{exc}") from exc

    def list_manual_corrections(
        self,
        *,
        source_language: str,
        target_language: str,
    ) -> tuple[ManualCorrection, ...]:
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    """
                    SELECT source_text, translated_text, updated_at, hit_count
                    FROM manual_corrections
                    WHERE source_language = ? AND target_language = ?
                    ORDER BY source_text COLLATE NOCASE, source_text
                    """,
                    (source_language, target_language),
                ).fetchall()
        except sqlite3.Error as exc:
            raise TranslationCacheError(f"读取人工修订列表失败：{exc}") from exc
        return tuple(
            ManualCorrection(
                source_text=str(row["source_text"]),
                translated_text=str(row["translated_text"]),
                updated_at=str(row["updated_at"]),
                hit_count=int(row["hit_count"]),
            )
            for row in rows
        )

    def replace_manual_corrections(
        self,
        corrections: Sequence[tuple[str, str]],
        *,
        source_language: str,
        target_language: str,
    ) -> None:
        normalized: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for source_text, translated_text in corrections:
            source_key = normalize_source_text(source_text)
            translated = translated_text.strip()
            if not source_key or not translated:
                raise ValueError("人工修订的原文和译文均不能为空")
            if source_key in seen:
                raise ValueError(f"人工修订原文重复：{source_text}")
            seen.add(source_key)
            normalized.append((source_key, source_text.strip(), translated))

        now = _utc_now()
        try:
            with self._connection() as connection:
                existing_rows = connection.execute(
                    """
                    SELECT source_key
                    FROM manual_corrections
                    WHERE source_language = ? AND target_language = ?
                    """,
                    (source_language, target_language),
                ).fetchall()
                existing = {str(row["source_key"]) for row in existing_rows}
                for source_key, source_text, translated in normalized:
                    connection.execute(
                        """
                        INSERT INTO manual_corrections (
                            source_key, source_language, target_language,
                            source_text, translated_text, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(source_key, source_language, target_language)
                        DO UPDATE SET
                            source_text = excluded.source_text,
                            translated_text = excluded.translated_text,
                            updated_at = excluded.updated_at
                        """,
                        (
                            source_key,
                            source_language,
                            target_language,
                            source_text,
                            translated,
                            now,
                        ),
                    )
                for source_key in existing - seen:
                    connection.execute(
                        """
                        DELETE FROM manual_corrections
                        WHERE source_key = ?
                          AND source_language = ?
                          AND target_language = ?
                        """,
                        (source_key, source_language, target_language),
                    )
        except sqlite3.Error as exc:
            raise TranslationCacheError(f"保存人工修订列表失败：{exc}") from exc

    def stats(self) -> CacheStats:
        try:
            with self._connection() as connection:
                automatic = connection.execute(
                    "SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM automatic_translations"
                ).fetchone()
                manual = connection.execute(
                    "SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM manual_corrections"
                ).fetchone()
        except sqlite3.Error as exc:
            raise TranslationCacheError(f"读取缓存统计失败：{exc}") from exc
        return CacheStats(
            automatic_entries=int(automatic[0]),
            manual_corrections=int(manual[0]),
            automatic_hits=int(automatic[1]),
            manual_hits=int(manual[1]),
        )

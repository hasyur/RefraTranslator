import sqlite3
from pathlib import Path

import pytest

from game_screen_translator.domain import ContextPair
from game_screen_translator.translation.cache import (
    CacheEnvironment,
    TranslationCache,
    TranslationCacheError,
    normalize_source_text,
)


def _environment(**changes: str) -> CacheEnvironment:
    values = {
        "profile_id": "game-a",
        "source_language": "japan",
        "target_language": "简体中文",
        "model": "hy-mt1.5-7b",
        "prompt_version": "prompt-v1",
        "glossary_revision": "glossary-v1",
    }
    values.update(changes)
    return CacheEnvironment(**values)


def test_automatic_cache_key_ignores_context_and_tracks_translation_contract(
    tmp_path: Path,
) -> None:
    cache = TranslationCache(tmp_path / "translations.sqlite3")
    first_context = (ContextPair("前文", "前文译文"),)
    second_context = (ContextPair("另一段", "另一段译文"),)
    environment = _environment()
    first_key, first_source_key = environment.automatic_key(
        "仕事 だ。",
        first_context,
    )
    second_key, second_source_key = environment.automatic_key(
        "仕事 だ。",
        second_context,
    )

    assert first_key == second_key
    assert first_key == "77545573f2a9c0683258d1dc18c71fefc2c3709de42329ea136558830051a19e"
    assert first_source_key == second_source_key == "仕事 だ。"
    profile_key, _ = _environment(profile_id="game-b").automatic_key(
        "仕事 だ。",
        first_context,
    )
    source_language_key, _ = _environment(
        source_language="English"
    ).automatic_key("仕事 だ。", first_context)
    assert profile_key != first_key
    assert source_language_key != first_key

    cache.store_automatic(" 仕事\nだ。 ", "是工作。", environment, first_context)

    hit = cache.lookup("仕事 だ。", environment, first_context)
    assert hit is not None
    assert (hit.translated_text, hit.origin) == ("是工作。", "automatic")
    context_hit = cache.lookup("仕事 だ。", environment, second_context)
    assert context_hit is not None
    assert context_hit.translated_text == "是工作。"
    assert cache.lookup("仕事だった。", environment, first_context) is None
    assert cache.lookup(
        "仕事 だ。",
        _environment(glossary_revision="glossary-v2"),
        first_context,
    ) is None
    assert cache.lookup(
        "仕事 だ。",
        _environment(model="another-model"),
        first_context,
    ) is None
    assert cache.lookup(
        "仕事 だ。",
        _environment(prompt_version="prompt-v2"),
        first_context,
    ) is None
    assert cache.lookup(
        "仕事 だ。",
        _environment(target_language="English"),
        first_context,
    ) is None


def test_manual_correction_has_priority_over_all_model_cache_dimensions(tmp_path: Path) -> None:
    cache = TranslationCache(tmp_path / "translations.sqlite3")
    environment = _environment()
    cache.store_automatic("フィクサー", "修理工", environment, ())
    cache.set_manual_correction(
        "フィクサー",
        "中间人",
        source_language="japan",
        target_language="简体中文",
    )

    hit = cache.lookup(
        "フィクサー",
        _environment(model="changed", prompt_version="prompt-v99"),
        (ContextPair("上下文", "上下文"),),
    )

    assert hit is not None
    assert (hit.translated_text, hit.origin) == ("中间人", "manual")
    stats = cache.stats()
    assert stats.automatic_entries == 1
    assert stats.manual_corrections == 1
    assert stats.manual_hits == 1

    assert cache.delete_manual_correction(
        "フィクサー",
        source_language="japan",
        target_language="简体中文",
    )
    assert not cache.delete_manual_correction(
        "フィクサー",
        source_language="japan",
        target_language="简体中文",
    )


def test_new_cache_uses_v2_schema_without_changing_hits_or_stats(
    tmp_path: Path,
) -> None:
    database = tmp_path / "translations.sqlite3"
    cache = TranslationCache(database)
    environment = _environment()

    cache.store_automatic("仕事 だ。", "是工作。", environment, ())
    hit = cache.lookup("仕事 だ。", environment, ())
    stats = cache.stats()

    with sqlite3.connect(database) as connection:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        columns = [
            str(row[1])
            for row in connection.execute("PRAGMA table_info(automatic_translations)")
        ]
        indexes = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }

    assert version == 2
    assert columns == ["cache_key", "translated_text", "hit_count"]
    assert "idx_automatic_source" not in indexes
    assert hit is not None
    assert (hit.translated_text, hit.origin) == ("是工作。", "automatic")
    assert stats.automatic_entries == 1
    assert stats.automatic_hits == 1
    assert stats.manual_corrections == 0
    assert stats.manual_hits == 0


def test_v1_migration_discards_automatic_rows_and_preserves_manual_corrections(
    tmp_path: Path,
) -> None:
    database = tmp_path / "translations.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE automatic_translations (
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
            CREATE TABLE manual_corrections (
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
            INSERT INTO automatic_translations VALUES (
                'old-cache-key', '旧原文', '旧原文', '旧译文', 'japan',
                '简体中文', 'old-model', 'old-prompt', 'old-glossary',
                'old-context', '2026-01-01T00:00:00+00:00',
                '2026-01-01T00:00:00+00:00', NULL, 4
            );
            INSERT INTO manual_corrections VALUES (
                '手工', 'japan', '简体中文', '手工', '保留',
                '2026-01-02T00:00:00+00:00',
                '2026-01-03T00:00:00+00:00', 7
            );
            PRAGMA user_version = 1;
            """
        )

    cache = TranslationCache(database)

    with sqlite3.connect(database) as connection:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        automatic_columns = [
            str(row[1])
            for row in connection.execute("PRAGMA table_info(automatic_translations)")
        ]
        automatic_rows = connection.execute(
            "SELECT * FROM automatic_translations"
        ).fetchall()
        manual_row = connection.execute(
            """
            SELECT source_key, source_language, target_language, source_text,
                   translated_text, updated_at, last_used_at, hit_count
            FROM manual_corrections
            """
        ).fetchone()

    assert version == 2
    assert automatic_columns == ["cache_key", "translated_text", "hit_count"]
    assert automatic_rows == []
    assert manual_row == (
        "手工",
        "japan",
        "简体中文",
        "手工",
        "保留",
        "2026-01-02T00:00:00+00:00",
        "2026-01-03T00:00:00+00:00",
        7,
    )
    hit = cache.lookup("手工", _environment(), ())
    assert hit is not None
    assert (hit.translated_text, hit.origin) == ("保留", "manual")


def test_v1_migration_rolls_back_when_rebuilding_schema_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "translations.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE automatic_translations (
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
            CREATE TABLE manual_corrections (
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
            INSERT INTO automatic_translations VALUES (
                'rollback-key', '回滚原文', '回滚原文', '回滚译文', 'japan',
                '简体中文', 'model', 'prompt', 'glossary', 'context',
                '2026-01-01T00:00:00+00:00',
                '2026-01-01T00:00:00+00:00', NULL, 3
            );
            INSERT INTO manual_corrections VALUES (
                '保留', 'japan', '简体中文', '保留', '手工保留',
                '2026-01-02T00:00:00+00:00', NULL, 2
            );
            PRAGMA user_version = 1;
            """
        )

    events: list[str] = []

    class FailingConnection(sqlite3.Connection):
        def execute(self, sql: str, parameters: object = ()) -> sqlite3.Cursor:
            statement = " ".join(sql.split())
            if statement.startswith("DROP TABLE IF EXISTS automatic_translations"):
                events.append("drop-automatic")
            if statement.startswith("CREATE TABLE IF NOT EXISTS manual_corrections"):
                events.append("fail-manual-create")
                raise sqlite3.OperationalError("injected schema failure")
            return super().execute(sql, parameters)

    def failing_connect(cache: TranslationCache) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(cache.database_path),
            timeout=10.0,
            factory=FailingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    monkeypatch.setattr(TranslationCache, "_connect", failing_connect)
    with pytest.raises(TranslationCacheError, match="无法初始化翻译缓存"):
        TranslationCache(database)

    assert events == ["drop-automatic", "fail-manual-create"]
    with sqlite3.connect(database) as connection:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        columns = [
            str(row[1])
            for row in connection.execute("PRAGMA table_info(automatic_translations)")
        ]
        automatic_row = connection.execute(
            "SELECT cache_key, translated_text, hit_count FROM automatic_translations"
        ).fetchone()
        manual_row = connection.execute(
            "SELECT source_key, translated_text, hit_count FROM manual_corrections"
        ).fetchone()

    assert version == 1
    assert columns == [
        "cache_key",
        "source_key",
        "source_text",
        "translated_text",
        "source_language",
        "target_language",
        "model",
        "prompt_version",
        "glossary_revision",
        "context_fingerprint",
        "created_at",
        "updated_at",
        "last_used_at",
        "hit_count",
    ]
    assert automatic_row == ("rollback-key", "回滚译文", 3)
    assert manual_row == ("保留", "手工保留", 2)


def test_cache_rejects_a_newer_schema_version(tmp_path: Path) -> None:
    database = tmp_path / "translations.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 3")

    with pytest.raises(TranslationCacheError, match="不支持的缓存数据库版本：3"):
        TranslationCache(database)


def test_source_normalization_is_unicode_and_whitespace_stable() -> None:
    assert normalize_source_text("  ＡＢＣ\n １２３ ") == "ABC 123"


def test_manual_corrections_can_be_listed_and_replaced_atomically(tmp_path: Path) -> None:
    cache = TranslationCache(tmp_path / "translations.sqlite3")
    cache.replace_manual_corrections(
        (("待て。", "等等。"), ("急げ。", "快点。")),
        source_language="japan",
        target_language="简体中文",
    )
    cache.lookup("待て。", _environment(), ())

    cache.replace_manual_corrections(
        (("待て。", "等一下。"), ("座れ。", "坐下。")),
        source_language="japan",
        target_language="简体中文",
    )
    corrections = cache.list_manual_corrections(
        source_language="japan",
        target_language="简体中文",
    )

    assert [(item.source_text, item.translated_text) for item in corrections] == [
        ("座れ。", "坐下。"),
        ("待て。", "等一下。"),
    ]
    assert next(item for item in corrections if item.source_text == "待て。").hit_count == 1


def test_cache_operations_release_database_file_on_windows(tmp_path: Path) -> None:
    database = tmp_path / "translations.sqlite3"
    cache = TranslationCache(database)
    cache.stats()

    database.unlink()

    assert not database.exists()

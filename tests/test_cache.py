from pathlib import Path

from game_screen_translator.domain import ContextPair
from game_screen_translator.translation.cache import (
    CacheEnvironment,
    TranslationCache,
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
    first_key, _, first_context_revision = environment.automatic_key(
        "仕事 だ。",
        first_context,
    )
    second_key, _, second_context_revision = environment.automatic_key(
        "仕事 だ。",
        second_context,
    )

    assert first_key == second_key
    assert first_context_revision != second_context_revision

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

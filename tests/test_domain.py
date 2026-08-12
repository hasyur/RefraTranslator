import pytest

from game_screen_translator.domain import RevisionRegistry, SourceText, TranslationBatch


def test_wire_id_is_safe_and_revision_specific() -> None:
    first = SourceText("字幕 区", "人物/<1>", 3, "こんにちは")
    second = SourceText("字幕 区", "人物/<1>", 4, "こんにちは")

    assert first.wire_id.startswith("sn_")
    assert first.wire_id.endswith("_r3")
    assert first.wire_id != second.wire_id
    assert all(character.isalnum() or character == "_" for character in first.wire_id)


def test_batch_rejects_duplicate_track_revision() -> None:
    item = SourceText("z", "t", 1, "one")

    with pytest.raises(ValueError, match="重复"):
        TranslationBatch((item, item))


def test_revision_registry_never_moves_backwards() -> None:
    registry = RevisionRegistry()
    old = SourceText("z", "t", 1, "old")
    new = SourceText("z", "t", 2, "new")

    assert registry.observe(new)
    assert not registry.observe(old)
    assert registry.latest_revision("z", "t") == 2
    assert registry.is_current(new)
    assert not registry.is_current(old)

from game_screen_translator.domain import SourceText, TranslationResult
from game_screen_translator.live.tracker import StableTextTracker
from game_screen_translator.ocr.types import OcrText


def _ocr(text: str, bounds=(10, 20, 210, 60)) -> OcrText:
    left, top, right, bottom = bounds
    return OcrText(
        text,
        0.99,
        ((left, top), (right, top), (right, bottom), (left, bottom)),
    )


def test_text_is_emitted_only_after_count_and_time_stability() -> None:
    tracker = StableTextTracker(
        "zone",
        stable_observations=2,
        stable_seconds=0.15,
        clear_after_seconds=0.9,
    )

    first = tracker.observe((_ocr("こんにちは"),), now=1.0)
    too_soon = tracker.observe((_ocr("こんにちは"),), now=1.10)
    stable = tracker.observe((_ocr("こんにちは"),), now=1.16)
    repeated = tracker.observe((_ocr("こんにちは"),), now=1.30)

    assert first.stable_sources == ()
    assert too_soon.stable_sources == ()
    assert len(stable.stable_sources) == 1
    assert stable.stable_sources[0].revision == 1
    assert repeated.stable_sources == ()


def test_changed_text_reuses_track_but_increments_revision() -> None:
    tracker = StableTextTracker(
        "zone",
        stable_observations=2,
        stable_seconds=0,
        clear_after_seconds=1,
    )
    tracker.observe((_ocr("古い"),), 1.0)
    old = tracker.observe((_ocr("古い"),), 1.1).stable_sources[0]

    changed = tracker.observe((_ocr("新しい"),), 1.2)
    stable = tracker.observe((_ocr("新しい"),), 1.3)

    assert changed.stable_sources == ()
    assert stable.stable_sources[0].track_id == old.track_id
    assert stable.stable_sources[0].revision == 2
    assert tracker.visible_tracks[0].translated_text is None


def test_old_translation_cannot_overwrite_new_revision() -> None:
    tracker = StableTextTracker(
        "zone",
        stable_observations=1,
        stable_seconds=0,
        clear_after_seconds=1,
    )
    old = tracker.observe((_ocr("古い"),), 1.0).stable_sources[0]
    new = tracker.observe((_ocr("新しい"),), 1.1).stable_sources[0]

    tracker.apply_translations((TranslationResult(old, "旧的"),))
    assert tracker.visible_tracks[0].translated_text is None

    tracker.apply_translations((TranslationResult(new, "新的"),))
    assert tracker.visible_tracks[0].translated_text == "新的"


def test_track_clears_only_after_an_empty_ocr_observation() -> None:
    tracker = StableTextTracker(
        "zone",
        stable_observations=1,
        stable_seconds=0,
        clear_after_seconds=0.9,
    )
    tracker.observe((_ocr("残る"),), 1.0)

    assert len(tracker.visible_tracks) == 1
    update = tracker.expire(2.0)

    assert len(update.removed_track_ids) == 1
    assert tracker.visible_tracks == ()


def test_far_boxes_do_not_share_a_track() -> None:
    tracker = StableTextTracker(
        "zone",
        stable_observations=1,
        stable_seconds=0,
        clear_after_seconds=2,
    )
    tracker.observe((_ocr("同じ", (0, 0, 100, 40)),), 1.0)
    tracker.observe((_ocr("同じ", (800, 500, 900, 540)),), 1.1)

    assert len(tracker.visible_tracks) == 2

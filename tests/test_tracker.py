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


def test_layout_line_breaks_reach_the_translation_source() -> None:
    tracker = StableTextTracker(
        "zone",
        stable_observations=1,
        stable_seconds=0,
        clear_after_seconds=1,
    )

    update = tracker.observe((_ocr("この世界に\n希望はある"),), now=1.0)

    assert update.stable_sources[0].text == "この世界に\n希望はある"


def test_clear_drops_visible_state_without_reusing_track_ids() -> None:
    tracker = StableTextTracker("zone", stable_observations=1)
    old = tracker.observe((_ocr("古い"),), now=1.0).stable_sources[0]

    assert tracker.clear() == (old.track_id,)
    assert tracker.visible_tracks == ()
    assert not tracker.has_pending_revisions

    new = tracker.observe((_ocr("新しい"),), now=2.0).stable_sources[0]
    assert new.track_id != old.track_id


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


def test_single_changed_observation_keeps_visible_translation() -> None:
    tracker = StableTextTracker(
        "zone",
        stable_observations=1,
        stable_seconds=0,
        clear_after_seconds=1,
    )
    source = tracker.observe((_ocr("古い"),), 1.0).stable_sources[0]
    tracker.apply_translations((TranslationResult(source, "旧译文"),))

    noisy = tracker.observe((_ocr("古し"),), 1.1)
    track = tracker.visible_tracks[0]

    assert noisy.stable_sources == ()
    assert track.text == "古い"
    assert track.revision == 1
    assert track.translated_text == "旧译文"
    assert track.display_translation == "旧译文"
    assert tracker.has_pending_revisions

    restored = tracker.observe((_ocr("古い"),), 1.2)
    assert restored.stable_sources == ()
    assert not tracker.has_pending_revisions
    assert tracker.visible_tracks[0].display_translation == "旧译文"


def test_confirmed_change_keeps_old_translation_until_new_one_is_ready() -> None:
    tracker = StableTextTracker(
        "zone",
        stable_observations=1,
        stable_seconds=0,
        clear_after_seconds=1,
    )
    old = tracker.observe((_ocr("古い"),), 1.0).stable_sources[0]
    tracker.apply_translations((TranslationResult(old, "旧译文"),))

    first = tracker.observe((_ocr("新しい"),), 1.1)
    confirmed = tracker.observe((_ocr("新しい"),), 1.2)
    new = confirmed.stable_sources[0]
    waiting = tracker.visible_tracks[0]

    assert first.stable_sources == ()
    assert new.track_id == old.track_id
    assert new.revision == 2
    assert waiting.text == "新しい"
    assert waiting.translated_text is None
    assert waiting.retained_translation == "旧译文"
    assert waiting.display_translation == "旧译文"

    tracker.apply_translations((TranslationResult(old, "过期译文"),))
    assert tracker.visible_tracks[0].display_translation == "旧译文"

    tracker.apply_translations((TranslationResult(new, "新译文"),))
    replaced = tracker.visible_tracks[0]
    assert replaced.translated_text == "新译文"
    assert replaced.retained_translation is None
    assert replaced.display_translation == "新译文"


def test_missing_ocr_keeps_translation_during_clear_grace_period() -> None:
    tracker = StableTextTracker(
        "zone",
        stable_observations=1,
        stable_seconds=0,
        clear_after_seconds=0.9,
    )
    source = tracker.observe((_ocr("残る"),), 1.0).stable_sources[0]
    tracker.apply_translations((TranslationResult(source, "保留译文"),))

    tracker.observe((), 1.2)
    assert tracker.visible_tracks[0].display_translation == "保留译文"
    assert tracker.expire_missing(2.0).removed_track_ids == ()
    assert tracker.visible_tracks[0].display_translation == "保留译文"

    removed = tracker.expire_missing(2.11)
    assert len(removed.removed_track_ids) == 1
    assert tracker.visible_tracks == ()


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


def test_timer_expires_only_tracks_already_missing_from_an_ocr_scan() -> None:
    tracker = StableTextTracker(
        "zone",
        stable_observations=1,
        stable_seconds=0,
        clear_after_seconds=0.9,
    )
    tracker.observe((_ocr("残る"),), 1.0)

    still_visible = tracker.expire_missing(10.0)
    tracker.observe((_ocr("残る"),), 10.0)
    tracker.observe((), 10.1)
    waiting = tracker.expire_missing(10.5)
    removed = tracker.expire_missing(11.01)

    assert still_visible.removed_track_ids == ()
    assert waiting.removed_track_ids == ()
    assert len(removed.removed_track_ids) == 1
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


def test_partial_observation_replaces_only_scanned_tracks() -> None:
    tracker = StableTextTracker("zone", clear_after_seconds=1.0)
    tracker.observe(
        (
            _ocr("待って。", (10, 10, 180, 40)),
            _ocr("先へ進め。", (10, 80, 220, 110)),
        ),
        1.0,
    )
    before = {track.text: track for track in tracker.visible_tracks}

    update = tracker.observe_partial(
        (_ocr("止まれ。", (10, 10, 180, 40)),),
        2.0,
        replace_track_ids=(before["待って。"].track_id,),
    )

    after = {track.text: track for track in update.visible_tracks}
    assert set(after) == {"止まれ。", "先へ進め。"}
    assert after["止まれ。"].track_id == before["待って。"].track_id
    assert after["止まれ。"].revision == 2
    assert after["先へ進め。"].last_seen == before["先へ進め。"].last_seen


def test_partial_empty_observation_marks_only_scanned_track_missing() -> None:
    tracker = StableTextTracker("zone", clear_after_seconds=1.0)
    tracker.observe(
        (
            _ocr("消える。", (10, 10, 180, 40)),
            _ocr("残る。", (10, 80, 180, 110)),
        ),
        1.0,
    )
    before = {track.text: track for track in tracker.visible_tracks}

    update = tracker.observe_partial(
        (),
        1.2,
        replace_track_ids=(before["消える。"].track_id,),
    )

    after = {track.text: track for track in update.visible_tracks}
    assert after["消える。"].missing_since == 1.2
    assert after["残る。"].missing_since is None

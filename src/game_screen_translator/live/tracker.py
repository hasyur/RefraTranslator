from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Iterable

from game_screen_translator.domain import SourceText, TranslationResult
from game_screen_translator.ocr.types import OcrText


Bounds = tuple[int, int, int, int]
_INLINE_SPACE_RE = re.compile(r"[^\S\r\n]+")
_LINE_BREAK_RE = re.compile(r"\r\n?|\n")


def normalize_text(text: str) -> str:
    lines = (
        _INLINE_SPACE_RE.sub(" ", line).strip()
        for line in _LINE_BREAK_RE.split(text)
    )
    return "\n".join(line for line in lines if line)


def _intersection_over_union(first: Bounds, second: Bounds) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0, right - left) * max(0, bottom - top)
    if not intersection:
        return 0.0
    first_area = max(1, first[2] - first[0]) * max(1, first[3] - first[1])
    second_area = max(1, second[2] - second[0]) * max(1, second[3] - second[1])
    return intersection / (first_area + second_area - intersection)


def _center_distance_ratio(first: Bounds, second: Bounds) -> float:
    first_center = ((first[0] + first[2]) / 2, (first[1] + first[3]) / 2)
    second_center = ((second[0] + second[2]) / 2, (second[1] + second[3]) / 2)
    dx = first_center[0] - second_center[0]
    dy = first_center[1] - second_center[1]
    scale = max(20.0, first[2] - first[0], first[3] - first[1], second[2] - second[0], second[3] - second[1])
    return (dx * dx + dy * dy) ** 0.5 / scale


@dataclass(frozen=True, slots=True)
class TrackedText:
    track_id: str
    revision: int
    text: str
    confidence: float
    bounds: Bounds
    first_seen: float
    last_seen: float
    observations: int
    stable_emitted: bool = False
    translated_text: str | None = None
    missing_since: float | None = None
    retained_translation: str | None = None

    @property
    def display_translation(self) -> str | None:
        """Return the current translation or the previous one held during replacement."""
        if self.translated_text is not None:
            return self.translated_text
        return self.retained_translation

    def source(self, zone_id: str) -> SourceText:
        return SourceText(zone_id, self.track_id, self.revision, self.text)


@dataclass(frozen=True, slots=True)
class TrackerUpdate:
    stable_sources: tuple[SourceText, ...]
    visible_tracks: tuple[TrackedText, ...]
    removed_track_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _RevisionCandidate:
    text: str
    confidence: float
    bounds: Bounds
    first_seen: float
    last_seen: float
    observations: int


class StableTextTracker:
    def __init__(
        self,
        zone_id: str,
        *,
        stable_observations: int = 1,
        stable_seconds: float = 0.0,
        clear_after_seconds: float = 0.9,
        revision_confirmations: int = 2,
    ) -> None:
        if not zone_id.strip():
            raise ValueError("zone_id 不能为空")
        if stable_observations < 1:
            raise ValueError("stable_observations 必须至少为 1")
        if revision_confirmations < 1:
            raise ValueError("revision_confirmations 必须至少为 1")
        if stable_seconds < 0 or clear_after_seconds < 0:
            raise ValueError("稳定与清理时间不能为负数")
        self.zone_id = zone_id
        self.stable_observations = stable_observations
        self.stable_seconds = stable_seconds
        self.clear_after_seconds = clear_after_seconds
        self.revision_confirmations = revision_confirmations
        self._tracks: dict[str, TrackedText] = {}
        self._revision_candidates: dict[str, _RevisionCandidate] = {}
        self._counter = 0

    @property
    def visible_tracks(self) -> tuple[TrackedText, ...]:
        return tuple(sorted(self._tracks.values(), key=lambda track: (track.bounds[1], track.bounds[0])))

    @property
    def has_pending_revisions(self) -> bool:
        return bool(self._revision_candidates)

    def observe(self, observations: Iterable[OcrText], now: float) -> TrackerUpdate:
        return self._observe_replacing(
            observations,
            now,
            replace_track_ids=set(self._tracks),
        )

    def observe_partial(
        self,
        observations: Iterable[OcrText],
        now: float,
        *,
        replace_track_ids: Iterable[str],
    ) -> TrackerUpdate:
        """Replace only tracks covered by a successfully scanned OCR ROI.

        Tracks outside ``replace_track_ids`` are intentionally untouched: a
        local OCR crop says nothing about whether text elsewhere on screen is
        still visible. New observations may still create tracks inside the
        changed region.
        """
        return self._observe_replacing(
            observations,
            now,
            replace_track_ids={
                track_id for track_id in replace_track_ids if track_id in self._tracks
            },
        )

    def _observe_replacing(
        self,
        observations: Iterable[OcrText],
        now: float,
        *,
        replace_track_ids: set[str],
    ) -> TrackerUpdate:
        unmatched_tracks = set(replace_track_ids)
        stable_sources: list[SourceText] = []

        for observation in sorted(observations, key=lambda item: (item.bounds[1], item.bounds[0])):
            track_id = self._best_match(observation, unmatched_tracks)
            if track_id is None:
                track = self._new_track(observation, now)
            else:
                unmatched_tracks.remove(track_id)
                track = self._update_track(self._tracks[track_id], observation, now)

            if self._is_stable(track, now) and not track.stable_emitted:
                track = replace(track, stable_emitted=True)
                stable_sources.append(track.source(self.zone_id))
            self._tracks[track.track_id] = track

        removed: list[str] = []
        for track_id in tuple(unmatched_tracks):
            self._revision_candidates.pop(track_id, None)
            track = self._tracks[track_id]
            missing_since = (
                track.last_seen if track.missing_since is None else track.missing_since
            )
            if now - missing_since >= self.clear_after_seconds:
                removed.append(track_id)
                del self._tracks[track_id]
            elif track.missing_since is None:
                self._tracks[track_id] = replace(track, missing_since=now)

        return TrackerUpdate(tuple(stable_sources), self.visible_tracks, tuple(removed))

    def expire(self, now: float) -> TrackerUpdate:
        return self.observe((), now)

    def expire_missing(self, now: float) -> TrackerUpdate:
        removed: list[str] = []
        for track_id, track in tuple(self._tracks.items()):
            if (
                track.missing_since is not None
                and now - track.missing_since >= self.clear_after_seconds
            ):
                removed.append(track_id)
                self._revision_candidates.pop(track_id, None)
                del self._tracks[track_id]
        return TrackerUpdate((), self.visible_tracks, tuple(removed))

    def apply_translations(self, results: Iterable[TranslationResult]) -> tuple[TrackedText, ...]:
        for result in results:
            track = self._tracks.get(result.source.track_id)
            if track is None or track.revision != result.source.revision:
                continue
            self._tracks[track.track_id] = replace(
                track,
                translated_text=result.translated_text,
                retained_translation=None,
            )
        return self.visible_tracks

    def _new_track(self, observation: OcrText, now: float) -> TrackedText:
        self._counter += 1
        digest = hashlib.blake2s(
            f"{self.zone_id}\0{self._counter}".encode("utf-8"),
            digest_size=5,
        ).hexdigest()
        return TrackedText(
            track_id=f"track-{digest}",
            revision=1,
            text=normalize_text(observation.text),
            confidence=observation.confidence,
            bounds=observation.bounds,
            first_seen=now,
            last_seen=now,
            observations=1,
        )

    def _update_track(self, track: TrackedText, observation: OcrText, now: float) -> TrackedText:
        text = normalize_text(observation.text)
        if text == track.text:
            self._revision_candidates.pop(track.track_id, None)
            return replace(
                track,
                confidence=observation.confidence,
                bounds=observation.bounds,
                last_seen=now,
                observations=track.observations + 1,
                missing_since=None,
            )
        if track.display_translation is not None:
            return self._stage_revision(track, observation, text, now)
        self._revision_candidates.pop(track.track_id, None)
        return replace(
            track,
            revision=track.revision + 1,
            text=text,
            confidence=observation.confidence,
            bounds=observation.bounds,
            first_seen=now,
            last_seen=now,
            observations=1,
            missing_since=None,
            stable_emitted=False,
            translated_text=None,
            retained_translation=None,
        )

    def _stage_revision(
        self,
        track: TrackedText,
        observation: OcrText,
        text: str,
        now: float,
    ) -> TrackedText:
        candidate = self._revision_candidates.get(track.track_id)
        if candidate is None or candidate.text != text:
            candidate = _RevisionCandidate(
                text,
                observation.confidence,
                observation.bounds,
                now,
                now,
                1,
            )
        else:
            candidate = replace(
                candidate,
                confidence=observation.confidence,
                bounds=observation.bounds,
                last_seen=now,
                observations=candidate.observations + 1,
            )
        self._revision_candidates[track.track_id] = candidate
        if candidate.observations < self.revision_confirmations:
            return replace(
                track,
                confidence=observation.confidence,
                bounds=observation.bounds,
                last_seen=now,
                missing_since=None,
            )

        del self._revision_candidates[track.track_id]
        return replace(
            track,
            revision=track.revision + 1,
            text=candidate.text,
            confidence=candidate.confidence,
            bounds=candidate.bounds,
            first_seen=candidate.first_seen,
            last_seen=candidate.last_seen,
            observations=candidate.observations,
            missing_since=None,
            stable_emitted=False,
            translated_text=None,
            retained_translation=track.display_translation,
        )

    def _best_match(self, observation: OcrText, candidates: set[str]) -> str | None:
        text = normalize_text(observation.text)
        best_id: str | None = None
        best_score = 0.0
        for track_id in candidates:
            track = self._tracks[track_id]
            iou = _intersection_over_union(track.bounds, observation.bounds)
            distance = _center_distance_ratio(track.bounds, observation.bounds)
            similarity = SequenceMatcher(None, track.text, text, autojunk=False).ratio()
            if not (iou >= 0.15 or distance <= 0.55):
                continue
            score = iou * 0.55 + similarity * 0.35 + max(0.0, 1.0 - distance) * 0.10
            if score > best_score:
                best_id = track_id
                best_score = score
        return best_id

    def _is_stable(self, track: TrackedText, now: float) -> bool:
        return (
            track.observations >= self.stable_observations
            and now - track.first_seen >= self.stable_seconds
        )

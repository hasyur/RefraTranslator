"""Replay the manual animated scenes through the experimental ROI pipeline.

The benchmark never starts RefraTranslator's live runtime or an LLM service. It
renders deterministic frames from tests/manual/animated_ocr_scenes.py, compares
adjacent-frame and last-accepted baselines, and optionally runs real PaddleOCR
at selected acceptance points.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import os
import statistics
import sys
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Sequence

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from game_screen_translator.ocr.contextual_roi import (
    ContextualOcrRegion,
    ContextualRoiPlan,
    ContextualRoiPlanner,
    TextAnchor,
    build_translation_context_group,
)
from game_screen_translator.ocr.dynamic_roi import (
    DynamicRoiProposal,
    FullScreenRoiDetector,
)
from game_screen_translator.ocr.paddle import PaddleOcrEngine
from game_screen_translator.ocr.roi import OcrRoi, recognize_ocr_rois
from game_screen_translator.ocr.roi_scheduler import (
    LatestFrameRoiScheduler,
    ScheduledRoiScan,
)
from game_screen_translator.ocr.text_filter import OcrTextFilter
from game_screen_translator.ocr.types import OcrText


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANUAL_SCENE_SCRIPT = PROJECT_ROOT / "tests" / "manual" / "animated_ocr_scenes.py"
FRAME_SIZE = (1600, 900)
SCENE_INDEX = {
    "typewriter": 0,
    "vertical-menu": 2,
    "horizontal-menu": 3,
    "changing-background": 4,
}
TYPEWRITER_EXPECTED = (
    "門は真夜中に開く。",
    "川岸に沿って進み、",
    "失われた鍵を探せ。",
)


@dataclass(frozen=True, slots=True)
class FrameSample:
    elapsed_s: float
    frame: np.ndarray


@dataclass(frozen=True, slots=True)
class AnchorSnapshot:
    track_id: str
    text: str
    bounds: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class ProposalStats:
    comparisons: int
    triggers: int
    fallbacks: int
    mean_coverage: float
    max_coverage: float
    reasons: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class ScanEvent:
    elapsed_s: float
    proposal_reason: str
    fallback: bool
    coverage: float
    ocr_ms: float
    observations: tuple[OcrText, ...]
    targets: tuple[OcrText, ...]
    accepted_map: tuple[AnchorSnapshot, ...]
    trigger_reason: str = "direct"


@dataclass(frozen=True, slots=True)
class SchedulerReplayStats:
    observations: int
    dispatches: int
    fallbacks: int
    median_observe_ms: float
    p95_observe_ms: float
    work_ms_per_scene_second: float
    trigger_reasons: tuple[tuple[str, int], ...]


class ManualSceneRenderer:
    """Load the standalone testbed without importing live translation code."""

    def __init__(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "refra_manual_multiframe_scenes", MANUAL_SCENE_SCRIPT
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法载入动态字幕靶场：{MANUAL_SCENE_SCRIPT}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self._app = QApplication.instance() or QApplication([])
        self._window = module.AnimatedOcrSceneWindow(fps=30)
        self._window.set_elapsed_for_test(0.0)

    def render(self, scene: str, elapsed_s: float) -> np.ndarray:
        width, height = FRAME_SIZE
        image = self._window.render_scene_to_image(
            SCENE_INDEX[scene], elapsed_s, width=width, height=height
        ).convertToFormat(QImage.Format.Format_RGB888)
        row_bytes = image.bytesPerLine()
        view = np.frombuffer(image.bits(), dtype=np.uint8).reshape(height, row_bytes)
        return view[:, : width * 3].reshape(height, width, 3).copy()


def _times(end_s: float, fps: float) -> tuple[float, ...]:
    count = math.floor(end_s * fps + 1e-9)
    values = [index / fps for index in range(count + 1)]
    if values[-1] < end_s - 1e-9:
        values.append(end_s)
    return tuple(values)


def _render_sequence(
    renderer: ManualSceneRenderer,
    scene: str,
    *,
    end_s: float,
    fps: float,
) -> tuple[FrameSample, ...]:
    return tuple(
        FrameSample(elapsed_s, renderer.render(scene, elapsed_s))
        for elapsed_s in _times(end_s, fps)
    )


def _proposal_stats(proposals: Iterable[DynamicRoiProposal]) -> ProposalStats:
    values = tuple(proposals)
    active = tuple(item for item in values if item.rois)
    reason_counts: dict[str, int] = {}
    for item in values:
        reason_counts[item.reason] = reason_counts.get(item.reason, 0) + 1
    coverages = tuple(item.coverage_fraction for item in active)
    return ProposalStats(
        comparisons=len(values),
        triggers=len(active),
        fallbacks=sum(item.fallback_full_frame for item in values),
        mean_coverage=statistics.fmean(coverages) if coverages else 0.0,
        max_coverage=max(coverages, default=0.0),
        reasons=tuple(sorted(reason_counts.items())),
    )


def compare_baselines(
    samples: Sequence[FrameSample], detector: FullScreenRoiDetector
) -> tuple[ProposalStats, ProposalStats]:
    if len(samples) < 2:
        raise ValueError("多帧比较至少需要两帧")
    adjacent = tuple(
        detector.propose(previous.frame, current.frame)
        for previous, current in zip(samples[:-1], samples[1:], strict=True)
    )
    sticky = tuple(
        detector.propose(samples[0].frame, current.frame)
        for current in samples[1:]
    )
    return _proposal_stats(adjacent), _proposal_stats(sticky)


def _normalized(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in value if character.isalnum())


def _ordered_text(observations: Sequence[OcrText | AnchorSnapshot]) -> str:
    return "".join(
        _normalized(item.text)
        for item in sorted(observations, key=lambda item: (item.bounds[1], item.bounds[0]))
    )


def _expected_score(
    expected: Sequence[str], observations: Sequence[OcrText | AnchorSnapshot]
) -> float:
    expected_text = "".join(_normalized(value) for value in expected)
    observed_text = _ordered_text(observations)
    for known_context in ("旅人", "システム", "案内人"):
        observed_text = observed_text.replace(_normalized(known_context), "")
    return SequenceMatcher(
        None, expected_text, observed_text, autojunk=False
    ).ratio()


def _contains_exact_lines(
    expected: Sequence[str], observations: Sequence[OcrText | AnchorSnapshot]
) -> bool:
    def canonical(value: str) -> str:
        return "".join(
            character
            for character in unicodedata.normalize("NFKC", value)
            if not character.isspace()
        )

    observed = {canonical(item.text) for item in observations}
    return all(canonical(value) in observed for value in expected)


def _anchors(
    observations: Sequence[OcrText], *, start_index: int = 1
) -> tuple[AnchorSnapshot, ...]:
    return tuple(
        AnchorSnapshot(f"track-{index:04d}", item.text, item.bounds)
        for index, item in enumerate(
            sorted(observations, key=lambda item: (item.bounds[1], item.bounds[0])),
            start=start_index,
        )
    )


def _intersects_roi(bounds: tuple[int, int, int, int], roi: OcrRoi) -> bool:
    left, top, width, height = roi
    right, bottom = left + width, top + height
    return not (
        bounds[2] <= left
        or right <= bounds[0]
        or bounds[3] <= top
        or bottom <= bounds[1]
    )


def _update_anchors(
    previous: Sequence[AnchorSnapshot],
    observations: Sequence[OcrText],
    targets: Sequence[OcrText],
    plan: ContextualRoiPlan,
    *,
    next_track_index: int,
) -> tuple[tuple[AnchorSnapshot, ...], int]:
    affected_ids = {
        track_id
        for region in plan.regions
        for track_id in region.affected_track_ids
    }
    retained = [] if plan.fallback_full_frame else [
        anchor for anchor in previous if anchor.track_id not in affected_ids
    ]
    updated_by_id = {anchor.track_id: anchor for anchor in retained}
    reusable = list(previous)
    target_keys = {(item.text, item.bounds) for item in targets}
    for observation in sorted(
        observations, key=lambda item: (item.bounds[1], item.bounds[0])
    ):
        observation_roi = (
            observation.bounds[0],
            observation.bounds[1],
            observation.bounds[2] - observation.bounds[0],
            observation.bounds[3] - observation.bounds[1],
        )
        match = next(
            (
                anchor
                for anchor in reusable
                if _normalized(anchor.text) == _normalized(observation.text)
                and _intersects_roi(anchor.bounds, observation_roi)
            ),
            None,
        )
        if match is not None:
            reusable.remove(match)
            track_id = match.track_id
        elif not plan.fallback_full_frame and (
            observation.text,
            observation.bounds,
        ) not in target_keys:
            # A padded OCR crop may contain stable neighboring rows. They are
            # useful as LLM context, but must not replace or duplicate tracks
            # outside affected_track_ids.
            continue
        else:
            track_id = f"track-{next_track_index:04d}"
            next_track_index += 1
        updated_by_id[track_id] = AnchorSnapshot(
            track_id, observation.text, observation.bounds
        )
    return (
        tuple(
            sorted(
                updated_by_id.values(),
                key=lambda item: (item.bounds[1], item.bounds[0]),
            )
        ),
        next_track_index,
    )


def _full_scan(
    engine: PaddleOcrEngine,
    text_filter: OcrTextFilter,
    frame: np.ndarray,
) -> tuple[tuple[OcrText, ...], float]:
    started = time.perf_counter()
    observations = text_filter.apply(engine.recognize_frame(frame)).accepted
    return tuple(observations), (time.perf_counter() - started) * 1000.0


def _roi_scan(
    engine: PaddleOcrEngine,
    text_filter: OcrTextFilter,
    frame: np.ndarray,
    plan: ContextualRoiPlan,
    anchors: Sequence[TextAnchor],
) -> tuple[tuple[OcrText, ...], tuple[OcrText, ...], float]:
    started = time.perf_counter()
    observations = text_filter.apply(
        recognize_ocr_rois(
            engine,
            frame,
            tuple(region.roi for region in plan.regions),
            edge_margin=12,
        )
    ).accepted
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    groups = tuple(
        build_translation_context_group(region, observations, anchors)
        for region in plan.regions
    )
    targets = tuple(item for group in groups for item in group.targets)
    return tuple(observations), targets, elapsed_ms


def _scheduler(
    detector: FullScreenRoiDetector,
    *,
    scan_interval_s: float,
    settle_interval_s: float,
    max_coalesce_s: float,
) -> LatestFrameRoiScheduler:
    return LatestFrameRoiScheduler(
        detector,
        min_ocr_interval_s=scan_interval_s,
        settle_interval_s=settle_interval_s,
        max_coalesce_s=max_coalesce_s,
    )


def replay_scheduler(
    samples: Sequence[FrameSample],
    *,
    detector: FullScreenRoiDetector,
    scan_interval_s: float,
    settle_interval_s: float,
    max_coalesce_s: float,
) -> SchedulerReplayStats:
    """Measure the two-baseline scheduler without invoking OCR."""
    if len(samples) < 2:
        raise ValueError("scheduler 回放至少需要两帧")
    scheduler = _scheduler(
        detector,
        scan_interval_s=scan_interval_s,
        settle_interval_s=settle_interval_s,
        max_coalesce_s=max_coalesce_s,
    )
    scheduler.prime(samples[0].frame, samples[0].elapsed_s)
    observe_ms: list[float] = []
    jobs: list[ScheduledRoiScan] = []
    for sample in samples[1:]:
        started = time.perf_counter()
        job = scheduler.observe(sample.frame, sample.elapsed_s)
        observe_ms.append((time.perf_counter() - started) * 1000.0)
        if job is None:
            continue
        jobs.append(job)
        follow_up = scheduler.complete(
            job, accepted=True, completed_at_s=sample.elapsed_s
        )
        if follow_up is not None:
            raise AssertionError("同步 detector 回放不应产生立即 follow-up")

    ordered_ms = sorted(observe_ms)
    p95_index = max(0, math.ceil(len(ordered_ms) * 0.95) - 1)
    duration_s = samples[-1].elapsed_s - samples[0].elapsed_s
    reasons: dict[str, int] = {}
    for job in jobs:
        reasons[job.trigger_reason] = reasons.get(job.trigger_reason, 0) + 1
    return SchedulerReplayStats(
        len(observe_ms),
        len(jobs),
        sum(job.proposal.fallback_full_frame for job in jobs),
        statistics.median(ordered_ms),
        ordered_ms[p95_index],
        sum(observe_ms) / duration_s if duration_s > 0 else 0.0,
        tuple(sorted(reasons.items())),
    )


def run_typewriter_ocr(
    samples: Sequence[FrameSample],
    *,
    detector: FullScreenRoiDetector,
    planner: ContextualRoiPlanner,
    engine: PaddleOcrEngine,
    text_filter: OcrTextFilter,
    scan_interval_s: float,
    settle_interval_s: float = 0.18,
    max_coalesce_s: float = 1.0 / 3.0,
) -> tuple[tuple[ScanEvent, ...], tuple[AnchorSnapshot, ...], float]:
    initial, initial_ms = _full_scan(engine, text_filter, samples[0].frame)
    anchors: tuple[AnchorSnapshot, ...] = _anchors(initial)
    next_track_index = len(anchors) + 1
    scheduler = _scheduler(
        detector,
        scan_interval_s=scan_interval_s,
        settle_interval_s=settle_interval_s,
        max_coalesce_s=max_coalesce_s,
    )
    scheduler.prime(samples[0].frame, samples[0].elapsed_s)
    events: list[ScanEvent] = []

    def accept(job: ScheduledRoiScan) -> None:
        nonlocal anchors, next_track_index
        plan = planner.plan_proposal(job.proposal, anchors, frame_size=FRAME_SIZE)
        observations, targets, ocr_ms = _roi_scan(
            engine, text_filter, job.frame, plan, anchors
        )
        anchors, next_track_index = _update_anchors(
            anchors,
            observations,
            targets,
            plan,
            next_track_index=next_track_index,
        )
        events.append(
            ScanEvent(
                job.observed_at_s,
                job.proposal.reason,
                plan.fallback_full_frame,
                plan.coverage_fraction,
                ocr_ms,
                observations,
                targets,
                anchors,
                job.trigger_reason,
            )
        )
        follow_up = scheduler.complete(
            job,
            accepted=True,
            completed_at_s=job.dispatched_at_s,
            target_count=len(targets),
        )
        if follow_up is not None:
            raise AssertionError("同步 OCR 回放不应产生立即 follow-up")

    for sample in samples[1:]:
        job = scheduler.observe(sample.frame, sample.elapsed_s)
        if job is not None:
            accept(job)

    if scheduler.has_pending:
        final_job = scheduler.poll(samples[-1].elapsed_s, force=True)
        if final_job is not None:
            accept(final_job)
    return tuple(events), anchors, initial_ms


def run_background_ocr(
    samples: Sequence[FrameSample],
    *,
    detector: FullScreenRoiDetector,
    planner: ContextualRoiPlanner,
    engine: PaddleOcrEngine,
    text_filter: OcrTextFilter,
    scan_interval_s: float,
    settle_interval_s: float = 0.18,
    max_coalesce_s: float = 1.0 / 3.0,
) -> tuple[tuple[ScanEvent, ...], tuple[AnchorSnapshot, ...], float]:
    initial, initial_ms = _full_scan(engine, text_filter, samples[0].frame)
    anchors: tuple[AnchorSnapshot, ...] = _anchors(initial)
    next_track_index = len(anchors) + 1
    scheduler = _scheduler(
        detector,
        scan_interval_s=scan_interval_s,
        settle_interval_s=settle_interval_s,
        max_coalesce_s=max_coalesce_s,
    )
    scheduler.prime(samples[0].frame, samples[0].elapsed_s)
    events: list[ScanEvent] = []
    for sample in samples[1:]:
        job = scheduler.observe(sample.frame, sample.elapsed_s)
        if job is None:
            continue
        plan = planner.plan_proposal(job.proposal, anchors, frame_size=FRAME_SIZE)
        observations, targets, ocr_ms = _roi_scan(
            engine, text_filter, job.frame, plan, anchors
        )
        anchors, next_track_index = _update_anchors(
            anchors,
            observations,
            targets,
            plan,
            next_track_index=next_track_index,
        )
        events.append(
            ScanEvent(
                job.observed_at_s,
                job.proposal.reason,
                plan.fallback_full_frame,
                plan.coverage_fraction,
                ocr_ms,
                observations,
                targets,
                anchors,
                job.trigger_reason,
            )
        )
        follow_up = scheduler.complete(
            job,
            accepted=True,
            completed_at_s=job.dispatched_at_s,
            target_count=len(targets),
        )
        if follow_up is not None:
            raise AssertionError("同步 OCR 回放不应产生立即 follow-up")
    return tuple(events), anchors, initial_ms


def run_scroll_rebuild(
    samples: Sequence[FrameSample],
    *,
    detector: FullScreenRoiDetector,
    planner: ContextualRoiPlanner,
    engine: PaddleOcrEngine,
    text_filter: OcrTextFilter,
) -> tuple[ScanEvent, tuple[AnchorSnapshot, ...], float]:
    initial, initial_ms = _full_scan(engine, text_filter, samples[0].frame)
    anchors: tuple[AnchorSnapshot, ...] = _anchors(initial)
    endpoint = min(samples, key=lambda item: abs(item.elapsed_s - 3.2))
    proposal = detector.propose(samples[0].frame, endpoint.frame)
    if not proposal.rois:
        raise RuntimeError("滚动终点没有产生 OCR 提议")
    plan = planner.plan_proposal(proposal, anchors, frame_size=FRAME_SIZE)
    observations, targets, ocr_ms = _roi_scan(
        engine, text_filter, endpoint.frame, plan, anchors
    )
    rebuilt, _ = _update_anchors(
        anchors,
        observations,
        targets,
        plan,
        next_track_index=len(anchors) + 1,
    )
    return (
        ScanEvent(
            endpoint.elapsed_s,
            proposal.reason,
            plan.fallback_full_frame,
            plan.coverage_fraction,
            ocr_ms,
            observations,
            targets,
            rebuilt,
        ),
        anchors,
        initial_ms,
    )


def _format_stats(label: str, stats: ProposalStats) -> str:
    return (
        f"  {label:<17} trigger={stats.triggers:>2}/{stats.comparisons:<2} "
        f"fallback={stats.fallbacks:>2}/{stats.comparisons:<2} "
        f"mean/max coverage={stats.mean_coverage * 100:5.1f}%/"
        f"{stats.max_coverage * 100:5.1f}% reasons={dict(stats.reasons)}"
    )


def _print_events(events: Sequence[ScanEvent]) -> None:
    for event in events:
        print(
            f"    t={event.elapsed_s:4.2f}s trigger={event.trigger_reason:<12} "
            f"reason={event.proposal_reason:<24} "
            f"fallback={str(event.fallback):<5} coverage={event.coverage * 100:5.1f}% "
            f"ocr={event.ocr_ms:6.1f}ms targets={[item.text for item in event.targets]} "
            f"map={[item.text for item in event.accepted_map]}"
        )


def _latency_summary(events: Sequence[ScanEvent]) -> str:
    if not events:
        return "-"
    values = sorted(event.ocr_ms for event in events)
    median = statistics.median(values)
    p95 = values[max(0, math.ceil(len(values) * 0.95) - 1)]
    return f"median={median:.1f}ms p95={p95:.1f}ms"


def _format_scheduler_stats(stats: SchedulerReplayStats) -> str:
    return (
        f"observe={stats.observations}, OCR jobs={stats.dispatches}, "
        f"fallback={stats.fallbacks}, observe median/p95="
        f"{stats.median_observe_ms:.2f}/{stats.p95_observe_ms:.2f}ms, "
        f"detector+scheduler work={stats.work_ms_per_scene_second:.1f}ms/s, "
        f"triggers={dict(stats.trigger_reasons)}"
    )


def _parse_hz_list(value: str) -> tuple[float, ...]:
    try:
        frequencies = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("频率必须是逗号分隔的数字") from exc
    if not frequencies or any(
        not math.isfinite(item) or item <= 0.0 for item in frequencies
    ):
        raise argparse.ArgumentTypeError("所有频率都必须大于 0")
    return frequencies


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("all", *SCENE_INDEX),
        default="all",
    )
    parser.add_argument("--detector-fps", type=float, default=6.0)
    parser.add_argument("--ocr-interval", type=float, default=1.0 / 3.0)
    parser.add_argument("--settle-interval", type=float, default=0.18)
    parser.add_argument("--max-coalesce", type=float, default=1.0 / 3.0)
    parser.add_argument(
        "--compare-ocr-hz",
        type=_parse_hz_list,
        metavar="HZ,HZ,...",
        help="repeat typewriter/background OCR with several rate caps",
    )
    parser.add_argument("--paddle-device", default="gpu:0")
    parser.add_argument("--paddle-language", default="japan")
    parser.add_argument("--paddle-max-side", type=int, default=1280)
    parser.add_argument(
        "--detector-only",
        action="store_true",
        help="skip PaddleOCR and report only change/ROI behavior",
    )
    parser.add_argument("--show-events", action="store_true")
    return parser


def _run_frequency_comparison(
    frequencies: Sequence[float],
    *,
    sequences: dict[str, tuple[FrameSample, ...]],
    detector: FullScreenRoiDetector,
    planner: ContextualRoiPlanner,
    engine: PaddleOcrEngine,
    text_filter: OcrTextFilter,
    settle_interval_s: float,
    max_coalesce_s: float,
) -> bool:
    print()
    print(
        "OCR base-rate comparison with empty-target backoff "
        f"(detector={1 / (sequences[next(iter(sequences))][1].elapsed_s - sequences[next(iter(sequences))][0].elapsed_s):.1f}Hz, "
        f"settle={settle_interval_s * 1000:.0f}ms, "
        f"max-coalesce={max_coalesce_s * 1000:.0f}ms)"
    )
    print(
        "  base   type scans/targets  exact complete  type OCR work  "
        "background scans/false  background OCR work"
    )
    all_ok = True
    for frequency in frequencies:
        interval_s = 1.0 / frequency
        type_summary = "-"
        type_work = "-"
        if "typewriter" in sequences:
            events, final_anchors, _ = run_typewriter_ocr(
                sequences["typewriter"],
                detector=detector,
                planner=planner,
                engine=engine,
                text_filter=text_filter,
                scan_interval_s=interval_s,
                settle_interval_s=settle_interval_s,
                max_coalesce_s=max_coalesce_s,
            )
            complete_event = next(
                (
                    event
                    for event in events
                    if _contains_exact_lines(
                        TYPEWRITER_EXPECTED, event.accepted_map
                    )
                ),
                None,
            )
            exact = _contains_exact_lines(TYPEWRITER_EXPECTED, final_anchors)
            targets = sum(bool(event.targets) for event in events)
            duration = sequences["typewriter"][-1].elapsed_s
            type_summary = (
                f"{len(events):>2}/{targets:<2}      "
                f"{str(exact):<5} "
                f"{complete_event.elapsed_s if complete_event else '-':>4}"
            )
            type_work = f"{sum(item.ocr_ms for item in events) / duration:6.1f}ms/s"
            all_ok = all_ok and exact and complete_event is not None

        background_summary = "-"
        background_work = "-"
        if "changing-background" in sequences:
            events, _, _ = run_background_ocr(
                sequences["changing-background"],
                detector=detector,
                planner=planner,
                engine=engine,
                text_filter=text_filter,
                scan_interval_s=interval_s,
                settle_interval_s=settle_interval_s,
                max_coalesce_s=max_coalesce_s,
            )
            false_target_scans = sum(bool(event.targets) for event in events)
            duration = sequences["changing-background"][-1].elapsed_s
            background_summary = f"{len(events):>2}/{false_target_scans:<2}"
            background_work = (
                f"{sum(item.ocr_ms for item in events) / duration:6.1f}ms/s"
            )
            all_ok = all_ok and false_target_scans == 0

        print(
            f"  {frequency:>4.1f}Hz {type_summary:<27} {type_work:<15} "
            f"{background_summary:<22} {background_work}"
        )
    return all_ok


def main() -> int:
    args = _build_parser().parse_args()
    if args.detector_fps <= 0.0:
        raise SystemExit("--detector-fps 必须大于 0")
    if args.ocr_interval <= 0.0:
        raise SystemExit("--ocr-interval 必须大于 0")
    if args.settle_interval < 0.0:
        raise SystemExit("--settle-interval 不能小于 0")
    if args.max_coalesce < 0.0:
        raise SystemExit("--max-coalesce 不能小于 0")

    renderer = ManualSceneRenderer()
    detector = FullScreenRoiDetector()
    planner = ContextualRoiPlanner()
    selected = tuple(
        scene
        for scene in SCENE_INDEX
        if args.scenario == "all" or args.scenario == scene
    )
    durations = {
        "typewriter": 4.8,
        "vertical-menu": 6.0,
        "horizontal-menu": 7.0,
        "changing-background": 6.0,
    }
    sequences = {
        scene: _render_sequence(
            renderer,
            scene,
            end_s=durations[scene],
            fps=args.detector_fps,
        )
        for scene in selected
    }

    print("Detector replay (adjacent frame vs initial sticky baseline)")
    detector_results: dict[str, tuple[ProposalStats, ProposalStats]] = {}
    for scene, samples in sequences.items():
        adjacent, sticky = compare_baselines(samples, detector)
        detector_results[scene] = adjacent, sticky
        print(scene)
        print(_format_stats("adjacent", adjacent))
        print(_format_stats("sticky", sticky))

    print()
    print(
        f"Latest-frame scheduler dry replay (detector={args.detector_fps:g}Hz, "
        f"OCR cap={1 / args.ocr_interval:.2f}Hz, no OCR-result feedback)"
    )
    for scene, samples in sequences.items():
        stats = replay_scheduler(
            samples,
            detector=detector,
            scan_interval_s=args.ocr_interval,
            settle_interval_s=args.settle_interval,
            max_coalesce_s=args.max_coalesce,
        )
        print(f"  {scene:<20} {_format_scheduler_stats(stats)}")

    if args.detector_only:
        return 0

    print()
    print("Initializing PaddleOCR; model startup is outside scan timings...")
    engine = PaddleOcrEngine(
        language=args.paddle_language,
        device=args.paddle_device,
        detection_max_side=args.paddle_max_side,
    )
    text_filter = OcrTextFilter("japan", translate_han_only=True)
    all_ok = True

    if "typewriter" in sequences:
        events, final_anchors, initial_ms = run_typewriter_ocr(
            sequences["typewriter"],
            detector=detector,
            planner=planner,
            engine=engine,
            text_filter=text_filter,
            scan_interval_s=args.ocr_interval,
            settle_interval_s=args.settle_interval,
            max_coalesce_s=args.max_coalesce,
        )
        score = _expected_score(TYPEWRITER_EXPECTED, final_anchors)
        complete_event = next(
            (
                event
                for event in events
                if _contains_exact_lines(TYPEWRITER_EXPECTED, event.accepted_map)
            ),
            None,
        )
        exact_final = _contains_exact_lines(TYPEWRITER_EXPECTED, final_anchors)
        typewriter_ok = score >= 0.999 and exact_final and complete_event is not None
        all_ok = all_ok and typewriter_ok
        print()
        print("typewriter accepted-baseline OCR")
        print(
            f"  initial full OCR={initial_ms:.1f}ms, recurring scans={len(events)}, "
            f"{_latency_summary(events)}, final score={score * 100:.1f}%, "
            f"exact_lines={exact_final}, "
            f"complete_at={complete_event.elapsed_s if complete_event else '-'} "
            f"result={'PASS' if typewriter_ok else 'CHECK'}"
        )
        print("  final text:", [anchor.text for anchor in final_anchors])
        if args.show_events:
            _print_events(events)

    for scene in ("vertical-menu", "horizontal-menu"):
        if scene not in sequences:
            continue
        _, sticky = detector_results[scene]
        rebuild, initial_anchors, initial_ms = run_scroll_rebuild(
            sequences[scene],
            detector=detector,
            planner=planner,
            engine=engine,
            text_filter=text_filter,
        )
        scroll_ok = (
            sticky.fallbacks > 0
            and rebuild.fallback
            and bool(rebuild.accepted_map)
        )
        all_ok = all_ok and scroll_ok
        print()
        print(f"{scene} fallback")
        print(
            f"  sticky fallback={sticky.fallbacks}/{sticky.comparisons}, "
            f"max coverage={sticky.max_coverage * 100:.1f}% "
            f"result={'PASS' if scroll_ok else 'CHECK'}"
        )
        print(
            f"  initial map={len(initial_anchors)} texts ({initial_ms:.1f}ms), "
            f"endpoint t={rebuild.elapsed_s:.2f}s rebuild="
            f"{len(rebuild.accepted_map)} texts ({rebuild.ocr_ms:.1f}ms), "
            f"targets={len(rebuild.targets)}"
        )
        if args.show_events:
            _print_events((rebuild,))

    if "changing-background" in sequences:
        events, final_anchors, initial_ms = run_background_ocr(
            sequences["changing-background"],
            detector=detector,
            planner=planner,
            engine=engine,
            text_filter=text_filter,
            scan_interval_s=args.ocr_interval,
            settle_interval_s=args.settle_interval,
            max_coalesce_s=args.max_coalesce,
        )
        false_target_events = tuple(event for event in events if event.targets)
        false_targets = tuple(
            target for event in false_target_events for target in event.targets
        )
        translation_safe = not false_targets
        all_ok = all_ok and translation_safe
        adjacent, _ = detector_results["changing-background"]
        heatmap_warning = adjacent.triggers == adjacent.comparisons
        print()
        print("changing-background false-trigger audit")
        print(
            f"  initial full OCR={initial_ms:.1f}ms, heatmap triggers="
            f"{adjacent.triggers}/{adjacent.comparisons}, OCR scans={len(events)}, "
            f"{_latency_summary(events)}, false target scans={len(false_target_events)}, "
            f"false targets={len(false_targets)}"
        )
        print(
            f"  translation target suppression={'PASS' if translation_safe else 'CHECK'}; "
            f"heatmap load={'WARN: every frame triggered' if heatmap_warning else 'PASS'}"
        )
        print("  final text:", [anchor.text for anchor in final_anchors])
        if args.show_events:
            _print_events(events)

    if args.compare_ocr_hz:
        all_ok = _run_frequency_comparison(
            args.compare_ocr_hz,
            sequences=sequences,
            detector=detector,
            planner=planner,
            engine=engine,
            text_filter=text_filter,
            settle_interval_s=args.settle_interval,
            max_coalesce_s=args.max_coalesce,
        ) and all_ok

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Benchmark PaddleOCR with full-screen change-driven local ROIs.

The experiment is deliberately separate from the live runtime. Screen captures
are kept in memory and recognized text is only printed with --show-text.
"""

from __future__ import annotations

import argparse
import math
import statistics
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from game_screen_translator.capture.dxcam_capture import DxcamCapture
from game_screen_translator.ocr.dynamic_roi import (
    DynamicRoiProposal,
    FullScreenRoiDetector,
)
from game_screen_translator.ocr.paddle import PaddleOcrEngine
from game_screen_translator.ocr.roi import OcrRoi, recognize_ocr_rois
from game_screen_translator.ocr.types import OcrText


@dataclass(frozen=True, slots=True)
class FramePair:
    baseline: np.ndarray
    current: np.ndarray
    expected_changed: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TimedResult:
    name: str
    samples_ms: tuple[float, ...]
    observations: tuple[OcrText, ...]

    @property
    def median_ms(self) -> float:
        return statistics.median(self.samples_ms)

    @property
    def p95_ms(self) -> float:
        ordered = sorted(self.samples_ms)
        return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _parse_roi(value: str) -> OcrRoi:
    try:
        parts = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("区域必须是四个整数：left,top,width,height") from exc
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("区域必须是四个整数：left,top,width,height")
    return parts


def _font(size: int, *, cjk: bool = False) -> ImageFont.FreeTypeFont:
    names = (
        ("YuGothR.ttc", "msyh.ttc", "segoeui.ttf")
        if cjk
        else ("segoeui.ttf", "msyh.ttc")
    )
    for name in names:
        path = Path("C:/Windows/Fonts") / name
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    raise RuntimeError("找不到用于合成 OCR 基准图的 Windows 字体")


def _synthetic_pair() -> FramePair:
    width, height = 1920, 1080
    y = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    background = np.empty((height, width, 3), dtype=np.uint8)
    background[..., 0] = 18 + y * 14
    background[..., 1] = 24 + y * 10
    background[..., 2] = 38 + y * 18
    base_image = Image.fromarray(background, mode="RGB")
    draw = ImageDraw.Draw(base_image)
    draw.rounded_rectangle((80, 60, 760, 340), radius=22, fill=(26, 32, 46))
    draw.text((120, 100), "MISSION", font=_font(42), fill=(236, 240, 248))
    draw.text((120, 190), "古い街道を調査する", font=_font(38, cjk=True), fill=(214, 224, 239))
    draw.rounded_rectangle((1260, 90, 1810, 410), radius=18, fill=(31, 35, 47))
    draw.text((1320, 140), "INVENTORY", font=_font(34), fill=(220, 225, 235))
    draw.text((1320, 240), "回復薬  3", font=_font(32, cjk=True), fill=(198, 210, 228))
    draw.rounded_rectangle((150, 700, 1770, 1010), radius=28, fill=(28, 31, 41))
    draw.text((230, 720), "旅人", font=_font(30, cjk=True), fill=(164, 178, 201))

    baseline_image = base_image.copy()
    current_image = base_image.copy()
    before_text = "門は真夜中に"
    current_text = "門は真夜中に開く。"
    ImageDraw.Draw(baseline_image).text(
        (230, 820),
        before_text,
        font=_font(48, cjk=True),
        fill=(244, 244, 240),
        stroke_width=2,
        stroke_fill=(5, 5, 8),
    )
    ImageDraw.Draw(current_image).text(
        (230, 820),
        current_text,
        font=_font(48, cjk=True),
        fill=(244, 244, 240),
        stroke_width=2,
        stroke_fill=(5, 5, 8),
    )
    return FramePair(
        np.asarray(baseline_image),
        np.asarray(current_image),
        (current_text,),
    )


def _load_pair(before: Path, after: Path) -> FramePair:
    with Image.open(before) as image:
        baseline = np.asarray(image.convert("RGB"))
    with Image.open(after) as image:
        current = np.asarray(image.convert("RGB"))
    return FramePair(baseline, current)


def _capture_pair(
    *, monitor: int, capture_region: OcrRoi, gap_seconds: float
) -> FramePair:
    with DxcamCapture(
        monitor_index=monitor,
        region_spec=capture_region,
        target_fps=30,
    ) as capture:
        deadline = time.monotonic() + 4.0
        baseline = None
        while baseline is None and time.monotonic() < deadline:
            frame = capture.latest_frame()
            if frame is not None:
                baseline = frame.copy()
            else:
                time.sleep(0.02)
        if baseline is None:
            raise RuntimeError("4 秒内没有捕获到基准帧")
        time.sleep(gap_seconds)
        current = capture.latest_frame()
        if current is None:
            raise RuntimeError("没有捕获到当前帧")
        return FramePair(baseline, current.copy())


def _benchmark(
    cases: Sequence[tuple[str, Callable[[], tuple[OcrText, ...]]]],
    *,
    warmups: int,
    repeats: int,
) -> tuple[TimedResult, ...]:
    latest: dict[str, tuple[OcrText, ...]] = {}
    samples: dict[str, list[float]] = {name: [] for name, _ in cases}
    for _, action in cases:
        for _ in range(warmups):
            action()
    for round_index in range(repeats):
        order = cases if round_index % 2 == 0 else tuple(reversed(cases))
        for name, action in order:
            started = time.perf_counter()
            latest[name] = tuple(action())
            samples[name].append((time.perf_counter() - started) * 1000.0)
    return tuple(
        TimedResult(name, tuple(samples[name]), latest[name]) for name, _ in cases
    )


def _normalized(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in value if character.isalnum())


def _ordered_text(observations: Sequence[OcrText]) -> str:
    ordered = sorted(observations, key=lambda item: (item.bounds[1], item.bounds[0]))
    return "".join(_normalized(item.text) for item in ordered)


def _inside_any_roi(
    observations: Sequence[OcrText], rois: Sequence[OcrRoi]
) -> tuple[OcrText, ...]:
    selected: list[OcrText] = []
    for item in observations:
        center_x = (item.bounds[0] + item.bounds[2]) / 2
        center_y = (item.bounds[1] + item.bounds[3]) / 2
        if any(
            left <= center_x <= left + width and top <= center_y <= top + height
            for left, top, width, height in rois
        ):
            selected.append(item)
    return tuple(selected)


def _fully_inside_any_roi(item: OcrText, rois: Sequence[OcrRoi]) -> bool:
    item_left, item_top, item_right, item_bottom = item.bounds
    return any(
        left <= item_left
        and top <= item_top
        and item_right <= left + width
        and item_bottom <= top + height
        for left, top, width, height in rois
    )


def _observation_pixels_changed(item: OcrText, pair: FramePair) -> bool:
    frame_height, frame_width = pair.current.shape[:2]
    left, top, right, bottom = item.bounds
    left, top = max(0, left), max(0, top)
    right, bottom = min(frame_width, right), min(frame_height, bottom)
    if right <= left or bottom <= top:
        return False
    before = pair.baseline[top:bottom, left:right, :3].astype(np.int16)
    after = pair.current[top:bottom, left:right, :3].astype(np.int16)
    difference = np.max(np.abs(after - before), axis=2)
    return float(np.mean(difference >= 14)) >= 0.01


def _expected_similarity(expected: Sequence[str], observed: Sequence[OcrText]) -> str:
    if not expected:
        return "-"
    expected_text = "".join(_normalized(text) for text in expected)
    return (
        f"{SequenceMatcher(None, expected_text, _ordered_text(observed), autojunk=False).ratio() * 100:.1f}%"
    )


def _proposal_timing(
    detector: FullScreenRoiDetector, pair: FramePair, repeats: int = 50
) -> tuple[DynamicRoiProposal, float, float]:
    samples: list[float] = []
    proposal = detector.propose(pair.baseline, pair.current)
    for _ in range(repeats):
        started = time.perf_counter()
        proposal = detector.propose(pair.baseline, pair.current)
        samples.append((time.perf_counter() - started) * 1000.0)
    ordered = sorted(samples)
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
    return proposal, statistics.median(samples), p95


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--synthetic", action="store_true", help="使用内存打字机测试卡（默认）")
    source.add_argument("--capture", action="store_true", help="临时捕获两帧，不写入磁盘")
    source.add_argument("--before", type=Path, help="变化前图片；同时需要 --after")
    parser.add_argument("--after", type=Path, help="变化后图片")
    parser.add_argument("--monitor", type=int, default=0)
    parser.add_argument("--capture-region", type=_parse_roi, default=(0, 0, 0, 0))
    parser.add_argument("--capture-gap", type=float, default=0.75)
    parser.add_argument("--paddle-language", default="japan")
    parser.add_argument("--paddle-device", default="gpu:0")
    parser.add_argument("--paddle-max-side", type=int, default=1280)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=8)
    parser.add_argument("--show-text", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.capture_gap < 0:
        raise SystemExit("--capture-gap 不能为负数")
    if args.warmups < 0 or args.repeats < 1:
        raise SystemExit("--warmups 必须 >= 0，--repeats 必须 >= 1")
    if (args.before is None) != (args.after is None):
        raise SystemExit("--before 和 --after 必须同时提供")

    if args.capture:
        pair = _capture_pair(
            monitor=args.monitor,
            capture_region=args.capture_region,
            gap_seconds=args.capture_gap,
        )
        source_name = "temporary display pair"
    elif args.before is not None:
        pair = _load_pair(args.before, args.after)
        source_name = f"{args.before} -> {args.after}"
    else:
        pair = _synthetic_pair()
        source_name = "synthetic typewriter pair"

    detector = FullScreenRoiDetector()
    proposal, proposal_median, proposal_p95 = _proposal_timing(detector, pair)
    frame_height, frame_width = pair.current.shape[:2]
    print(f"Source: {source_name}; frame={frame_width}x{frame_height}")
    print(
        f"ROI proposal: reason={proposal.reason}; regions={len(proposal.rois)}; "
        f"changed={proposal.changed_fraction * 100:.2f}%; "
        f"coverage={proposal.coverage_fraction * 100:.2f}%; "
        f"median={proposal_median:.2f} ms; p95={proposal_p95:.2f} ms"
    )
    for index, roi in enumerate(proposal.rois, start=1):
        print(f"  ROI {index}: {roi}")

    print("Initializing PaddleOCR (model startup is excluded from timings)...")
    paddle = PaddleOcrEngine(
        language=args.paddle_language,
        device=args.paddle_device,
        detection_max_side=args.paddle_max_side,
    )

    def dynamic_action() -> tuple[OcrText, ...]:
        current_plan = detector.propose(pair.baseline, pair.current)
        return recognize_ocr_rois(
            paddle, pair.current, current_plan.rois, edge_margin=12
        )

    results = _benchmark(
        (
            ("Paddle full", lambda: paddle.recognize_frame(pair.current)),
            ("Paddle dynamic ROI", dynamic_action),
        ),
        warmups=args.warmups,
        repeats=args.repeats,
    )
    print()
    print("case                 median     p95     min     max  boxes  expected")
    print("-------------------  -------  ------  ------  ------  -----  --------")
    for result in results:
        expected_observations = (
            _inside_any_roi(result.observations, proposal.rois)
            if result.name == "Paddle full"
            else result.observations
        )
        print(
            f"{result.name:<19}  {result.median_ms:7.1f}  {result.p95_ms:6.1f}  "
            f"{min(result.samples_ms):6.1f}  {max(result.samples_ms):6.1f}  "
            f"{len(result.observations):5d}  "
            f"{_expected_similarity(pair.expected_changed, expected_observations):>8}"
        )

    full, dynamic = results
    full_inside = _inside_any_roi(full.observations, proposal.rois)
    consistency = SequenceMatcher(
        None,
        _ordered_text(full_inside),
        _ordered_text(dynamic.observations),
        autojunk=False,
    ).ratio()
    changed_full = tuple(
        item for item in full.observations if _observation_pixels_changed(item, pair)
    )
    contained_changed = sum(
        1 for item in changed_full if _fully_inside_any_roi(item, proposal.rois)
    )
    containment = contained_changed / len(changed_full) if changed_full else 1.0
    print(
        f"Dynamic ROI speedup: {full.median_ms / max(dynamic.median_ms, 0.001):.2f}x; "
        f"ROI/full OCR output similarity: {consistency * 100:.1f}%"
    )
    print(
        f"Changed full-OCR boxes fully contained by ROIs: "
        f"{contained_changed}/{len(changed_full)} ({containment * 100:.1f}%); "
        "this is a proposal recall proxy, not ground truth accuracy"
    )

    if args.show_text:
        for result in results:
            print(f"\n[{result.name}]")
            for item in sorted(
                result.observations, key=lambda value: (value.bounds[1], value.bounds[0])
            ):
                print(f"  {item.bounds}: {item.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

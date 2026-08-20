"""Exercise contextual dynamic ROI planning on generated game-like frame pairs."""

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

from game_screen_translator.ocr.contextual_roi import (
    ContextualRoiPlanner,
    TextAnchor,
    build_translation_context_group,
)
from game_screen_translator.ocr.dynamic_roi import FullScreenRoiDetector
from game_screen_translator.ocr.paddle import PaddleOcrEngine
from game_screen_translator.ocr.roi import recognize_ocr_rois
from game_screen_translator.ocr.text_filter import OcrTextFilter
from game_screen_translator.ocr.types import OcrText


@dataclass(frozen=True, slots=True)
class SyntheticScenario:
    name: str
    description: str
    baseline: np.ndarray
    current: np.ndarray
    expected_targets: tuple[str, ...] | None
    expected_context: tuple[str, ...] = ()
    expected_fallback: bool | None = False


@dataclass(frozen=True, slots=True)
class AnchorSnapshot:
    track_id: str
    text: str
    bounds: tuple[int, int, int, int]


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


def _base_image(*, dialogue: bool = True) -> Image.Image:
    width, height = 1920, 1080
    y = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    background = np.empty((height, width, 3), dtype=np.uint8)
    background[..., 0] = 17 + y * 18
    background[..., 1] = 23 + y * 13
    background[..., 2] = 36 + y * 21
    image = Image.fromarray(background, mode="RGB")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((75, 55, 620, 250), radius=20, fill=(25, 31, 45))
    draw.text((115, 95), "MISSION", font=_font(34), fill=(225, 232, 243))
    draw.text((115, 165), "遺跡を調査する", font=_font(30, cjk=True), fill=(185, 201, 222))
    if dialogue:
        draw.rounded_rectangle((140, 680, 1780, 1015), radius=28, fill=(27, 30, 40))
    return image


def _draw_dialogue(
    image: Image.Image,
    *,
    speaker: str = "旅人",
    lines: Sequence[tuple[str, int, tuple[int, int, int]]] = (),
) -> None:
    draw = ImageDraw.Draw(image)
    draw.text((220, 715), speaker, font=_font(30, cjk=True), fill=(157, 176, 204))
    for text, y, color in lines:
        draw.text(
            (220, y),
            text,
            font=_font(46, cjk=True),
            fill=color,
            stroke_width=2,
            stroke_fill=(5, 5, 8),
        )


def _typewriter_scenario() -> SyntheticScenario:
    baseline = _base_image()
    current = baseline.copy()
    _draw_dialogue(baseline, lines=(("門は真夜中に", 820, (244, 244, 240)),))
    _draw_dialogue(current, lines=(("門は真夜中に開く。", 820, (244, 244, 240)),))
    return SyntheticScenario(
        "typewriter",
        "句尾逐字增加，旧框应帮助恢复完整当前行",
        np.asarray(baseline),
        np.asarray(current),
        ("門は真夜中に開く。",),
        ("旅人",),
    )


def _fade_scenario() -> SyntheticScenario:
    baseline = _base_image()
    current = baseline.copy()
    _draw_dialogue(baseline, speaker="システム")
    _draw_dialogue(
        current,
        speaker="システム",
        lines=(("新しい任務が追加されました。", 820, (244, 244, 240)),),
    )
    return SyntheticScenario(
        "fade",
        "整行从背景中淡入，没有可吸附的旧正文框",
        np.asarray(baseline),
        np.asarray(current),
        ("新しい任務が追加されました。",),
        ("システム",),
    )


def _wrapped_scenario() -> SyntheticScenario:
    baseline = _base_image()
    current = baseline.copy()
    first = "川岸に沿って進み、"
    second = "失われた鍵を探す。"
    _draw_dialogue(baseline, lines=((first, 790, (244, 244, 240)),))
    _draw_dialogue(
        current,
        lines=(
            (first, 790, (244, 244, 240)),
            (second, 865, (244, 244, 240)),
        ),
    )
    return SyntheticScenario(
        "wrapped",
        "新换行出现，上一行应只作为翻译上下文",
        np.asarray(baseline),
        np.asarray(current),
        (second,),
        (first,),
    )


def _menu_scenario() -> SyntheticScenario:
    baseline = _base_image(dialogue=False)
    current = baseline.copy()
    for image, description in (
        (baseline, "軽量な偵察用ライフル"),
        (current, "連射速度が向上する"),
    ):
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((340, 250, 1580, 850), radius=24, fill=(29, 34, 45))
        draw.text((420, 310), "武器を選択", font=_font(42, cjk=True), fill=(229, 235, 244))
        draw.text((420, 440), "スカウト", font=_font(38, cjk=True), fill=(243, 220, 155))
        draw.text((420, 560), description, font=_font(36, cjk=True), fill=(211, 221, 235))
        draw.text((1260, 760), "閉じる", font=_font(30, cjk=True), fill=(170, 184, 204))
    return SyntheticScenario(
        "menu",
        "菜单说明局部替换，同栏标题作为上下文",
        np.asarray(baseline),
        np.asarray(current),
        ("連射速度が向上する",),
        ("スカウト",),
    )


def _animated_background_scenario() -> SyntheticScenario:
    baseline = _base_image()
    current = baseline.copy()
    _draw_dialogue(
        baseline, lines=(("門は閉ざされている。", 820, (244, 244, 240)),)
    )
    _draw_dialogue(
        current, lines=(("門は閉ざされている。", 820, (244, 244, 240)),)
    )
    ImageDraw.Draw(baseline).ellipse((300, 370, 450, 520), fill=(90, 125, 180))
    ImageDraw.Draw(current).ellipse((560, 370, 710, 520), fill=(90, 125, 180))
    return SyntheticScenario(
        "animated-background",
        "背景物体移动但文字不变，不应产生 LLM target",
        np.asarray(baseline),
        np.asarray(current),
        (),
        (),
    )


def _scroll_scenario() -> SyntheticScenario:
    baseline = _base_image(dialogue=False)
    current = _base_image(dialogue=False)
    for image, stripe_offset, line_offset in (
        (baseline, 0, 0),
        (current, 12, -58),
    ):
        draw = ImageDraw.Draw(image)
        draw.rectangle((120, 120, 1800, 1020), fill=(24, 29, 41))
        for y in range(120 - stripe_offset, 1020, 24):
            draw.rectangle((120, y, 1800, min(y + 11, 1020)), fill=(49, 55, 70))
        for index in range(18):
            y = 145 + index * 48 + line_offset
            if 125 <= y <= 990:
                draw.text(
                    (190, y),
                    f"記録 {index + (1 if line_offset else 0):02d}  遺跡調査報告",
                    font=_font(28, cjk=True),
                    fill=(222, 228, 238),
                )
    return SyntheticScenario(
        "scroll",
        "大面积列表滚动，应安全回退全帧并重建文字地图",
        np.asarray(baseline),
        np.asarray(current),
        None,
        (),
        True,
    )


def _scenarios() -> tuple[SyntheticScenario, ...]:
    return (
        _typewriter_scenario(),
        _fade_scenario(),
        _wrapped_scenario(),
        _menu_scenario(),
        _animated_background_scenario(),
        _scroll_scenario(),
    )


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


def _anchors(observations: Sequence[OcrText]) -> tuple[AnchorSnapshot, ...]:
    ordered = sorted(observations, key=lambda item: (item.bounds[1], item.bounds[0]))
    return tuple(
        AnchorSnapshot(f"prior-{index:03d}", item.text, item.bounds)
        for index, item in enumerate(ordered, start=1)
    )


def _normalized(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in value if character.isalnum())


def _target_score(
    expected: tuple[str, ...] | None, observations: Sequence[OcrText]
) -> tuple[str, bool]:
    if expected is None:
        return "-", True
    if not expected:
        return ("100.0%", True) if not observations else ("0.0%", False)
    expected_text = "".join(_normalized(item) for item in expected)
    observed_text = "".join(
        _normalized(item.text)
        for item in sorted(observations, key=lambda value: (value.bounds[1], value.bounds[0]))
    )
    score = SequenceMatcher(None, expected_text, observed_text, autojunk=False).ratio()
    return f"{score * 100:.1f}%", score >= 0.90


def _context_score(
    expected: Sequence[str], context: Sequence[str]
) -> tuple[str, bool]:
    if not expected:
        return "-", True
    joined = "".join(_normalized(item) for item in context)
    matched = sum(1 for item in expected if _normalized(item) in joined)
    return f"{matched}/{len(expected)}", matched == len(expected)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=(
            "all",
            "typewriter",
            "fade",
            "wrapped",
            "menu",
            "animated-background",
            "scroll",
        ),
        default="all",
    )
    parser.add_argument("--paddle-language", default="japan")
    parser.add_argument("--paddle-device", default="gpu:0")
    parser.add_argument("--paddle-max-side", type=int, default=1280)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=4)
    parser.add_argument("--show-text", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.warmups < 0 or args.repeats < 1:
        raise SystemExit("--warmups 必须 >= 0，--repeats 必须 >= 1")
    scenarios = tuple(
        item for item in _scenarios() if args.scenario == "all" or item.name == args.scenario
    )

    print("Initializing PaddleOCR (one initial full scan per scenario is outside recurring timings)...")
    paddle = PaddleOcrEngine(
        language=args.paddle_language,
        device=args.paddle_device,
        detection_max_side=args.paddle_max_side,
    )
    detector = FullScreenRoiDetector()
    planner = ContextualRoiPlanner()
    text_filter = OcrTextFilter("japan", translate_han_only=True)
    all_passed = True

    print()
    print(
        "scenario             regions coverage fallback  full ms   ROI ms speedup targets context result"
    )
    print(
        "-------------------  ------- -------- ---------  -------  ------- ------- ------- ------- ------"
    )
    for scenario in scenarios:
        baseline_observations = text_filter.apply(
            paddle.recognize_frame(scenario.baseline)
        ).accepted
        anchors: tuple[TextAnchor, ...] = _anchors(baseline_observations)
        proposal = detector.propose(scenario.baseline, scenario.current)
        plan = planner.plan_proposal(
            proposal,
            anchors,
            frame_size=(scenario.current.shape[1], scenario.current.shape[0]),
        )

        def dynamic_action() -> tuple[OcrText, ...]:
            current_proposal = detector.propose(scenario.baseline, scenario.current)
            current_plan = planner.plan_proposal(
                current_proposal,
                anchors,
                frame_size=(scenario.current.shape[1], scenario.current.shape[0]),
            )
            return text_filter.apply(
                recognize_ocr_rois(
                    paddle,
                    scenario.current,
                    tuple(region.roi for region in current_plan.regions),
                    edge_margin=12,
                )
            ).accepted

        full_result, dynamic_result = _benchmark(
            (
                (
                    "full",
                    lambda: text_filter.apply(
                        paddle.recognize_frame(scenario.current)
                    ).accepted,
                ),
                ("contextual ROI", dynamic_action),
            ),
            warmups=args.warmups,
            repeats=args.repeats,
        )
        groups = tuple(
            build_translation_context_group(region, dynamic_result.observations, anchors)
            for region in plan.regions
        )
        targets = tuple(item for group in groups for item in group.targets)
        context = tuple(
            item.text
            for group in groups
            for item in (*group.context_before, *group.context_after)
        )
        target_label, targets_ok = _target_score(scenario.expected_targets, targets)
        context_label, context_ok = _context_score(scenario.expected_context, context)
        fallback_ok = (
            scenario.expected_fallback is None
            or plan.fallback_full_frame == scenario.expected_fallback
        )
        scenario_ok = targets_ok and context_ok and fallback_ok
        all_passed = all_passed and scenario_ok
        speedup = full_result.median_ms / max(dynamic_result.median_ms, 0.001)
        print(
            f"{scenario.name:<19}  {len(plan.regions):7d} "
            f"{plan.coverage_fraction * 100:7.2f}% "
            f"{str(plan.fallback_full_frame):>9}  "
            f"{full_result.median_ms:7.1f}  {dynamic_result.median_ms:7.1f} "
            f"{speedup:7.2f} {target_label:>7} {context_label:>7} "
            f"{'PASS' if scenario_ok else 'CHECK'}"
        )
        if args.show_text:
            print(f"  {scenario.description}")
            print(f"  proposal={proposal.reason}; plan={plan.reason}")
            for index, region in enumerate(plan.regions, start=1):
                print(
                    f"  ROI {index}: {region.roi}; affected={region.affected_track_ids}; "
                    f"before={region.context_before_ids}; after={region.context_after_ids}"
                )
            print("  targets:", [item.text for item in targets])
            print("  context:", list(context))

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

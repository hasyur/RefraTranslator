from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from game_screen_translator.config import ConfigError, load_config
from game_screen_translator.domain import SourceText, TranslationBatch
from game_screen_translator.ocr.paddle import OcrDependencyError, OcrResultError, PaddleOcrEngine
from game_screen_translator.preview.renderer import render_preview
from game_screen_translator.profiles import (
    GameProfile,
    ProfileError,
    apply_profile_capture_settings,
    create_game_profile,
    load_game_profile,
)
from game_screen_translator.translation.cached import CachedTranslationService
from game_screen_translator.translation.hy_mt import (
    HyMtPromptBuilder,
    TranslationProtocolError,
)
from game_screen_translator.translation.service import TranslationService
from game_screen_translator.translation.transport import (
    OpenAICompatibleTransport,
    TranslationTransportError,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="game-screen-translator",
        description="游戏屏幕翻译原型",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="本机 TOML 配置文件（默认：config.toml）",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor", help="检查 API 连通性和模型名称")

    gui = commands.add_parser("gui", help="打开图形化 Profile、区域和启动管理器")
    gui.add_argument("--duration", type=float, help="指定秒数后自动关闭（用于测试）")

    translate = commands.add_parser("translate", help="直接翻译一段文本")
    translate.add_argument("text", help="待翻译文本")
    translate.add_argument("--zone-id", default="manual")
    translate.add_argument("--track-id", default="manual-1")
    translate.add_argument("--revision", type=int, default=1)
    translate.add_argument(
        "--profile",
        dest="profile_id",
        help="使用指定游戏的术语表和独立翻译缓存",
    )

    preview = commands.add_parser("preview", help="对静态截图执行 OCR、翻译并渲染预览")
    preview.add_argument("image", type=Path, help="输入截图")
    preview.add_argument(
        "--output",
        type=Path,
        default=Path("output/preview.png"),
        help="输出图片（默认：output/preview.png）",
    )
    preview.add_argument(
        "--profile",
        dest="profile_id",
        help="使用指定游戏的术语表和独立翻译缓存",
    )

    live = commands.add_parser("live", help="启动实时屏幕捕获与透明翻译覆盖层")
    live.add_argument(
        "--region",
        type=_parse_region,
        metavar="LEFT,TOP,WIDTH,HEIGHT",
        help="临时覆盖 config.toml 的捕获区域；宽高为 0 表示延伸到屏幕边缘",
    )
    live.add_argument("--monitor", type=int, help="临时覆盖显示器索引")
    live.add_argument("--debug-border", action="store_true", help="显示翻译区域边框")
    live.add_argument("--duration", type=float, help="指定秒数后自动停止（用于测试）")
    live.add_argument(
        "--test-source",
        type=Path,
        help="在捕获区显示一张普通图片，用于验证实时端到端链路",
    )
    live.add_argument(
        "--profile",
        dest="profile_id",
        help="使用指定游戏的术语表和独立翻译缓存",
    )

    profile = commands.add_parser("profile", help="管理每个游戏独立的资料库")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)

    profile_init = profile_commands.add_parser("init", help="新建游戏 Profile")
    profile_init.add_argument("profile_id", help="稳定的游戏 ID，例如 cyberpunk2077")
    profile_init.add_argument("--name", help="显示名称；默认与 ID 相同")

    profile_info = profile_commands.add_parser("info", help="查看 Profile 路径与统计")
    profile_info.add_argument("profile_id")

    profile_correct = profile_commands.add_parser(
        "correct",
        help="添加或替换一条最高优先级的人工修订",
    )
    profile_correct.add_argument("profile_id")
    profile_correct.add_argument("source", help="OCR 原文")
    profile_correct.add_argument("target", help="固定译文")

    profile_uncorrect = profile_commands.add_parser(
        "uncorrect",
        help="删除一条人工修订",
    )
    profile_uncorrect.add_argument("profile_id")
    profile_uncorrect.add_argument("source", help="OCR 原文")
    return parser


def _parse_region(value: str) -> tuple[int, int, int, int]:
    try:
        values = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("区域必须是四个整数：LEFT,TOP,WIDTH,HEIGHT") from exc
    if len(values) != 4 or any(part < 0 for part in values):
        raise argparse.ArgumentTypeError("区域必须是四个非负整数：LEFT,TOP,WIDTH,HEIGHT")
    return values  # type: ignore[return-value]


async def _doctor(config_path: Path) -> int:
    config = load_config(config_path)
    async with OpenAICompatibleTransport(config.translation) as transport:
        models = await transport.list_models()
    print(f"API：{config.translation.normalized_base_url}")
    print(f"可见模型：{len(models)} 个")
    if config.translation.model not in models:
        print(f"失败：找不到配置模型 {config.translation.model!r}", file=sys.stderr)
        return 2
    print(f"模型：{config.translation.model}（可用）")
    return 0


def _optional_profile(
    config_path: Path,
    config,
    profile_id: str | None,
) -> GameProfile | None:
    if profile_id is None:
        return None
    return load_game_profile(config_path, config, profile_id)


async def _translate(
    config_path: Path,
    source: SourceText,
    profile_id: str | None = None,
) -> str:
    config = load_config(config_path)
    profile = _optional_profile(config_path, config, profile_id)
    async with OpenAICompatibleTransport(config.translation) as transport:
        prompt_builder = HyMtPromptBuilder(config.translation.target_language)
        service = TranslationService(
            transport,
            prompt_builder=prompt_builder,
        )
        cached_service = CachedTranslationService(
            service,
            profile=profile,
            source_language=config.ocr.language,
            target_language=config.translation.target_language,
            model=config.translation.model,
            prompt_version=prompt_builder.prompt_version,
        )
        cached_outcome = await cached_service.translate(TranslationBatch((source,)))
    outcome = cached_outcome.outcome
    if not outcome.results:
        raise RuntimeError("翻译结果因 revision 过期而被丢弃")
    return outcome.results[0].translated_text


async def _preview(
    config_path: Path,
    image_path: Path,
    output_path: Path,
    profile_id: str | None = None,
) -> Path:
    config = load_config(config_path)
    profile = _optional_profile(config_path, config, profile_id)
    engine = PaddleOcrEngine(
        language=config.ocr.language,
        min_score=config.ocr.min_score,
        cache_dir=(config_path.resolve().parent / config.ocr.cache_dir),
        detection_model=config.ocr.detection_model,
        recognition_model=config.ocr.recognition_model,
        model_source=config.ocr.model_source,
        device=config.ocr.device,
    )
    observations = engine.recognize(image_path)
    if not observations:
        raise RuntimeError("截图中没有识别出满足置信度阈值的文字")

    sources = tuple(
        SourceText(
            zone_id="static-preview",
            track_id=f"ocr-{index}",
            revision=1,
            text=observation.text,
        )
        for index, observation in enumerate(observations)
    )
    async with OpenAICompatibleTransport(config.translation) as transport:
        prompt_builder = HyMtPromptBuilder(config.translation.target_language)
        service = TranslationService(
            transport,
            prompt_builder=prompt_builder,
        )
        cached_service = CachedTranslationService(
            service,
            profile=profile,
            source_language=config.ocr.language,
            target_language=config.translation.target_language,
            model=config.translation.model,
            prompt_version=prompt_builder.prompt_version,
        )
        cached_outcome = await cached_service.translate(TranslationBatch(sources))
    outcome = cached_outcome.outcome

    translations = tuple(result.translated_text for result in outcome.results)
    if len(translations) != len(observations):
        raise RuntimeError("有 OCR 区域在翻译完成前已经过期")
    return render_preview(
        image_path,
        output_path,
        observations,
        translations,
        config.preview,
    )


def _profile_command(config_path: Path, args: argparse.Namespace) -> int:
    config = load_config(config_path)
    if args.profile_command == "init":
        profile = create_game_profile(
            config_path,
            config,
            args.profile_id,
            display_name=args.name,
        )
        print(f"Profile 已创建：{profile.display_name} ({profile.profile_id})")
        print(f"目录：{profile.directory}")
        print(f"术语表：{profile.glossary_path}")
        print(f"缓存：{profile.database_path}")
        return 0

    profile = load_game_profile(config_path, config, args.profile_id)
    if args.profile_command == "info":
        stats = profile.cache.stats()
        print(f"Profile：{profile.display_name} ({profile.profile_id})")
        print(f"目录：{profile.directory}")
        print(f"术语：{len(profile.glossary)} 条")
        print(
            f"模型缓存：{stats.automatic_entries} 条（命中 {stats.automatic_hits} 次）"
        )
        print(
            f"人工修订：{stats.manual_corrections} 条（命中 {stats.manual_hits} 次）"
        )
        if profile.capture_settings.region is not None:
            print(
                "捕获区域："
                + ",".join(str(value) for value in profile.capture_settings.region)
            )
        if profile.capture_settings.monitor_index is not None:
            print(f"显示器：{profile.capture_settings.monitor_index}")
        return 0
    if args.profile_command == "correct":
        profile.cache.set_manual_correction(
            args.source,
            args.target,
            source_language=config.ocr.language,
            target_language=config.translation.target_language,
        )
        print(f"人工修订已保存到 {profile.profile_id}：{args.source} -> {args.target}")
        return 0
    if args.profile_command == "uncorrect":
        deleted = profile.cache.delete_manual_correction(
            args.source,
            source_language=config.ocr.language,
            target_language=config.translation.target_language,
        )
        if not deleted:
            raise ProfileError(f"没有找到对应的人工修订：{args.source}")
        print(f"人工修订已删除：{args.source}")
        return 0
    raise AssertionError(f"未知 Profile 命令：{args.profile_command}")


async def _run(args: argparse.Namespace) -> int:
    if args.command == "doctor":
        return await _doctor(args.config)
    if args.command == "translate":
        result = await _translate(
            args.config,
            SourceText(args.zone_id, args.track_id, args.revision, args.text),
            args.profile_id,
        )
        print(result)
        return 0
    if args.command == "preview":
        output = await _preview(args.config, args.image, args.output, args.profile_id)
        print(f"预览已保存：{output}")
        return 0
    if args.command == "profile":
        return _profile_command(args.config, args)
    raise AssertionError(f"未知命令：{args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "gui":
            from game_screen_translator.gui.launcher import run_launcher

            return run_launcher(args.config, duration_seconds=args.duration)
        if args.command == "live":
            from game_screen_translator.live.runtime import run_live

            config = load_config(args.config)
            profile = _optional_profile(args.config, config, args.profile_id)
            live_config = config.live
            if profile is not None:
                live_config = apply_profile_capture_settings(
                    live_config,
                    profile.capture_settings,
                )
            if args.region is not None:
                left, top, width, height = args.region
                live_config = replace(
                    live_config,
                    left=left,
                    top=top,
                    width=width,
                    height=height,
                )
            if args.monitor is not None:
                live_config = replace(live_config, monitor_index=args.monitor)
            return run_live(
                replace(config, live=live_config),
                args.config,
                duration_seconds=args.duration,
                debug_border=args.debug_border,
                test_source=args.test_source,
                profile=profile,
            )
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130
    except (
        ConfigError,
        ProfileError,
        FileNotFoundError,
        OcrDependencyError,
        OcrResultError,
        TranslationProtocolError,
        TranslationTransportError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

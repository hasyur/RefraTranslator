from __future__ import annotations

import os
from pathlib import Path

import pytest

from game_screen_translator.branding import LEGACY_LIVE_TEST_ENV, LIVE_TEST_ENV
from game_screen_translator.config import load_config
from game_screen_translator.domain import SourceText, TranslationBatch
from game_screen_translator.profiles import create_game_profile, load_game_profile
from game_screen_translator.translation.cached import CachedTranslationService
from game_screen_translator.translation.hy_mt import HyMtPromptBuilder
from game_screen_translator.translation.service import TranslationService
from game_screen_translator.translation.transport import OpenAICompatibleTransport


pytestmark = pytest.mark.integration


def _require_live_service() -> None:
    if not any(
        os.getenv(name) == "1"
        for name in (LIVE_TEST_ENV, LEGACY_LIVE_TEST_ENV)
    ):
        pytest.skip(f"设置 {LIVE_TEST_ENV}=1 后才访问本地 LLM 服务")


@pytest.mark.asyncio
async def test_live_model_and_glossary_contract(tmp_path: Path) -> None:
    _require_live_service()

    config_path = Path(__file__).parents[2] / "config.toml"
    config = load_config(config_path)
    temporary_config_path = tmp_path / "config.toml"
    profile = create_game_profile(temporary_config_path, config, "live")
    profile.glossary_path.write_text(
        '[[terms]]\nsource="フィクサー"\ntarget="中间人"\n',
        encoding="utf-8",
    )
    profile = load_game_profile(temporary_config_path, config, "live")
    first_source = SourceText("integration", "line-1", 1, "フィクサーから仕事を受けた。")
    second_source = SourceText("integration", "line-2", 1, "フィクサーから仕事を受けた。")
    async with OpenAICompatibleTransport(config.translation) as transport:
        assert config.translation.model in await transport.list_models()
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
        first = await cached_service.translate(
            TranslationBatch((first_source,)),
        )
        second = await cached_service.translate(
            TranslationBatch((second_source,)),
        )

    assert len(first.outcome.results) == 1
    assert "中间人" in first.outcome.results[0].translated_text
    assert first.origins == ("model",)
    assert second.origins == ("automatic",)


@pytest.mark.asyncio
async def test_live_model_preserves_eight_item_short_id_routing() -> None:
    _require_live_service()

    config_path = Path(__file__).parents[2] / "config.toml"
    config = load_config(config_path)
    sources = (
        SourceText("integration", "memory", 1, "メモリ使用量は105.8MBです。"),
        SourceText("integration", "network", 1, "通信速度は0 Mbpsです。"),
        SourceText("integration", "process", 1, "使用量は1975MBです。"),
        SourceText("integration", "temperature", 1, "温度は62度です。"),
        SourceText("integration", "fps", 1, "フレームレートは144 FPSです。"),
        SourceText("integration", "latency", 1, "遅延は16.7msです。"),
        SourceText("integration", "gpu", 1, "GPU使用率は98%です。"),
        SourceText("integration", "cpu", 1, "CPU使用率は37%です。"),
    )
    async with OpenAICompatibleTransport(config.translation) as transport:
        service = TranslationService(
            transport,
            prompt_builder=HyMtPromptBuilder(config.translation.target_language),
        )
        outcome = await service.translate(TranslationBatch(sources))

    assert tuple(result.source for result in outcome.results) == sources
    markers = ("105.8", "0", "1975", "62", "144", "16.7", "98", "37")
    assert all(
        marker in result.translated_text
        for marker, result in zip(markers, outcome.results, strict=True)
    )

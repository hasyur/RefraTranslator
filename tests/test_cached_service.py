from __future__ import annotations

import re
from pathlib import Path

import pytest

from game_screen_translator.config import AppConfig, TranslationConfig
from game_screen_translator.domain import ContextPair, SourceText, TranslationBatch
from game_screen_translator.profiles import create_game_profile, load_game_profile
from game_screen_translator.translation.cached import CachedTranslationService
from game_screen_translator.translation.hy_mt import HyMtPromptBuilder
from game_screen_translator.translation.service import TranslationService


class RecordingTransport:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        wire_ids = re.findall(r'<sn id="([^"]+)">', prompt)
        return "<target>" + "".join(
            f'<sn id="{wire_id}">模型译文</sn>' for wire_id in wire_ids
        ) + "</target>"


def _config() -> AppConfig:
    return AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-7b",
        )
    )


def _service(transport, profile):
    builder = HyMtPromptBuilder()
    base = TranslationService(transport, prompt_builder=builder)
    return CachedTranslationService(
        base,
        profile=profile,
        source_language="japan",
        target_language="简体中文",
        model="hy-mt1.5-7b",
        prompt_version=builder.prompt_version,
    )


@pytest.mark.asyncio
async def test_profile_glossary_and_cache_avoid_repeated_model_calls(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    created = create_game_profile(config_path, _config(), "game")
    created.glossary_path.write_text(
        '[[terms]]\nsource="フィクサー"\ntarget="中间人"\n',
        encoding="utf-8",
    )
    profile = load_game_profile(config_path, _config(), "game")
    transport = RecordingTransport()
    service = _service(transport, profile)

    first = await service.translate(
        TranslationBatch((SourceText("z", "first", 1, "フィクサー"),))
    )
    second = await service.translate(
        TranslationBatch((SourceText("z", "second", 1, "フィクサー"),))
    )

    assert first.origins == ("model",)
    assert second.origins == ("automatic",)
    assert len(transport.prompts) == 1
    assert "フィクサー 翻译成 中间人" in transport.prompts[0]


@pytest.mark.asyncio
async def test_manual_correction_bypasses_model_and_context_version(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    profile.cache.set_manual_correction(
        "待て。",
        "等等。",
        source_language="japan",
        target_language="简体中文",
    )
    transport = RecordingTransport()
    service = _service(transport, profile)

    outcome = await service.translate(
        TranslationBatch((SourceText("z", "line", 1, "待て。"),)),
        context=(ContextPair("急げ。", "快点。"),),
    )

    assert [result.translated_text for result in outcome.outcome.results] == ["等等。"]
    assert outcome.origins == ("manual",)
    assert transport.prompts == []


@pytest.mark.asyncio
async def test_changed_context_causes_automatic_cache_miss(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    transport = RecordingTransport()
    service = _service(transport, profile)

    await service.translate(
        TranslationBatch((SourceText("z", "first", 1, "そうだ。"),)),
        context=(ContextPair("A", "甲"),),
    )
    outcome = await service.translate(
        TranslationBatch((SourceText("z", "second", 1, "そうだ。"),)),
        context=(ContextPair("B", "乙"),),
    )

    assert outcome.origins == ("model",)
    assert len(transport.prompts) == 2

from __future__ import annotations

import asyncio
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from game_screen_translator.config import AppConfig, TranslationConfig
from game_screen_translator.domain import (
    ContextPair,
    RevisionRegistry,
    SourceText,
    TranslationBatch,
)
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


class ControlledTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, asyncio.Future[str]]] = []

    async def complete(self, prompt: str) -> str:
        future = asyncio.get_running_loop().create_future()
        self.calls.append((prompt, future))
        return await future


class ThreadControlledTransport:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()

    async def complete(self, prompt: str) -> str:
        with self._lock:
            self.prompts.append(prompt)
        self.started.set()
        if not self.release.wait(timeout=3):
            raise TimeoutError("test transport was not released")
        wire_ids = re.findall(r'<sn id="([^"]+)">', prompt)
        return "<target>" + "".join(
            f'<sn id="{wire_id}">模型译文</sn>' for wire_id in wire_ids
        ) + "</target>"


async def _wait_for_calls(transport: ControlledTransport, count: int) -> None:
    for _ in range(100):
        if len(transport.calls) >= count:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"只观察到 {len(transport.calls)} 次调用，预期 {count} 次")


def _config() -> AppConfig:
    return AppConfig(
        translation=TranslationConfig(
            provider="openai_compatible",
            base_url="http://server.test/v1",
            model="hy-mt1.5-7b",
        )
    )


def _service(transport, profile, *, revisions: RevisionRegistry | None = None):
    builder = HyMtPromptBuilder()
    base = TranslationService(
        transport,
        prompt_builder=builder,
        revisions=revisions,
    )
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
async def test_changed_context_reuses_stable_source_cache(tmp_path: Path) -> None:
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

    assert outcome.origins == ("automatic",)
    assert len(transport.prompts) == 1


@pytest.mark.asyncio
async def test_concurrent_identical_cache_keys_share_one_model_call(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    transport = ControlledTransport()
    first_service = _service(transport, profile)
    second_service = _service(transport, profile)
    first_source = SourceText("z", "first", 1, "待って。")
    second_source = SourceText("z", "second", 1, "待って。")

    first_task = asyncio.create_task(
        first_service.translate(
            TranslationBatch((first_source,)),
            context=(ContextPair("A", "甲"),),
        )
    )
    await _wait_for_calls(transport, 1)
    second_task = asyncio.create_task(
        second_service.translate(
            TranslationBatch((second_source,)),
            context=(ContextPair("B", "乙"),),
        )
    )
    await asyncio.sleep(0)

    assert len(transport.calls) == 1
    transport.calls[0][1].set_result(
        f'<target><sn id="{first_source.wire_id}">等一下。</sn></target>'
    )
    first, second = await asyncio.gather(first_task, second_task)

    assert [item.translated_text for item in first.outcome.results] == ["等一下。"]
    assert [item.translated_text for item in second.outcome.results] == ["等一下。"]
    assert first.origins == ("model",)
    assert second.origins == ("inflight",)
    assert profile.cache.inflight_count == 0
    stats = profile.cache.stats()
    assert stats.automatic_entries == 1
    assert stats.automatic_hits == 1


def test_identical_cache_keys_share_one_model_call_across_worker_threads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    transport = ThreadControlledTransport()
    waiter_joined = threading.Event()
    original_claim = profile.cache.claim_inflight

    def claim_inflight(*args, **kwargs):
        claim = original_claim(*args, **kwargs)
        if not claim.is_owner:
            waiter_joined.set()
        return claim

    monkeypatch.setattr(profile.cache, "claim_inflight", claim_inflight)
    first_source = SourceText("z", "first", 1, "待って。")
    second_source = SourceText("z", "second", 1, "待って。")
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            asyncio.run,
            _service(transport, profile).translate(
                TranslationBatch((first_source,))
            ),
        )
        assert transport.started.wait(timeout=2)
        second_future = executor.submit(
            asyncio.run,
            _service(transport, profile).translate(
                TranslationBatch((second_source,))
            ),
        )
        assert waiter_joined.wait(timeout=2)
        assert len(transport.prompts) == 1
        transport.release.set()
        first = first_future.result(timeout=2)
        second = second_future.result(timeout=2)

    assert first.origins == ("model",)
    assert second.origins == ("inflight",)
    assert profile.cache.inflight_count == 0


@pytest.mark.asyncio
async def test_inflight_owner_failure_releases_key_for_retry(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    transport = ControlledTransport()
    first_source = SourceText("z", "first", 1, "待って。")
    second_source = SourceText("z", "second", 1, "待って。")
    first_task = asyncio.create_task(
        _service(transport, profile).translate(TranslationBatch((first_source,)))
    )
    await _wait_for_calls(transport, 1)
    second_task = asyncio.create_task(
        _service(transport, profile).translate(TranslationBatch((second_source,)))
    )
    await asyncio.sleep(0)

    transport.calls[0][1].set_exception(RuntimeError("backend failed"))
    failed = await asyncio.gather(first_task, second_task, return_exceptions=True)

    assert all(isinstance(item, RuntimeError) for item in failed)
    assert profile.cache.inflight_count == 0

    retry_transport = RecordingTransport()
    retry = await _service(retry_transport, profile).translate(
        TranslationBatch((SourceText("z", "retry", 1, "待って。"),))
    )
    assert retry.origins == ("model",)
    assert len(retry_transport.prompts) == 1


@pytest.mark.asyncio
async def test_inflight_result_survives_a_stale_owner_for_current_waiter(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    profile = create_game_profile(config_path, _config(), "game")
    transport = ControlledTransport()
    revisions = RevisionRegistry()
    old = SourceText("z", "line", 1, "待って。")
    current = SourceText("z", "line", 2, "待って。")

    old_task = asyncio.create_task(
        _service(transport, profile, revisions=revisions).translate(
            TranslationBatch((old,))
        )
    )
    await _wait_for_calls(transport, 1)
    current_task = asyncio.create_task(
        _service(transport, profile, revisions=revisions).translate(
            TranslationBatch((current,))
        )
    )
    await asyncio.sleep(0)

    assert len(transport.calls) == 1
    transport.calls[0][1].set_result(
        f'<target><sn id="{old.wire_id}">等一下。</sn></target>'
    )
    old_outcome, current_outcome = await asyncio.gather(old_task, current_task)

    assert old_outcome.outcome.results == ()
    assert old_outcome.outcome.discarded_stale == (old,)
    assert [item.translated_text for item in current_outcome.outcome.results] == [
        "等一下。"
    ]
    assert current_outcome.origins == ("inflight",)
    assert profile.cache.inflight_count == 0

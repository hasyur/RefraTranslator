import json

import httpx
import pytest

from game_screen_translator.config import TranslationConfig
from game_screen_translator.translation.transport import (
    OpenAICompatibleTransport,
    TranslationTransportError,
)


def _config(**overrides) -> TranslationConfig:
    values = {
        "provider": "openai_compatible",
        "base_url": "http://server.test/v1",
        "model": "hy-mt1.5-7b",
    }
    values.update(overrides)
    return TranslationConfig(**values)


@pytest.mark.asyncio
async def test_transport_lists_models_and_sends_chat_contract() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "hy-mt1.5-7b"}]})
        body = json.loads(request.content)
        assert body["model"] == "hy-mt1.5-7b"
        assert body["messages"] == [{"role": "user", "content": "prompt"}]
        assert body["stream"] is False
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "<target />"}}]},
        )

    async with OpenAICompatibleTransport(
        _config(),
        http_transport=httpx.MockTransport(handler),
    ) as transport:
        assert await transport.list_models() == ("hy-mt1.5-7b",)
        assert await transport.complete("prompt") == "<target />"

    assert [request.url.path for request in requests] == [
        "/v1/models",
        "/v1/chat/completions",
    ]


@pytest.mark.asyncio
async def test_transport_reports_http_error_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="model is loading")

    async with OpenAICompatibleTransport(
        _config(),
        http_transport=httpx.MockTransport(handler),
    ) as transport:
        with pytest.raises(TranslationTransportError, match="503.*model is loading"):
            await transport.complete("prompt")

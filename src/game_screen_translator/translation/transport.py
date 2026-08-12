from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from types import TracebackType
from typing import Any

import httpx

from game_screen_translator.config import TranslationConfig


class TranslationTransportError(RuntimeError):
    """Raised when the OpenAI-compatible service cannot satisfy a request."""


def parse_model_ids(payload: Any) -> tuple[str, ...]:
    if not isinstance(payload, Mapping):
        raise TranslationTransportError("/v1/models 返回的 JSON 根节点不是对象")
    records = payload.get("data")
    if not isinstance(records, list):
        raise TranslationTransportError("/v1/models 响应缺少 data 数组")
    model_ids: list[str] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        model_id = record.get("id")
        if not isinstance(model_id, str):
            continue
        model_id = model_id.strip()
        if model_id and model_id not in seen:
            seen.add(model_id)
            model_ids.append(model_id)
    return tuple(model_ids)


class OpenAICompatibleTransport:
    def __init__(
        self,
        config: TranslationConfig,
        *,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        headers: dict[str, str] = {"Accept": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        self._client = httpx.AsyncClient(
            base_url=config.normalized_base_url,
            timeout=httpx.Timeout(config.timeout_seconds),
            headers=headers,
            transport=http_transport,
        )
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self._closed = False

    async def __aenter__(self) -> OpenAICompatibleTransport:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            await self._client.aclose()

    async def list_models(self) -> tuple[str, ...]:
        payload = await self._request_json("GET", "models")
        return parse_model_ids(payload)

    async def complete(self, prompt: str) -> str:
        request_body = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_tokens": self.config.max_output_tokens,
            "stream": False,
        }
        payload = await self._request_json("POST", "chat/completions", json=request_body)
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TranslationTransportError("/v1/chat/completions 响应结构不完整") from exc
        if not isinstance(content, str) or not content.strip():
            raise TranslationTransportError("/v1/chat/completions 返回了空内容")
        return content

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if self._closed:
            raise TranslationTransportError("翻译客户端已经关闭")
        try:
            async with self._semaphore:
                response = await self._client.request(method, path, **kwargs)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TranslationTransportError(
                f"翻译服务请求超时（{self.config.timeout_seconds:g} 秒）"
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip()
            if len(detail) > 300:
                detail = detail[:300] + "…"
            raise TranslationTransportError(
                f"翻译服务返回 HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise TranslationTransportError(f"无法连接翻译服务：{exc}") from exc

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise TranslationTransportError("翻译服务返回的不是有效 JSON") from exc
        if not isinstance(payload, dict):
            raise TranslationTransportError("翻译服务 JSON 根节点不是对象")
        return payload

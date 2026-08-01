import json
from collections.abc import AsyncIterator
from typing import Any, get_args

import httpx

from app.core.config import Settings
from app.core.errors import GatewayConfigError, UpstreamError, UpstreamProtocolError
from app.schemas.chat import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionDelta,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Role,
    Usage,
)

PROVIDER_NAME = "openai"
SSE_DONE = "[DONE]"
_ROLES = frozenset(get_args(Role))


def _headers(settings: Settings) -> dict[str, str]:
    if not settings.openai_api_key:
        raise GatewayConfigError("OPENAI_API_KEY is not configured")
    return {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }


def _url(settings: Settings) -> str:
    return f"{settings.openai_base_url.rstrip('/')}/chat/completions"


def build_payload(request: ChatCompletionRequest, *, stream: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": request.model,
        "messages": [message.model_dump() for message in request.messages],
        "stream": stream,
    }
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.top_p is not None:
        payload["top_p"] = request.top_p
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    if request.stop:
        payload["stop"] = request.stop
    return payload


def _parse_response(body: dict[str, Any]) -> ChatCompletionResponse:
    try:
        choices = [
            ChatCompletionChoice(
                index=choice.get("index", position),
                message=ChatMessage(
                    role=choice["message"].get("role", "assistant"),
                    content=choice["message"].get("content") or "",
                ),
                finish_reason=choice.get("finish_reason"),
            )
            for position, choice in enumerate(body["choices"])
        ]
        raw_usage = body.get("usage")
        usage = Usage(**raw_usage) if raw_usage else None
        return ChatCompletionResponse(
            id=body["id"],
            created=body["created"],
            model=body["model"],
            provider=PROVIDER_NAME,
            choices=choices,
            usage=usage,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise UpstreamProtocolError(PROVIDER_NAME, str(exc)) from exc


async def create_chat_completion(
    client: httpx.AsyncClient,
    settings: Settings,
    request: ChatCompletionRequest,
) -> ChatCompletionResponse:
    response = await client.post(
        _url(settings),
        json=build_payload(request, stream=False),
        headers=_headers(settings),
    )
    if response.status_code >= 400:
        raise UpstreamError(PROVIDER_NAME, response.status_code, response.text)
    return _parse_response(response.json())


async def open_stream(
    client: httpx.AsyncClient,
    settings: Settings,
    request: ChatCompletionRequest,
) -> httpx.Response:
    upstream_request = client.build_request(
        "POST",
        _url(settings),
        json=build_payload(request, stream=True),
        headers=_headers(settings),
    )
    response = await client.send(upstream_request, stream=True)
    if response.status_code >= 400:
        await response.aread()
        detail = response.text
        await response.aclose()
        raise UpstreamError(PROVIDER_NAME, response.status_code, detail)
    return response


def _parse_chunk(data: str) -> ChatCompletionChunk | None:
    try:
        body = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None

    choices = []
    for position, choice in enumerate(body.get("choices") or []):
        delta = choice.get("delta") or {}
        role = delta.get("role")
        choices.append(
            ChatCompletionChunkChoice(
                index=choice.get("index", position),
                delta=ChatCompletionDelta(
                    role=role if role in _ROLES else None,
                    content=delta.get("content"),
                ),
                finish_reason=choice.get("finish_reason"),
            )
        )

    return ChatCompletionChunk(
        id=body.get("id", ""),
        created=body.get("created", 0),
        model=body.get("model", ""),
        provider=PROVIDER_NAME,
        choices=choices,
    )


async def iter_stream(response: httpx.Response) -> AsyncIterator[str]:
    try:
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data == SSE_DONE:
                break
            chunk = _parse_chunk(data)
            if chunk is not None:
                yield f"data: {chunk.model_dump_json()}\n\n"
        yield f"data: {SSE_DONE}\n\n"
    finally:
        await response.aclose()

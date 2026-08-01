import json
from typing import Any, get_args

from app.core.errors import UpstreamProtocolError
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

SSE_DONE = "[DONE]"
_ROLES = frozenset(get_args(Role))


def to_upstream_payload(
    request: ChatCompletionRequest,
    *,
    model: str,
    stream: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
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


def to_unified_response(body: dict[str, Any], *, provider: str) -> ChatCompletionResponse:
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
        return ChatCompletionResponse(
            id=body["id"],
            created=body["created"],
            model=body["model"],
            provider=provider,
            choices=choices,
            usage=Usage(**raw_usage) if raw_usage else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise UpstreamProtocolError(provider, str(exc)) from exc


def to_unified_chunk(data: str, *, provider: str) -> ChatCompletionChunk | None:
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
        provider=provider,
        choices=choices,
    )

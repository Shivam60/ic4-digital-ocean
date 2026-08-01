import json
import time
import uuid
from typing import Any

from app.core.errors import UpstreamProtocolError
from app.schemas.chat import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionDelta,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Usage,
)

_DONE_REASON_TO_FINISH_REASON = {
    "stop": "stop",
    "length": "length",
    "load": "stop",
}


def new_completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def to_upstream_payload(
    request: ChatCompletionRequest, *, model: str, stream: bool
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if request.temperature is not None:
        options["temperature"] = request.temperature
    if request.top_p is not None:
        options["top_p"] = request.top_p
    if request.max_tokens is not None:
        options["num_predict"] = request.max_tokens
    if request.stop:
        options["stop"] = request.stop

    payload: dict[str, Any] = {
        "model": model,
        "messages": [message.model_dump() for message in request.messages],
        "stream": stream,
    }
    if options:
        payload["options"] = options
    return payload


def _finish_reason(body: dict[str, Any]) -> str | None:
    if not body.get("done"):
        return None
    done_reason = body.get("done_reason") or "stop"
    return _DONE_REASON_TO_FINISH_REASON.get(done_reason, done_reason)


def _usage(body: dict[str, Any]) -> Usage | None:
    prompt_tokens = body.get("prompt_eval_count")
    completion_tokens = body.get("eval_count")
    if prompt_tokens is None and completion_tokens is None:
        return None
    prompt_tokens = prompt_tokens or 0
    completion_tokens = completion_tokens or 0
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def to_unified_response(
    body: dict[str, Any], *, provider: str, completion_id: str
) -> ChatCompletionResponse:
    try:
        message = body["message"]
        return ChatCompletionResponse(
            id=completion_id,
            created=int(time.time()),
            model=body.get("model", ""),
            provider=provider,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(
                        role=message.get("role", "assistant"),
                        content=message.get("content") or "",
                    ),
                    finish_reason=_finish_reason(body) or "stop",
                )
            ],
            usage=_usage(body),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise UpstreamProtocolError(provider, str(exc)) from exc


def to_unified_chunk(
    line: str, *, provider: str, completion_id: str, created: int
) -> ChatCompletionChunk | None:
    try:
        body = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None

    message = body.get("message") or {}
    return ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=body.get("model", ""),
        provider=provider,
        choices=[
            ChatCompletionChunkChoice(
                index=0,
                delta=ChatCompletionDelta(content=message.get("content") or None),
                finish_reason=_finish_reason(body),
            )
        ],
    )

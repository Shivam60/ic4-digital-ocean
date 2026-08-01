import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

MODEL_OK = "mock/ok"
MODEL_429 = "mock/429"
MODEL_500 = "mock/500"

TOKENS = ["Hello", ",", " world", " from", " the", " anthropic", " mock", "."]
TOKEN_DELAY_SECONDS = 0.15

app = FastAPI(title="mock-anthropic-provider")


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class MessagesRequest(BaseModel):
    model: str
    messages: list[Message] = Field(min_length=1)
    system: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stop_sequences: list[str] | None = None
    stream: bool = False


def _message_id() -> str:
    return f"msg_{uuid.uuid4().hex[:24]}"


def _error(status_code: int, error_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"type": "error", "error": {"type": error_type, "message": message}},
    )


def _event(event_type: str, body: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(body)}\n\n"


def _message_envelope(message_id: str, model: str) -> dict[str, Any]:
    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 11, "output_tokens": 0},
    }


async def _stream_message(model: str) -> AsyncIterator[str]:
    message_id = _message_id()

    yield _event(
        "message_start",
        {"type": "message_start", "message": _message_envelope(message_id, model)},
    )
    yield _event(
        "content_block_start",
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
    )
    yield _event("ping", {"type": "ping"})

    for token in TOKENS:
        await asyncio.sleep(TOKEN_DELAY_SECONDS)
        yield _event(
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": token},
            },
        )

    yield _event("content_block_stop", {"type": "content_block_stop", "index": 0})
    yield _event(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": len(TOKENS)},
        },
    )
    yield _event("message_stop", {"type": "message_stop"})


@app.post("/v1/messages")
async def messages(
    payload: MessagesRequest,
    x_api_key: str | None = Header(default=None),
    anthropic_version: str | None = Header(default=None),
) -> Any:
    if not x_api_key:
        return _error(401, "authentication_error", "missing x-api-key header")

    if not anthropic_version:
        return _error(400, "invalid_request_error", "missing anthropic-version header")

    if payload.max_tokens is None:
        return _error(400, "invalid_request_error", "max_tokens: field required")

    if payload.model == MODEL_429:
        return _error(
            429, "rate_limit_error", "number of requests has exceeded your rate limit"
        )

    if payload.model == MODEL_500:
        return _error(500, "api_error", "an unexpected error occurred")

    if payload.model != MODEL_OK:
        return _error(404, "not_found_error", f"model: {payload.model}")

    if not payload.stream:
        envelope = _message_envelope(_message_id(), payload.model)
        envelope["content"] = [{"type": "text", "text": "".join(TOKENS)}]
        envelope["stop_reason"] = "end_turn"
        envelope["usage"]["output_tokens"] = len(TOKENS)
        return envelope

    return StreamingResponse(
        _stream_message(payload.model),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

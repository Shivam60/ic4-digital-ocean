import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

MODEL_OK = "mock/ok"
MODEL_429 = "mock/429"
MODEL_500 = "mock/500"

TOKENS = ["Hello", ",", " world", " from", " the", " ollama", " mock", "."]
TOKEN_DELAY_SECONDS = 0.15
SSE_DONE = "[DONE]"

app = FastAPI(title="mock-ollama-provider")


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class NativeChatRequest(BaseModel):
    model: str
    messages: list[Message] = Field(min_length=1)
    stream: bool = True
    options: dict[str, Any] | None = None


class CompatChatRequest(BaseModel):
    model: str
    messages: list[Message] = Field(min_length=1)
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: list[str] | None = None
    stream: bool = False


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _native_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


def _native_line(model: str, content: str) -> str:
    body = {
        "model": model,
        "created_at": _now(),
        "message": {"role": "assistant", "content": content},
        "done": False,
    }
    return f"{json.dumps(body)}\n"


def _native_final_line(model: str) -> str:
    body = {
        "model": model,
        "created_at": _now(),
        "message": {"role": "assistant", "content": ""},
        "done_reason": "stop",
        "done": True,
        "total_duration": 1_393_682_708,
        "prompt_eval_count": 11,
        "eval_count": len(TOKENS),
    }
    return f"{json.dumps(body)}\n"


async def _stream_native(model: str) -> AsyncIterator[str]:
    for token in TOKENS:
        await asyncio.sleep(TOKEN_DELAY_SECONDS)
        yield _native_line(model, token)
    yield _native_final_line(model)


def _native_full(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "created_at": _now(),
        "message": {"role": "assistant", "content": "".join(TOKENS)},
        "done_reason": "stop",
        "done": True,
        "total_duration": 1_393_682_708,
        "prompt_eval_count": 11,
        "eval_count": len(TOKENS),
    }


@app.post("/api/chat")
async def native_chat(payload: NativeChatRequest) -> Any:
    if payload.model == MODEL_429:
        return _native_error(429, "server busy, please try again")

    if payload.model == MODEL_500:
        return _native_error(500, "an unexpected error occurred")

    if payload.model != MODEL_OK:
        return _native_error(
            404, f'model "{payload.model}" not found, try pulling it first'
        )

    if not payload.stream:
        return _native_full(payload.model)

    return StreamingResponse(
        _stream_native(payload.model),
        media_type="application/x-ndjson",
    )


def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _compat_error(status_code: int, message: str, error_type: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "type": error_type,
                "param": None,
                "code": None,
            }
        },
    )


def _compat_chunk(
    completion_id: str,
    created: int,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None = None,
) -> str:
    body = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(body)}\n\n"


async def _stream_compat(model: str) -> AsyncIterator[str]:
    completion_id = _completion_id()
    created = int(time.time())

    yield _compat_chunk(
        completion_id, created, model, {"role": "assistant", "content": ""}
    )
    for token in TOKENS:
        await asyncio.sleep(TOKEN_DELAY_SECONDS)
        yield _compat_chunk(completion_id, created, model, {"content": token})
    yield _compat_chunk(completion_id, created, model, {}, finish_reason="stop")
    yield f"data: {SSE_DONE}\n\n"


@app.post("/v1/chat/completions")
async def compat_chat(payload: CompatChatRequest) -> Any:
    if payload.model == MODEL_429:
        return _compat_error(
            429, "server busy, please try again", "rate_limit_exceeded"
        )

    if payload.model == MODEL_500:
        return _compat_error(500, "an unexpected error occurred", "server_error")

    if payload.model != MODEL_OK:
        return _compat_error(
            404, f"model '{payload.model}' not found", "invalid_request_error"
        )

    if not payload.stream:
        return {
            "id": _completion_id(),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": payload.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "".join(TOKENS)},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": len(TOKENS),
                "total_tokens": 11 + len(TOKENS),
            },
        }

    return StreamingResponse(
        _stream_compat(payload.model),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

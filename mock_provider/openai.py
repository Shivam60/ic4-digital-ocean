import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

MODEL_OK = "mock/ok"
MODEL_429 = "mock/429"
MODEL_500 = "mock/500"

TOKENS = ["Hello", ",", " world", " from", " the", " mock", " provider", "."]
TOKEN_DELAY_SECONDS = 0.15
SSE_DONE = "[DONE]"

app = FastAPI(title="mock-openai-provider")


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[Message] = Field(min_length=1)
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: list[str] | None = None
    stream: bool = False


def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _error(
    status_code: int,
    message: str,
    error_type: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "message": message,
                "type": error_type,
                "param": None,
                "code": None,
            }
        },
    )


def _chunk(
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


async def _stream_tokens(model: str) -> AsyncIterator[str]:
    completion_id = _completion_id()
    created = int(time.time())

    yield _chunk(completion_id, created, model, {"role": "assistant", "content": ""})
    for token in TOKENS:
        await asyncio.sleep(TOKEN_DELAY_SECONDS)
        yield _chunk(completion_id, created, model, {"content": token})
    yield _chunk(completion_id, created, model, {}, finish_reason="stop")
    yield f"data: {SSE_DONE}\n\n"


def _full_response(model: str) -> dict[str, Any]:
    content = "".join(TOKENS)
    return {
        "id": _completion_id(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": len(TOKENS),
            "total_tokens": 11 + len(TOKENS),
        },
    }


@app.post("/v1/chat/completions")
async def chat_completions(payload: ChatCompletionRequest) -> Any:
    if payload.model == MODEL_429:
        return _error(
            429,
            "Rate limit reached for requests",
            "rate_limit_exceeded",
            headers={"Retry-After": "1"},
        )

    if payload.model == MODEL_500:
        return _error(
            500, "The server had an error processing your request", "server_error"
        )

    if payload.model != MODEL_OK:
        return _error(
            404, f"The model `{payload.model}` does not exist", "invalid_request_error"
        )

    if not payload.stream:
        return _full_response(payload.model)

    return StreamingResponse(
        _stream_tokens(payload.model),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

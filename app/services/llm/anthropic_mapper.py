import json
import time
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

_STOP_REASON_TO_FINISH_REASON = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
}


def to_upstream_payload(
    request: ChatCompletionRequest,
    *,
    model: str,
    stream: bool,
    default_max_tokens: int,
) -> dict[str, Any]:
    system_parts = [
        message.content for message in request.messages if message.role == "system"
    ]
    conversation = [
        {"role": message.role, "content": message.content}
        for message in request.messages
        if message.role != "system"
    ]

    payload: dict[str, Any] = {
        "model": model,
        "messages": conversation,
        "max_tokens": request.max_tokens or default_max_tokens,
        "stream": stream,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.top_p is not None:
        payload["top_p"] = request.top_p
    if request.stop:
        payload["stop_sequences"] = request.stop
    return payload


def _finish_reason(stop_reason: str | None) -> str | None:
    if stop_reason is None:
        return None
    return _STOP_REASON_TO_FINISH_REASON.get(stop_reason, stop_reason)


def to_unified_response(
    body: dict[str, Any], *, provider: str
) -> ChatCompletionResponse:
    try:
        text = "".join(
            block.get("text") or ""
            for block in body.get("content") or []
            if block.get("type") == "text"
        )
        raw_usage = body.get("usage") or {}
        input_tokens = raw_usage.get("input_tokens")
        output_tokens = raw_usage.get("output_tokens")
        usage = None
        if input_tokens is not None or output_tokens is not None:
            input_tokens = input_tokens or 0
            output_tokens = output_tokens or 0
            usage = Usage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )

        return ChatCompletionResponse(
            id=body["id"],
            created=int(time.time()),
            model=body.get("model", ""),
            provider=provider,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=text),
                    finish_reason=_finish_reason(body.get("stop_reason")) or "stop",
                )
            ],
            usage=usage,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise UpstreamProtocolError(provider, str(exc)) from exc


class AnthropicStreamState:
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.message_id = ""
        self.model = ""
        self.created = int(time.time())
        self.finished = False

    def consume(self, data: str) -> ChatCompletionChunk | None:
        try:
            body = json.loads(data)
        except json.JSONDecodeError:
            return None
        if not isinstance(body, dict):
            return None

        event_type = body.get("type")

        if event_type == "message_start":
            message = body.get("message") or {}
            self.message_id = message.get("id", "")
            self.model = message.get("model", "")
            return None

        if event_type == "content_block_delta":
            delta = body.get("delta") or {}
            if delta.get("type") != "text_delta":
                return None
            return self._chunk(content=delta.get("text") or "")

        if event_type == "message_delta":
            stop_reason = (body.get("delta") or {}).get("stop_reason")
            finish_reason = _finish_reason(stop_reason)
            if finish_reason is None:
                return None
            return self._chunk(finish_reason=finish_reason)

        if event_type == "message_stop":
            self.finished = True

        return None

    def _chunk(
        self, content: str | None = None, finish_reason: str | None = None
    ) -> ChatCompletionChunk:
        return ChatCompletionChunk(
            id=self.message_id,
            created=self.created,
            model=self.model,
            provider=self.provider,
            choices=[
                ChatCompletionChunkChoice(
                    index=0,
                    delta=ChatCompletionDelta(content=content),
                    finish_reason=finish_reason,
                )
            ],
        )

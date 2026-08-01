import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.schemas.chat import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionDelta,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
)
from app.services.llm.http_service import HttpLLMService

STOP_LINE = "STOP"
DONE_FRAME = "data: [DONE]\n\n"


class StubReader:
    def __init__(self, provider: str) -> None:
        self._provider = provider
        self.finished = False

    def read(self, line: str) -> ChatCompletionChunk | None:
        if line == STOP_LINE:
            self.finished = True
            return None
        if not line.strip():
            return None
        return ChatCompletionChunk(
            id="stub-1",
            created=1,
            model="stub-model",
            provider=self._provider,
            choices=[
                ChatCompletionChunkChoice(
                    index=0,
                    delta=ChatCompletionDelta(content=line),
                    finish_reason=None,
                )
            ],
        )


class StubDialect:
    path = "/stub/chat"

    def headers(self, api_key: str | None) -> dict[str, str]:
        return {"X-Stub-Auth": api_key} if api_key else {}

    def to_payload(
        self, request: ChatCompletionRequest, *, stream: bool
    ) -> dict[str, Any]:
        return {"stub_model": request.model, "stub_stream": stream}

    def to_response(
        self, body: dict[str, Any], *, provider: str
    ) -> ChatCompletionResponse:
        return ChatCompletionResponse(
            id="stub-1",
            created=1,
            model=body["model"],
            provider=provider,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=body["text"]),
                    finish_reason="stop",
                )
            ],
        )

    def new_reader(self, provider: str) -> StubReader:
        return StubReader(provider)


def _request(stream: bool = False) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="demo",
        messages=[ChatMessage(role="user", content="hi")],
        stream=stream,
    )


def _service(
    handler: httpx.MockTransport | Any, api_key: str | None = "secret"
) -> HttpLLMService:
    return HttpLLMService(
        name="stub",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://provider.test/",
        dialect=StubDialect(),
        api_key=api_key,
    )


async def _emit(*lines: str) -> AsyncIterator[bytes]:
    for line in lines:
        yield f"{line}\n".encode()


async def test_complete_sends_the_translated_payload() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"model": "stub-model", "text": "hello"})

    await _service(handler).complete(_request())

    assert str(seen[0].url) == "http://provider.test/stub/chat"
    assert seen[0].headers["x-stub-auth"] == "secret"
    assert seen[0].headers["content-type"] == "application/json"
    assert json.loads(seen[0].content) == {"stub_model": "demo", "stub_stream": False}


async def test_complete_returns_the_dialect_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "stub-model", "text": "hello"})

    response = await _service(handler).complete(_request())

    assert response.provider == "stub"
    assert response.model == "stub-model"
    assert response.choices[0].message.content == "hello"


async def test_stream_relays_reader_chunks_as_sse() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_emit("Hello", " world", STOP_LINE))

    handle = await _service(handler).stream(_request(stream=True))
    frames = [frame async for frame in handle.events]

    assert handle.provider == "stub"
    assert json.loads(seen[0].content)["stub_stream"] is True
    assert frames[-1] == DONE_FRAME

    contents = [
        json.loads(frame.removeprefix("data: "))["choices"][0]["delta"]["content"]
        for frame in frames[:-1]
    ]
    assert contents == ["Hello", " world"]


async def test_stream_omits_the_authorization_header_when_no_key_is_set() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_emit(STOP_LINE))

    handle = await _service(handler, api_key=None).stream(_request(stream=True))
    frames = [frame async for frame in handle.events]

    assert "x-stub-auth" not in seen[0].headers
    assert frames == [DONE_FRAME]

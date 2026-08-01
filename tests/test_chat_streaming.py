import json
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_model_repository
from app.core.config import Settings, get_settings
from app.services.llm.ollama import OllamaService
from app.services.llm.openai_mapper import SSE_DONE
from app.services.model_repository import ModelRepository

UPSTREAM_API_KEY = "test-key"
UPSTREAM_CHUNK_SIZE = 7
PROVIDER_NAME = "ollama"


def _upstream_frame(content: str | None, finish_reason: str | None = None) -> str:
    delta: dict[str, str] = {} if content is None else {"content": content}
    body = {
        "id": "chatcmpl-relay",
        "object": "chat.completion.chunk",
        "created": 1_700_000_000,
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(body)}\n\n"


UPSTREAM_BODY = "".join(
    [
        _upstream_frame("Hel"),
        _upstream_frame("lo, "),
        "data: {not valid json\n\n",
        _upstream_frame("world"),
        _upstream_frame(None, finish_reason="stop"),
        f"data: {SSE_DONE}\n\n",
    ]
)


async def _dribble(body: str) -> AsyncIterator[bytes]:
    raw = body.encode()
    for start in range(0, len(raw), UPSTREAM_CHUNK_SIZE):
        yield raw[start : start + UPSTREAM_CHUNK_SIZE]


@pytest.fixture
def upstream_settings() -> Settings:
    return Settings(openai_api_key=UPSTREAM_API_KEY)


@pytest.fixture
def seen_requests(app: FastAPI, upstream_settings: Settings) -> list[httpx.Request]:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_dribble(UPSTREAM_BODY),
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    repository = ModelRepository(
        services=[
            OllamaService(
                name=PROVIDER_NAME,
                client=mock_client,
                base_url="http://upstream.test/v1",
                api_key=UPSTREAM_API_KEY,
            )
        ],
        routes={},
        default_chain=[PROVIDER_NAME],
    )
    app.dependency_overrides[get_model_repository] = lambda: repository
    app.dependency_overrides[get_settings] = lambda: upstream_settings
    yield captured
    app.dependency_overrides.clear()


async def test_streaming_relay_emits_unified_sse(
    client: httpx.AsyncClient,
    upstream_settings: Settings,
    seen_requests: list[httpx.Request],
) -> None:
    response = await client.post(
        f"{upstream_settings.api_prefix}/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-gateway-provider"] == PROVIDER_NAME

    assert len(seen_requests) == 1
    upstream_request = seen_requests[0]
    assert upstream_request.headers["authorization"] == f"Bearer {UPSTREAM_API_KEY}"
    assert json.loads(upstream_request.content)["stream"] is True

    frames = [
        line[len("data:") :].strip()
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]

    assert frames[-1] == SSE_DONE
    assert frames.count(SSE_DONE) == 1

    chunks = [json.loads(frame) for frame in frames[:-1]]
    assert [chunk["object"] for chunk in chunks] == ["chat.completion.chunk"] * 4
    assert {chunk["provider"] for chunk in chunks} == {PROVIDER_NAME}

    text = "".join(chunk["choices"][0]["delta"]["content"] or "" for chunk in chunks)
    assert text == "Hello, world"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"

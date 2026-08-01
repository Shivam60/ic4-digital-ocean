from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from tests.helpers import (
    ANTHROPIC_MOCK_REPLY,
    DONE,
    MODEL_OK,
    MODEL_RATE_LIMITED,
    OLLAMA_MOCK_REPLY,
    OPENAI_MOCK_REPLY,
    anthropic_provider,
    ask,
    error_of,
    ollama_provider,
    openai_provider,
    provider_returning,
    served_by,
    sse_frames,
    streamed_text,
    use_chain,
)


@pytest.fixture(autouse=True)
def _reset_overrides(app: FastAPI) -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


PROVIDERS = [
    pytest.param(openai_provider, OPENAI_MOCK_REPLY, id="openai"),
    pytest.param(ollama_provider, OLLAMA_MOCK_REPLY, id="ollama-native"),
    pytest.param(anthropic_provider, ANTHROPIC_MOCK_REPLY, id="anthropic"),
]


@pytest.mark.parametrize(("build_provider", "expected_reply"), PROVIDERS)
async def test_each_provider_returns_the_same_unified_completion(
    app: FastAPI,
    client: httpx.AsyncClient,
    build_provider,
    expected_reply: str,
) -> None:
    use_chain(app, build_provider("only"))

    response = await ask(client, MODEL_OK)

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["provider"] == "only"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == expected_reply
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"]["total_tokens"] > 0


@pytest.mark.parametrize(("build_provider", "expected_reply"), PROVIDERS)
async def test_each_provider_streams_the_same_unified_sse(
    app: FastAPI,
    client: httpx.AsyncClient,
    build_provider,
    expected_reply: str,
) -> None:
    use_chain(app, build_provider("only"))

    response = await ask(client, MODEL_OK, stream=True)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert served_by(response) == "only"

    frames = sse_frames(response)
    assert frames[-1] == DONE
    assert frames.count(DONE) == 1
    assert streamed_text(response) == expected_reply


@pytest.mark.parametrize(("build_provider", "_reply"), PROVIDERS)
async def test_each_provider_reports_rate_limits_as_transient(
    app: FastAPI,
    client: httpx.AsyncClient,
    build_provider,
    _reply: str,
) -> None:
    use_chain(app, build_provider("only"))

    response = await ask(client, MODEL_RATE_LIMITED)

    assert response.status_code == 503
    error = error_of(response)
    assert error["type"] == "all_providers_failed"
    assert error["attempts"][0]["status_code"] == 429


@pytest.mark.parametrize(("build_provider", "expected_reply"), PROVIDERS)
async def test_fallback_crosses_wire_formats(
    app: FastAPI,
    client: httpx.AsyncClient,
    build_provider,
    expected_reply: str,
) -> None:
    use_chain(app, provider_returning(429, name="primary"), build_provider("backup"))

    response = await ask(client, MODEL_OK, stream=True)

    assert response.status_code == 200
    assert served_by(response) == "backup"
    assert streamed_text(response) == expected_reply

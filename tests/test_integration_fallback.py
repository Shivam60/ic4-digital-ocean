from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from tests.helpers import (
    DONE,
    MODEL_OK,
    MODEL_RATE_LIMITED,
    MODEL_UNKNOWN,
    OPENAI_MOCK_REPLY,
    ask,
    error_of,
    ollama_provider,
    openai_provider,
    provider_returning,
    served_by,
    sse_frames,
    streamed_text,
    unreachable_provider,
    use_chain,
)


@pytest.fixture(autouse=True)
def _reset_overrides(app: FastAPI) -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


async def test_healthy_provider_returns_a_unified_completion(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    use_chain(app, openai_provider("primary"))

    response = await ask(client, MODEL_OK)

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "primary"
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == OPENAI_MOCK_REPLY
    assert body["choices"][0]["finish_reason"] == "stop"


async def test_healthy_provider_streams_unified_sse(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    use_chain(app, openai_provider("primary"))

    response = await ask(client, MODEL_OK, stream=True)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert served_by(response) == "primary"
    assert sse_frames(response)[-1] == DONE
    assert streamed_text(response) == OPENAI_MOCK_REPLY


@pytest.mark.parametrize("status_code", [429, 500, 502, 503])
async def test_transient_failure_falls_back_without_the_client_noticing(
    app: FastAPI, client: httpx.AsyncClient, status_code: int
) -> None:
    use_chain(
        app,
        provider_returning(status_code, name="primary"),
        openai_provider("backup"),
    )

    response = await ask(client, MODEL_OK)

    assert response.status_code == 200
    assert response.json()["provider"] == "backup"
    assert response.json()["choices"][0]["message"]["content"] == OPENAI_MOCK_REPLY


async def test_transient_failure_falls_back_mid_setup_of_a_stream(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    use_chain(app, provider_returning(429, name="primary"), openai_provider("backup"))

    response = await ask(client, MODEL_OK, stream=True)

    assert response.status_code == 200
    assert served_by(response) == "backup"
    assert streamed_text(response) == OPENAI_MOCK_REPLY


async def test_unreachable_provider_falls_back(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    use_chain(app, unreachable_provider("primary"), openai_provider("backup"))

    response = await ask(client, MODEL_OK)

    assert response.status_code == 200
    assert response.json()["provider"] == "backup"


async def test_unknown_model_is_terminal_and_never_retried(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    use_chain(app, openai_provider("primary"), ollama_provider("backup"))

    response = await ask(client, MODEL_UNKNOWN)

    assert response.status_code == 404
    assert error_of(response)["type"] == "upstream_error"
    assert error_of(response)["provider"] == "primary"


async def test_every_provider_rate_limited_reports_the_whole_chain(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    use_chain(app, openai_provider("primary"), ollama_provider("backup"))

    response = await ask(client, MODEL_RATE_LIMITED)

    assert response.status_code == 503
    error = error_of(response)
    assert error["type"] == "all_providers_failed"
    assert error["model"] == MODEL_RATE_LIMITED
    assert [attempt["provider"] for attempt in error["attempts"]] == [
        "primary",
        "backup",
    ]
    assert {attempt["status_code"] for attempt in error["attempts"]} == {429}

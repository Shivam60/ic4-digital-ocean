import json
from typing import Any

import httpx
from fastapi import FastAPI

from app.api.deps import get_model_repository
from app.services.llm.ollama import OllamaService
from app.services.model_repository import ModelRepository
from mock_provider.ollama import app as mock_ollama_app
from mock_provider.openai import app as mock_openai_app

MODEL_OK = "mock/ok"
MODEL_RATE_LIMITED = "mock/429"
MODEL_SERVER_ERROR = "mock/500"
MODEL_UNKNOWN = "mock/does-not-exist"

DONE = "[DONE]"
OPENAI_MOCK_REPLY = "Hello, world from the mock provider."
OLLAMA_MOCK_REPLY = "Hello, world from the ollama mock."


def openai_provider(name: str = "openai_mock") -> OllamaService:
    return _asgi_provider(name, mock_openai_app)


def ollama_provider(name: str = "ollama_mock") -> OllamaService:
    return _asgi_provider(name, mock_ollama_app)


def provider_returning(status_code: int, name: str = "flaky") -> OllamaService:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"error": {"message": "upstream is unhappy", "type": "server_error"}},
        )

    return _transport_provider(name, httpx.MockTransport(handler))


def unreachable_provider(name: str = "dead") -> OllamaService:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return _transport_provider(name, httpx.MockTransport(handler))


def use_chain(app: FastAPI, *providers: OllamaService) -> None:
    repository = ModelRepository(
        services=list(providers),
        routes={},
        default_chain=[provider.name for provider in providers],
    )
    app.dependency_overrides[get_model_repository] = lambda: repository


async def ask(
    client: httpx.AsyncClient, model: str, *, stream: bool = False
) -> httpx.Response:
    return await client.post(
        "/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": stream,
        },
    )


def sse_frames(response: httpx.Response) -> list[str]:
    return [
        line[len("data:") :].strip()
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]


def sse_chunks(response: httpx.Response) -> list[dict[str, Any]]:
    return [json.loads(frame) for frame in sse_frames(response) if frame != DONE]


def streamed_text(response: httpx.Response) -> str:
    return "".join(
        chunk["choices"][0]["delta"].get("content") or ""
        for chunk in sse_chunks(response)
    )


def served_by(response: httpx.Response) -> str:
    return response.headers["x-gateway-provider"]


def error_of(response: httpx.Response) -> dict[str, Any]:
    return response.json()["error"]


def _asgi_provider(name: str, asgi_app: FastAPI) -> OllamaService:
    return _transport_provider(name, httpx.ASGITransport(app=asgi_app))


def _transport_provider(
    name: str, transport: httpx.BaseTransport | httpx.AsyncBaseTransport
) -> OllamaService:
    return OllamaService(
        name=name,
        client=httpx.AsyncClient(transport=transport),
        base_url="http://provider.test/v1",
    )

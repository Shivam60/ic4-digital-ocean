import json
from typing import Any

import httpx
from fastapi import FastAPI

from app.api.deps import get_model_repository
from app.services.llm.anthropic import AnthropicService
from app.services.llm.base import LLMService
from app.services.llm.ollama import OllamaService
from app.services.llm.openai import OpenAIService
from app.services.model_repository import ModelRepository
from mock_provider.anthropic import app as mock_anthropic_app
from mock_provider.ollama import app as mock_ollama_app
from mock_provider.openai import app as mock_openai_app

MODEL_OK = "mock/ok"
MODEL_RATE_LIMITED = "mock/429"
MODEL_SERVER_ERROR = "mock/500"
MODEL_UNKNOWN = "mock/does-not-exist"

DONE = "[DONE]"
OPENAI_MOCK_REPLY = "Hello, world from the mock provider."
OLLAMA_MOCK_REPLY = "Hello, world from the ollama mock."
ANTHROPIC_MOCK_REPLY = "Hello, world from the anthropic mock."


def openai_provider(name: str = "openai_mock") -> OpenAIService:
    return OpenAIService(
        name=name,
        client=_asgi_client(mock_openai_app),
        base_url="http://provider.test/v1",
    )


def ollama_provider(name: str = "ollama_mock") -> OllamaService:
    return OllamaService(
        name=name,
        client=_asgi_client(mock_ollama_app),
        base_url="http://provider.test",
    )


def ollama_compat_provider(name: str = "ollama_compat") -> OpenAIService:
    return OpenAIService(
        name=name,
        client=_asgi_client(mock_ollama_app),
        base_url="http://provider.test/v1",
    )


def anthropic_provider(name: str = "anthropic_mock") -> AnthropicService:
    return AnthropicService(
        name=name,
        client=_asgi_client(mock_anthropic_app),
        base_url="http://provider.test",
        api_key="test-anthropic-key",
    )


def counting_provider(
    name: str = "spy",
) -> tuple[OpenAIService, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-spy",
                "object": "chat.completion",
                "created": 1_700_000_000,
                "model": MODEL_OK,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "spy reply"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 2,
                    "total_tokens": 3,
                },
            },
        )

    service = OpenAIService(
        name=name,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://provider.test/v1",
    )
    return service, calls


def provider_returning(status_code: int, name: str = "flaky") -> OpenAIService:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"error": {"message": "upstream is unhappy", "type": "server_error"}},
        )

    return OpenAIService(
        name=name,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://provider.test/v1",
    )


def unreachable_provider(name: str = "dead") -> OpenAIService:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return OpenAIService(
        name=name,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://provider.test/v1",
    )


def use_chain(app: FastAPI, *providers: LLMService) -> None:
    repository = ModelRepository(
        services=list(providers),
        routes={},
        default_chain=[provider.name for provider in providers],
    )
    app.dependency_overrides[get_model_repository] = lambda: repository


async def ask(
    client: httpx.AsyncClient,
    model: str,
    *,
    stream: bool = False,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await client.post(
        "/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": stream,
        },
        headers=headers,
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


def _asgi_client(asgi_app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=asgi_app))

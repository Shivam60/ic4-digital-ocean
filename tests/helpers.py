import json
from typing import Any

import httpx
from fastapi import FastAPI

from app.api.deps import get_model_router
from app.services.llm.anthropic import AnthropicDialect
from app.services.llm.base import LLMService
from app.services.llm.http_service import HttpLLMService
from app.services.llm.ollama import OllamaDialect
from app.services.llm.openai import OpenAIDialect
from app.services.model_router import ModelRouter
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


def openai_provider(name: str = "openai_mock") -> HttpLLMService:
    return HttpLLMService(
        name=name,
        client=_asgi_client(mock_openai_app),
        base_url="http://provider.test/v1",
        dialect=OpenAIDialect(),
    )


def ollama_provider(name: str = "ollama_mock") -> HttpLLMService:
    return HttpLLMService(
        name=name,
        client=_asgi_client(mock_ollama_app),
        base_url="http://provider.test",
        dialect=OllamaDialect(),
    )


def ollama_compat_provider(name: str = "ollama_compat") -> HttpLLMService:
    return HttpLLMService(
        name=name,
        client=_asgi_client(mock_ollama_app),
        base_url="http://provider.test/v1",
        dialect=OpenAIDialect(),
    )


def anthropic_provider(name: str = "anthropic_mock") -> HttpLLMService:
    return HttpLLMService(
        name=name,
        client=_asgi_client(mock_anthropic_app),
        base_url="http://provider.test",
        dialect=AnthropicDialect(),
        api_key="test-anthropic-key",
    )


def counting_provider(
    name: str = "spy",
) -> tuple[HttpLLMService, list[httpx.Request]]:
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

    service = HttpLLMService(
        name=name,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://provider.test/v1",
        dialect=OpenAIDialect(),
    )
    return service, calls


def provider_returning(status_code: int, name: str = "flaky") -> HttpLLMService:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"error": {"message": "upstream is unhappy", "type": "server_error"}},
        )

    return HttpLLMService(
        name=name,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://provider.test/v1",
        dialect=OpenAIDialect(),
    )


def unreachable_provider(name: str = "dead") -> HttpLLMService:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return HttpLLMService(
        name=name,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://provider.test/v1",
        dialect=OpenAIDialect(),
    )


def use_chain(app: FastAPI, *providers: LLMService) -> None:
    model_router = ModelRouter(
        services=list(providers),
        routes={},
        default_chain=[provider.name for provider in providers],
    )
    app.dependency_overrides[get_model_router] = lambda: model_router


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

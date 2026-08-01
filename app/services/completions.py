from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings
from app.core.errors import GatewayConfigError, UpstreamError
from app.schemas.chat import ChatCompletionRequest
from app.services.llm.openai_compat import (
    SSE_DONE,
    to_unified_chunk,
    to_upstream_payload,
)

PROVIDER_NAME = "openai"


def _headers(settings: Settings) -> dict[str, str]:
    if not settings.openai_api_key:
        raise GatewayConfigError("OPENAI_API_KEY is not configured")
    return {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }


def _url(settings: Settings) -> str:
    return f"{settings.openai_base_url.rstrip('/')}/chat/completions"


async def open_stream(
    client: httpx.AsyncClient,
    settings: Settings,
    request: ChatCompletionRequest,
) -> httpx.Response:
    upstream_request = client.build_request(
        "POST",
        _url(settings),
        json=to_upstream_payload(request, model=request.model, stream=True),
        headers=_headers(settings),
    )
    response = await client.send(upstream_request, stream=True)
    if response.status_code >= 400:
        await response.aread()
        detail = response.text
        await response.aclose()
        raise UpstreamError(PROVIDER_NAME, response.status_code, detail)
    return response


async def iter_stream(response: httpx.Response) -> AsyncIterator[str]:
    try:
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data == SSE_DONE:
                break
            chunk = to_unified_chunk(data, provider=PROVIDER_NAME)
            if chunk is not None:
                yield f"data: {chunk.model_dump_json()}\n\n"
        yield f"data: {SSE_DONE}\n\n"
    finally:
        await response.aclose()

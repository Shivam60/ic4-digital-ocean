from collections.abc import AsyncIterator

import httpx

from app.core.errors import UpstreamError
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.services.llm.anthropic_mapper import (
    AnthropicStreamState,
    to_unified_response,
    to_upstream_payload,
)
from app.services.llm.base import StreamHandle

SSE_DONE = "[DONE]"


class AnthropicService:
    def __init__(
        self,
        name: str,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str | None = None,
        version: str = "2023-06-01",
        default_max_tokens: int = 1024,
    ) -> None:
        self.name = name
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._version = version
        self._default_max_tokens = default_max_tokens

    @property
    def _url(self) -> str:
        return f"{self._base_url}/v1/messages"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": self._version,
        }
        if self._api_key:
            headers["x-api-key"] = self._api_key
        return headers

    def _payload(self, request: ChatCompletionRequest, *, stream: bool) -> dict:
        return to_upstream_payload(
            request,
            model=request.model,
            stream=stream,
            default_max_tokens=self._default_max_tokens,
        )

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        response = await self._client.post(
            self._url,
            json=self._payload(request, stream=False),
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise UpstreamError(self.name, response.status_code, response.text)
        return to_unified_response(response.json(), provider=self.name)

    async def stream(self, request: ChatCompletionRequest) -> StreamHandle:
        upstream_request = self._client.build_request(
            "POST",
            self._url,
            json=self._payload(request, stream=True),
            headers=self._headers(),
        )
        response = await self._client.send(upstream_request, stream=True)
        if response.status_code >= 400:
            await response.aread()
            detail = response.text
            await response.aclose()
            raise UpstreamError(self.name, response.status_code, detail)
        return StreamHandle(provider=self.name, events=self._iter_events(response))

    async def _iter_events(self, response: httpx.Response) -> AsyncIterator[str]:
        state = AnthropicStreamState(self.name)
        try:
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                chunk = state.consume(line[len("data:") :].strip())
                if chunk is not None:
                    yield f"data: {chunk.model_dump_json()}\n\n"
                if state.finished:
                    break
            yield f"data: {SSE_DONE}\n\n"
        finally:
            await response.aclose()

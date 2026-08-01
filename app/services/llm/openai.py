from collections.abc import AsyncIterator

import httpx

from app.core.errors import UpstreamError
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.services.llm.base import StreamHandle
from app.services.llm.openai_mapper import (
    SSE_DONE,
    to_unified_chunk,
    to_unified_response,
    to_upstream_payload,
)


class OpenAIService:
    def __init__(
        self,
        name: str,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str | None = None,
    ) -> None:
        self.name = name
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    @property
    def _url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def complete(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        response = await self._client.post(
            self._url,
            json=to_upstream_payload(request, model=request.model, stream=False),
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise UpstreamError(self.name, response.status_code, response.text)
        return to_unified_response(response.json(), provider=self.name)

    async def stream(self, request: ChatCompletionRequest) -> StreamHandle:
        upstream_request = self._client.build_request(
            "POST",
            self._url,
            json=to_upstream_payload(request, model=request.model, stream=True),
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
        try:
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == SSE_DONE:
                    break
                chunk = to_unified_chunk(data, provider=self.name)
                if chunk is not None:
                    yield f"data: {chunk.model_dump_json()}\n\n"
            yield f"data: {SSE_DONE}\n\n"
        finally:
            await response.aclose()

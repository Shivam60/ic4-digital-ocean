import time
from collections.abc import AsyncIterator

import httpx

from app.core.errors import UpstreamError
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.services.llm.base import StreamHandle
from app.services.llm.ollama_mapper import (
    new_completion_id,
    to_unified_chunk,
    to_unified_response,
    to_upstream_payload,
)

SSE_DONE = "[DONE]"


class OllamaService:
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
        return f"{self._base_url}/api/chat"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        response = await self._client.post(
            self._url,
            json=to_upstream_payload(request, model=request.model, stream=False),
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise UpstreamError(self.name, response.status_code, response.text)
        return to_unified_response(
            response.json(), provider=self.name, completion_id=new_completion_id()
        )

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
        completion_id = new_completion_id()
        created = int(time.time())
        try:
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                chunk = to_unified_chunk(
                    line,
                    provider=self.name,
                    completion_id=completion_id,
                    created=created,
                )
                if chunk is None:
                    continue
                yield f"data: {chunk.model_dump_json()}\n\n"
                if chunk.choices[0].finish_reason is not None:
                    break
            yield f"data: {SSE_DONE}\n\n"
        finally:
            await response.aclose()

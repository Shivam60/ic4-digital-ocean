from collections.abc import AsyncIterator

import httpx

from app.core.errors import UpstreamError
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.services.llm.base import ChunkReader, Dialect, StreamHandle

SSE_DONE = "[DONE]"


class HttpLLMService:
    def __init__(
        self,
        name: str,
        client: httpx.AsyncClient,
        base_url: str,
        dialect: Dialect,
        api_key: str | None = None,
    ) -> None:
        self.name = name
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._dialect = dialect
        self._api_key = api_key

    @property
    def _url(self) -> str:
        return f"{self._base_url}{self._dialect.path}"

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            **self._dialect.headers(self._api_key),
        }

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        response = await self._client.post(
            self._url,
            json=self._dialect.to_payload(request, stream=False),
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise UpstreamError(self.name, response.status_code, response.text)
        return self._dialect.to_response(response.json(), provider=self.name)

    async def stream(self, request: ChatCompletionRequest) -> StreamHandle:
        upstream_request = self._client.build_request(
            "POST",
            self._url,
            json=self._dialect.to_payload(request, stream=True),
            headers=self._headers(),
        )
        response = await self._client.send(upstream_request, stream=True)
        if response.status_code >= 400:
            await response.aread()
            detail = response.text
            await response.aclose()
            raise UpstreamError(self.name, response.status_code, detail)
        return StreamHandle(
            provider=self.name,
            events=self._iter_events(response, self._dialect.new_reader(self.name)),
        )

    async def _iter_events(
        self, response: httpx.Response, reader: ChunkReader
    ) -> AsyncIterator[str]:
        try:
            async for line in response.aiter_lines():
                chunk = reader.read(line)
                if chunk is not None:
                    yield f"data: {chunk.model_dump_json()}\n\n"
                if reader.finished:
                    break
            yield f"data: {SSE_DONE}\n\n"
        finally:
            await response.aclose()

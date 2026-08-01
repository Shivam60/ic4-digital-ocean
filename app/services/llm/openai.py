from typing import Any

from app.schemas.chat import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from app.services.llm.base import ChunkReader
from app.services.llm.openai_mapper import (
    SSE_DONE,
    to_unified_chunk,
    to_unified_response,
    to_upstream_payload,
)


class OpenAIChunkReader:
    def __init__(self, provider: str) -> None:
        self._provider = provider
        self.finished = False

    def read(self, line: str) -> ChatCompletionChunk | None:
        if not line.startswith("data:"):
            return None
        data = line[len("data:") :].strip()
        if data == SSE_DONE:
            self.finished = True
            return None
        return to_unified_chunk(data, provider=self._provider)


class OpenAIDialect:
    path = "/chat/completions"

    def headers(self, api_key: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def to_payload(
        self, request: ChatCompletionRequest, *, stream: bool
    ) -> dict[str, Any]:
        return to_upstream_payload(request, model=request.model, stream=stream)

    def to_response(
        self, body: dict[str, Any], *, provider: str
    ) -> ChatCompletionResponse:
        return to_unified_response(body, provider=provider)

    def new_reader(self, provider: str) -> ChunkReader:
        return OpenAIChunkReader(provider)

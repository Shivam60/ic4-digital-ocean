import time
from typing import Any

from app.schemas.chat import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from app.services.llm.base import ChunkReader
from app.services.llm.ollama_mapper import (
    new_completion_id,
    to_unified_chunk,
    to_unified_response,
    to_upstream_payload,
)


class OllamaChunkReader:
    def __init__(self, provider: str) -> None:
        self._provider = provider
        self._completion_id = new_completion_id()
        self._created = int(time.time())
        self.finished = False

    def read(self, line: str) -> ChatCompletionChunk | None:
        if not line.strip():
            return None
        chunk = to_unified_chunk(
            line,
            provider=self._provider,
            completion_id=self._completion_id,
            created=self._created,
        )
        if chunk is None:
            return None
        if chunk.choices[0].finish_reason is not None:
            self.finished = True
        return chunk


class OllamaDialect:
    path = "/api/chat"

    def headers(self, api_key: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def to_payload(
        self, request: ChatCompletionRequest, *, stream: bool
    ) -> dict[str, Any]:
        return to_upstream_payload(request, model=request.model, stream=stream)

    def to_response(
        self, body: dict[str, Any], *, provider: str
    ) -> ChatCompletionResponse:
        return to_unified_response(
            body, provider=provider, completion_id=new_completion_id()
        )

    def new_reader(self, provider: str) -> ChunkReader:
        return OllamaChunkReader(provider)

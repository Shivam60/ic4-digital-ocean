from typing import Any

from app.schemas.chat import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from app.services.llm.anthropic_mapper import (
    AnthropicStreamState,
    to_unified_response,
    to_upstream_payload,
)
from app.services.llm.base import ChunkReader

DEFAULT_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 1024


class AnthropicChunkReader:
    def __init__(self, provider: str) -> None:
        self._state = AnthropicStreamState(provider)
        self.finished = False

    def read(self, line: str) -> ChatCompletionChunk | None:
        if not line.startswith("data:"):
            return None
        chunk = self._state.consume(line[len("data:") :].strip())
        self.finished = self._state.finished
        return chunk


class AnthropicDialect:
    path = "/v1/messages"

    def __init__(
        self,
        version: str = DEFAULT_VERSION,
        default_max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._version = version
        self._default_max_tokens = default_max_tokens

    def headers(self, api_key: str | None) -> dict[str, str]:
        headers = {"anthropic-version": self._version}
        if api_key:
            headers["x-api-key"] = api_key
        return headers

    def to_payload(
        self, request: ChatCompletionRequest, *, stream: bool
    ) -> dict[str, Any]:
        return to_upstream_payload(
            request,
            model=request.model,
            stream=stream,
            default_max_tokens=self._default_max_tokens,
        )

    def to_response(
        self, body: dict[str, Any], *, provider: str
    ) -> ChatCompletionResponse:
        return to_unified_response(body, provider=provider)

    def new_reader(self, provider: str) -> ChunkReader:
        return AnthropicChunkReader(provider)

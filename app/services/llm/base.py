from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.schemas.chat import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
)


@dataclass
class StreamHandle:
    provider: str
    events: AsyncIterator[str]


class ChunkReader(Protocol):
    finished: bool

    def read(self, line: str) -> ChatCompletionChunk | None: ...


class Dialect(Protocol):
    path: str

    def headers(self, api_key: str | None) -> dict[str, str]: ...

    def to_payload(
        self, request: ChatCompletionRequest, *, stream: bool
    ) -> dict[str, Any]: ...

    def to_response(
        self, body: dict[str, Any], *, provider: str
    ) -> ChatCompletionResponse: ...

    def new_reader(self, provider: str) -> ChunkReader: ...


@runtime_checkable
class LLMService(Protocol):
    name: str

    async def complete(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse: ...

    async def stream(self, request: ChatCompletionRequest) -> StreamHandle: ...

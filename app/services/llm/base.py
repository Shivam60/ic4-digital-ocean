from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse


@dataclass
class StreamHandle:
    provider: str
    events: AsyncIterator[str]


@runtime_checkable
class LLMService(Protocol):
    name: str

    async def complete(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse: ...

    async def stream(self, request: ChatCompletionRequest) -> StreamHandle: ...

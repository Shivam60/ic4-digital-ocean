from typing import Protocol, runtime_checkable

from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse


@runtime_checkable
class LLMService(Protocol):
    name: str

    async def complete(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse: ...

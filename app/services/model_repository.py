from collections.abc import Mapping, Sequence

from app.core.errors import GatewayError
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.services.llm.base import LLMService


class ModelNotRoutableError(GatewayError):
    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(f"no provider is configured for model '{model}'")


class ModelRepository:
    def __init__(
        self,
        services: Sequence[LLMService],
        routes: Mapping[str, str],
        default_provider: str | None = None,
    ) -> None:
        self._services = {service.name: service for service in services}
        self._routes = dict(routes)
        self._default_provider = default_provider

    def resolve_chain(self, model: str) -> list[LLMService]:
        provider = self._routes.get(model, self._default_provider)
        service = self._services.get(provider) if provider else None
        if service is None:
            raise ModelNotRoutableError(model)
        return [service]

    async def complete(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        service = self.resolve_chain(request.model)[0]
        return await service.complete(request)

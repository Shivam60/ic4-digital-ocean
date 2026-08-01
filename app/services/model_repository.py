import logging
from collections.abc import Mapping, Sequence

import httpx

from app.core.errors import (
    AllProvidersFailedError,
    GatewayError,
    ProviderAttempt,
    UpstreamError,
    is_transient_status,
)
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.services.llm.base import LLMService, StreamHandle

logger = logging.getLogger(__name__)


class ModelNotRoutableError(GatewayError):
    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(f"no provider is configured for model '{model}'")


class ModelRepository:
    def __init__(
        self,
        services: Sequence[LLMService],
        routes: Mapping[str, Sequence[str]],
        default_chain: Sequence[str],
    ) -> None:
        self._services = {service.name: service for service in services}
        self._routes = {model: list(chain) for model, chain in routes.items()}
        self._default_chain = list(default_chain)

    def resolve_chain(self, model: str) -> list[LLMService]:
        names = self._routes.get(model, self._default_chain)
        chain = [self._services[name] for name in names if name in self._services]
        if not chain:
            raise ModelNotRoutableError(model)
        return chain

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        attempts: list[ProviderAttempt] = []
        for service in self.resolve_chain(request.model):
            try:
                return await service.complete(request)
            except UpstreamError as exc:
                if not is_transient_status(exc.status_code):
                    raise
                attempts.append(
                    ProviderAttempt(exc.provider, exc.status_code, exc.detail)
                )
            except httpx.TransportError as exc:
                attempts.append(ProviderAttempt(service.name, None, str(exc)))
            last = attempts[-1]
            logger.warning(
                "provider %s failed for model %s (status=%s): %s - falling back",
                last.provider,
                request.model,
                last.status_code or "unreachable",
                last.detail,
            )
        raise AllProvidersFailedError(request.model, attempts)

    async def stream(self, request: ChatCompletionRequest) -> StreamHandle:
        attempts: list[ProviderAttempt] = []
        for service in self.resolve_chain(request.model):
            try:
                return await service.stream(request)
            except UpstreamError as exc:
                if not is_transient_status(exc.status_code):
                    raise
                attempts.append(
                    ProviderAttempt(exc.provider, exc.status_code, exc.detail)
                )
            except httpx.TransportError as exc:
                attempts.append(ProviderAttempt(service.name, None, str(exc)))
            last = attempts[-1]
            logger.warning(
                "provider %s failed before commit for model %s (status=%s): %s"
                " - falling back",
                last.provider,
                request.model,
                last.status_code or "unreachable",
                last.detail,
            )
        raise AllProvidersFailedError(request.model, attempts)

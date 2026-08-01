import httpx

from app.core.config import ProviderConfig, Settings
from app.core.errors import GatewayConfigError
from app.services.llm.anthropic import AnthropicDialect
from app.services.llm.base import Dialect, LLMService
from app.services.llm.http_service import HttpLLMService
from app.services.llm.ollama import OllamaDialect
from app.services.llm.openai import OpenAIDialect


def build_dialect(config: ProviderConfig, settings: Settings) -> Dialect:
    if config.kind == "openai":
        return OpenAIDialect()
    if config.kind == "ollama":
        return OllamaDialect()
    return AnthropicDialect(
        version=settings.anthropic_version,
        default_max_tokens=settings.anthropic_default_max_tokens,
    )


def build_service(
    name: str,
    config: ProviderConfig,
    client: httpx.AsyncClient,
    settings: Settings,
) -> LLMService:
    return HttpLLMService(
        name=name,
        client=client,
        base_url=config.base_url,
        dialect=build_dialect(config, settings),
        api_key=config.api_key,
    )


def build_services(settings: Settings, client: httpx.AsyncClient) -> list[LLMService]:
    services = [
        build_service(name, config, client, settings)
        for name, config in settings.providers.items()
    ]
    _validate_chains(settings)
    return services


def _validate_chains(settings: Settings) -> None:
    known = set(settings.providers)
    referenced = {
        name for chain in settings.model_routes.values() for name in chain
    } | set(settings.default_chain)
    unknown = sorted(referenced - known)
    if unknown:
        raise GatewayConfigError(
            f"routing references unregistered providers: {', '.join(unknown)}"
        )

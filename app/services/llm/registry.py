import httpx

from app.core.config import ProviderConfig, Settings
from app.core.errors import GatewayConfigError
from app.services.llm.anthropic import AnthropicService
from app.services.llm.base import LLMService
from app.services.llm.ollama import OllamaService
from app.services.llm.openai import OpenAIService


def build_service(
    name: str,
    config: ProviderConfig,
    client: httpx.AsyncClient,
    settings: Settings,
) -> LLMService:
    if config.kind == "openai":
        return OpenAIService(
            name=name,
            client=client,
            base_url=config.base_url,
            api_key=config.api_key,
        )
    if config.kind == "ollama":
        return OllamaService(
            name=name,
            client=client,
            base_url=config.base_url,
            api_key=config.api_key,
        )
    return AnthropicService(
        name=name,
        client=client,
        base_url=config.base_url,
        api_key=config.api_key,
        version=settings.anthropic_version,
        default_max_tokens=settings.anthropic_default_max_tokens,
    )


def build_services(
    settings: Settings, client: httpx.AsyncClient
) -> list[LLMService]:
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

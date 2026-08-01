from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderKind = Literal["openai", "ollama", "anthropic"]


class ProviderConfig(BaseModel):
    kind: ProviderKind
    base_url: str
    api_key: str | None = None


class ApiKeyConfig(BaseModel):
    label: str
    key_hash: str
    scopes: list[str] = Field(default_factory=list)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "model-router-gateway"
    environment: Literal["local", "dev", "staging", "prod"] = "local"
    debug: bool = False
    api_prefix: str = "/v1"

    host: str = "127.0.0.1"
    port: int = 8000

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    providers: dict[str, ProviderConfig] = Field(
        default_factory=lambda: {
            "ollama": ProviderConfig(kind="ollama", base_url="http://127.0.0.1:11434")
        }
    )

    default_chain: list[str] = Field(default_factory=lambda: ["ollama"])
    model_routes: dict[str, list[str]] = Field(default_factory=dict)

    # An empty list leaves the gateway open, which is only appropriate locally.
    # A key with no scopes may use every scope.
    api_keys: list[ApiKeyConfig] = Field(default_factory=list)

    anthropic_version: str = "2023-06-01"
    anthropic_default_max_tokens: int = 1024

    # Streaming upstreams must not carry a read timeout: long gaps between tokens are
    # normal. A stalled-but-connected upstream is caught by the first-chunk budget.
    upstream_connect_timeout_seconds: float = 5.0
    upstream_write_timeout_seconds: float = 30.0
    upstream_first_chunk_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

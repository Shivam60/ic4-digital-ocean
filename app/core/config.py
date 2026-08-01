from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"

    # Streaming upstreams must not carry a read timeout: long gaps between tokens are
    # normal. A stalled-but-connected upstream is caught by the first-chunk budget.
    upstream_connect_timeout_seconds: float = 5.0
    upstream_write_timeout_seconds: float = 30.0
    upstream_first_chunk_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

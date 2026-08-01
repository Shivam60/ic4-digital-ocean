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

    app_name: str = "fastapi-async-service"
    environment: Literal["local", "dev", "staging", "prod"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    host: str = "127.0.0.1"
    port: int = 8000

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Timeout applied to outbound HTTP calls made through the shared async client.
    http_client_timeout_seconds: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

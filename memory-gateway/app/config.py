"""Application settings loaded from environment / `.env`."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "memory-gateway"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Upstream (main AI — mandatory for answers)
    upstream_provider: str = "openai"
    upstream_base_url: str = "https://api.openai.com/v1"
    upstream_api_key: str = ""

    # Memory AI (optional compressor — never answers the user)
    memory_ai_enabled: bool = False
    memory_ai_provider: str = "openrouter"
    memory_ai_base_url: str = "https://openrouter.ai/api/v1"
    memory_ai_model: str = "cheap-model"
    memory_ai_api_key: str = ""

    # Context
    context_budget: int = Field(default=8000, ge=1)

    # Storage (SQLite MVP; Redis optional later)
    sqlite_path: str = "./data/memory.db"
    redis_url: str | None = None

    # Gateway security hooks (Phase 7)
    gateway_api_key: str | None = None
    max_request_bytes: int = Field(default=2_000_000, ge=1024)


@lru_cache
def get_settings() -> Settings:
    return Settings()

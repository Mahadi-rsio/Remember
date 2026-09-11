"""Provider factory and public exports."""

from __future__ import annotations

from app.config import Settings, get_settings
from app.providers.base import AIProvider, ProviderResponse
from app.providers.memory_ai import MemoryAIAdapter, create_memory_ai_adapter
from app.providers.openai_compatible import OpenAICompatibleProvider, UpstreamError

__all__ = [
    "AIProvider",
    "MemoryAIAdapter",
    "OpenAICompatibleProvider",
    "ProviderResponse",
    "UpstreamError",
    "create_memory_ai_adapter",
    "create_upstream_provider",
]


def create_upstream_provider(settings: Settings | None = None) -> AIProvider:
    """Build the main (answer) upstream provider from settings."""
    cfg = settings or get_settings()
    return OpenAICompatibleProvider(
        base_url=cfg.upstream_base_url,
        api_key=cfg.upstream_api_key,
    )

"""Upstream / Memory AI provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProviderResponse:
    """Raw upstream HTTP result — gateway must not rewrite the body."""

    status_code: int
    content: bytes
    headers: Mapping[str, str] = field(default_factory=dict)
    media_type: str | None = None


class AIProvider(ABC):
    """Pluggable main-model (and later Memory AI) HTTP adapter."""

    @abstractmethod
    async def chat(self, body: dict[str, Any]) -> ProviderResponse:
        """Non-streaming Chat Completions (`POST /chat/completions`)."""

    @abstractmethod
    async def responses(self, body: dict[str, Any]) -> ProviderResponse:
        """Non-streaming Responses API (`POST /responses`)."""

    @abstractmethod
    async def models(self) -> ProviderResponse:
        """List models (`GET /models`)."""

    @abstractmethod
    def stream(
        self,
        path: str,
        body: dict[str, Any],
    ) -> AsyncIterator[bytes]:
        """
        Stream upstream SSE/body bytes for a POST path (e.g. `chat/completions`).

        Implementations must yield chunks as they arrive (no full-buffer).
        The first await on the returned async iterator establishes the upstream
        connection; callers should use `stream_request` when status/headers
        are needed before iterating.
        """

    @abstractmethod
    async def aclose(self) -> None:
        """Release underlying HTTP resources."""

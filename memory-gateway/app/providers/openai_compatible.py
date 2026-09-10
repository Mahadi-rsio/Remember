"""OpenAI-compatible HTTP adapter (OpenAI, OpenRouter, local, etc.)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from app.providers.base import AIProvider, ProviderResponse

# Hop-by-hop / framing headers must not be forwarded to the client.
_DROP_RESPONSE_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-length",
        "content-encoding",
    }
)


def filter_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Copy upstream headers safe to return to the client."""
    return {
        k: v
        for k, v in headers.items()
        if k.lower() not in _DROP_RESPONSE_HEADERS
    }


class UpstreamError(Exception):
    """Transport-level failure talking to the main upstream (not HTTP 4xx/5xx)."""

    def __init__(self, message: str, *, cause: BaseException | None = None):
        super().__init__(message)
        self.cause = cause


@dataclass(slots=True)
class ProviderStream:
    """Open upstream stream; iterate bytes then close."""

    status_code: int
    headers: dict[str, str]
    media_type: str | None
    _response: httpx.Response

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        try:
            # Prefer raw chunks for true SSE proxies; fall back when the
            # transport (e.g. httpx MockTransport) already buffered content.
            try:
                async for chunk in self._response.aiter_raw():
                    if chunk:
                        yield chunk
                return
            except httpx.StreamConsumed:
                content = self._response.content
                if content:
                    yield content
        finally:
            await self._response.aclose()

    async def aclose(self) -> None:
        await self._response.aclose()


class OpenAICompatibleProvider(AIProvider):
    """Forwards requests to any OpenAI-compatible `base_url`."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = 300.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout, connect=30.0),
        )

    def _auth_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        url = path if path.startswith("/") else f"/{path}"
        try:
            response = await self._client.request(
                method,
                url,
                json=json_body,
                headers=self._auth_headers(),
            )
        except httpx.HTTPError as exc:
            raise UpstreamError(f"upstream request failed: {exc}", cause=exc) from exc

        media_type = response.headers.get("content-type")
        return ProviderResponse(
            status_code=response.status_code,
            content=response.content,
            headers=filter_response_headers(response.headers),
            media_type=media_type,
        )

    async def chat(self, body: dict[str, Any]) -> ProviderResponse:
        return await self._request("POST", "/chat/completions", json_body=body)

    async def responses(self, body: dict[str, Any]) -> ProviderResponse:
        return await self._request("POST", "/responses", json_body=body)

    async def models(self) -> ProviderResponse:
        return await self._request("GET", "/models")

    async def open_stream(self, path: str, body: dict[str, Any]) -> ProviderStream:
        """Start a streaming upstream POST; caller must consume/close `ProviderStream`."""
        url = path if path.startswith("/") else f"/{path}"
        try:
            request = self._client.build_request(
                "POST",
                url,
                json=body,
                headers=self._auth_headers(),
            )
            response = await self._client.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"upstream stream failed: {exc}", cause=exc) from exc

        return ProviderStream(
            status_code=response.status_code,
            headers=filter_response_headers(response.headers),
            media_type=response.headers.get("content-type"),
            _response=response,
        )

    def stream(
        self,
        path: str,
        body: dict[str, Any],
    ) -> AsyncIterator[bytes]:
        """Async generator over raw upstream bytes (no full-buffer)."""

        async def _gen() -> AsyncIterator[bytes]:
            handle = await self.open_stream(path, body)
            async for chunk in handle.aiter_bytes():
                yield chunk

        return _gen()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

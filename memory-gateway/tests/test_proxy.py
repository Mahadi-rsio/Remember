"""Phase 1: transparent proxy — forward correctness, streaming identity, errors."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.providers.base import AIProvider, ProviderResponse
from app.providers.openai_compatible import (
    OpenAICompatibleProvider,
    UpstreamError,
    filter_response_headers,
)


@dataclass
class _FakeStream:
    status_code: int = 200
    headers: dict[str, str] = field(
        default_factory=lambda: {"content-type": "text/event-stream"}
    )
    media_type: str | None = "text/event-stream"
    chunks: list[bytes] = field(default_factory=list)

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk


class FakeProvider(AIProvider):
    """In-memory provider for route-level tests."""

    def __init__(self) -> None:
        self.last_chat_body: dict[str, Any] | None = None
        self.last_responses_body: dict[str, Any] | None = None
        self.chat_result = ProviderResponse(
            status_code=200,
            content=b'{"id":"chat-1","choices":[{"message":{"role":"assistant","content":"hi"}}]}',
            headers={"content-type": "application/json", "x-request-id": "upstream-chat"},
            media_type="application/json",
        )
        self.responses_result = ProviderResponse(
            status_code=200,
            content=b'{"id":"resp-1","output":[]}',
            headers={"content-type": "application/json", "x-request-id": "upstream-resp"},
            media_type="application/json",
        )
        self.models_result = ProviderResponse(
            status_code=200,
            content=b'{"data":[{"id":"gpt-test"}]}',
            headers={"content-type": "application/json"},
            media_type="application/json",
        )
        self.stream_chunks = [
            b'data: {"id":"chunk-1"}\n\n',
            b"data: [DONE]\n\n",
        ]
        self.fail_with: Exception | None = None

    async def chat(self, body: dict[str, Any]) -> ProviderResponse:
        if self.fail_with:
            raise self.fail_with
        self.last_chat_body = body
        return self.chat_result

    async def responses(self, body: dict[str, Any]) -> ProviderResponse:
        if self.fail_with:
            raise self.fail_with
        self.last_responses_body = body
        return self.responses_result

    async def models(self) -> ProviderResponse:
        if self.fail_with:
            raise self.fail_with
        return self.models_result

    def stream(self, path: str, body: dict[str, Any]) -> AsyncIterator[bytes]:
        async def _gen() -> AsyncIterator[bytes]:
            handle = await self.open_stream(path, body)
            async for chunk in handle.aiter_bytes():
                yield chunk

        return _gen()

    async def open_stream(self, path: str, body: dict[str, Any]) -> _FakeStream:
        if self.fail_with:
            raise self.fail_with
        self.last_chat_body = body
        return _FakeStream(chunks=list(self.stream_chunks))

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def client(fake_provider: FakeProvider, tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "proxy.db"))
    get_settings.cache_clear()
    from app.storage.db import reset_engine

    reset_engine()
    app = create_app()
    with TestClient(app) as test_client:
        app.state.upstream_provider = fake_provider
        yield test_client, fake_provider
    reset_engine()
    get_settings.cache_clear()


def test_chat_completions_passthrough(client):
    test_client, provider = client
    payload = {"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]}
    response = test_client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    assert response.content == provider.chat_result.content
    assert response.headers.get("x-request-id") == "upstream-chat"
    assert provider.last_chat_body == payload
    assert response.json()["choices"][0]["message"]["content"] == "hi"


def test_responses_passthrough(client):
    test_client, provider = client
    payload = {"model": "gpt-test", "input": "hello"}
    response = test_client.post("/v1/responses", json=payload)

    assert response.status_code == 200
    assert response.content == provider.responses_result.content
    assert response.headers.get("x-request-id") == "upstream-resp"
    assert provider.last_responses_body == payload


def test_models_passthrough(client):
    test_client, provider = client
    response = test_client.get("/v1/models")

    assert response.status_code == 200
    assert response.content == provider.models_result.content
    assert response.json()["data"][0]["id"] == "gpt-test"


def test_streaming_identity(client):
    test_client, provider = client
    payload = {
        "model": "gpt-test",
        "stream": True,
        "messages": [{"role": "user", "content": "stream please"}],
    }
    with test_client.stream("POST", "/v1/chat/completions", json=payload) as response:
        assert response.status_code == 200
        body = b"".join(response.iter_bytes())

    assert body == b"".join(provider.stream_chunks)
    assert provider.last_chat_body == payload


def test_upstream_http_error_passthrough(client):
    test_client, provider = client
    provider.chat_result = ProviderResponse(
        status_code=401,
        content=b'{"error":{"message":"Invalid API key","type":"invalid_request_error"}}',
        headers={"content-type": "application/json"},
        media_type="application/json",
    )
    response = test_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": []},
    )
    assert response.status_code == 401
    assert response.content == provider.chat_result.content
    assert response.json()["error"]["message"] == "Invalid API key"


def test_upstream_unreachable_maps_to_502(client):
    test_client, provider = client
    provider.fail_with = UpstreamError("connection refused")
    response = test_client.post(
        "/v1/chat/completions",
        json={"model": "gpt-test", "messages": []},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_unreachable"


def test_request_too_large(client, monkeypatch):
    _test_client, _provider = client
    monkeypatch.setenv("MAX_REQUEST_BYTES", "1024")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as fresh:
        fresh.app.state.upstream_provider = FakeProvider()
        big = {
            "model": "x",
            "messages": [{"role": "user", "content": "y" * 2000}],
        }
        response = fresh.post("/v1/chat/completions", json=big)
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "request_too_large"
    get_settings.cache_clear()


def test_invalid_json(client):
    test_client, _provider = client
    response = test_client.post(
        "/v1/chat/completions",
        content=b"{not-json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_json"


def test_filter_response_headers_drops_hop_by_hop():
    filtered = filter_response_headers(
        {
            "Content-Type": "application/json",
            "Transfer-Encoding": "chunked",
            "X-Request-Id": "abc",
            "Content-Length": "12",
        }
    )
    lower = {k.lower(): v for k, v in filtered.items()}
    assert "transfer-encoding" not in lower
    assert "content-length" not in lower
    assert lower["x-request-id"] == "abc"


@pytest.mark.asyncio
async def test_openai_compatible_provider_forwards_with_mock_transport():
    upstream_body = {"id": "cmpl-1", "choices": [{"message": {"content": "pong"}}]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers.get("Authorization") == "Bearer test-key"
        payload = json.loads(request.content.decode())
        assert payload["messages"][0]["content"] == "ping"
        return httpx.Response(
            200,
            json=upstream_body,
            headers={"x-upstream": "yes", "content-type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://example.test/v1"
    ) as http:
        provider = OpenAICompatibleProvider(
            base_url="https://example.test/v1",
            api_key="test-key",
            client=http,
        )
        result = await provider.chat(
            {"model": "gpt-test", "messages": [{"role": "user", "content": "ping"}]}
        )

    assert result.status_code == 200
    assert json.loads(result.content) == upstream_body
    assert result.headers.get("x-upstream") == "yes"


@pytest.mark.asyncio
async def test_openai_compatible_stream_identity():
    sse = b'data: {"id":"1"}\n\ndata: [DONE]\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        assert b'"stream": true' in request.content or b'"stream":true' in request.content
        return httpx.Response(
            200,
            content=sse,
            headers={"content-type": "text/event-stream"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://example.test/v1"
    ) as http:
        provider = OpenAICompatibleProvider(
            base_url="https://example.test/v1",
            api_key="k",
            client=http,
        )
        handle = await provider.open_stream(
            "/chat/completions",
            {"model": "gpt-test", "stream": True, "messages": []},
        )
        chunks: list[bytes] = []
        async for chunk in handle.aiter_bytes():
            chunks.append(chunk)

    assert b"".join(chunks) == sse


@pytest.mark.asyncio
async def test_openai_compatible_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://example.test/v1"
    ) as http:
        provider = OpenAICompatibleProvider(
            base_url="https://example.test/v1",
            api_key="k",
            client=http,
        )
        with pytest.raises(UpstreamError):
            await provider.chat({"model": "x", "messages": []})

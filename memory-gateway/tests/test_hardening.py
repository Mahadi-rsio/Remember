"""Phase 7 hardening tests: auth, rate limiting, secret redaction, failure isolation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.rate_limit import reset_rate_limit_state
from app.config import get_settings
from app.main import create_app
from app.providers.base import AIProvider, ProviderResponse
from app.providers.openai_compatible import UpstreamError


# ---------------------------------------------------------------------------
# Shared fake provider (copied from test_proxy.py to keep tests isolated)
# ---------------------------------------------------------------------------


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

    async def aclose(self) -> None:
        pass


class FakeProvider(AIProvider):
    def __init__(self) -> None:
        self.chat_called = False
        self.fail_with: Exception | None = None
        self.chat_result = ProviderResponse(
            status_code=200,
            content=b'{"id":"chat-1","choices":[{"message":{"role":"assistant","content":"hi"}}]}',
            headers={"content-type": "application/json"},
            media_type="application/json",
        )
        self.models_result = ProviderResponse(
            status_code=200,
            content=b'{"data":[{"id":"gpt-test"}]}',
            headers={"content-type": "application/json"},
            media_type="application/json",
        )

    async def chat(self, body: dict[str, Any]) -> ProviderResponse:
        if self.fail_with:
            raise self.fail_with
        self.chat_called = True
        return self.chat_result

    async def responses(self, body: dict[str, Any]) -> ProviderResponse:
        if self.fail_with:
            raise self.fail_with
        return self.chat_result

    async def models(self) -> ProviderResponse:
        return self.models_result

    async def open_stream(self, path: str, body: dict[str, Any]) -> _FakeStream:
        if self.fail_with:
            raise self.fail_with
        return _FakeStream()

    def stream(self, path: str, body: dict[str, Any]):
        async def _gen():
            handle = _FakeStream()
            async for chunk in handle.aiter_bytes():
                yield chunk

        return _gen()

    async def aclose(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """Reset rate-limit state between tests."""
    reset_rate_limit_state()
    yield
    reset_rate_limit_state()


def _make_client(monkeypatch, tmp_path, extra_env: dict[str, str] | None = None):
    """Create a fresh TestClient with an isolated DB and optional env overrides."""
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    for key, value in (extra_env or {}).items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    from app.storage.db import reset_engine

    reset_engine()
    app = create_app()
    provider = FakeProvider()
    client = TestClient(app)
    client.__enter__()
    app.state.upstream_provider = provider
    return client, provider, app


@pytest.fixture
def clean_client(monkeypatch, tmp_path):
    from app.storage.db import reset_engine

    client, provider, app = _make_client(monkeypatch, tmp_path)
    yield client, provider, app
    client.__exit__(None, None, None)
    reset_engine()
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


def test_auth_required_when_key_set(monkeypatch, tmp_path):
    """When GATEWAY_API_KEY is set, unauthenticated request → 401."""
    from app.storage.db import reset_engine

    client, provider, app = _make_client(
        monkeypatch, tmp_path, {"GATEWAY_API_KEY": "secret-key-123"}
    )
    try:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 401, response.text
        body = response.json()
        assert body["error"]["code"] == "invalid_api_key"
        assert not provider.chat_called
    finally:
        client.__exit__(None, None, None)
        reset_engine()
        get_settings.cache_clear()


def test_auth_passes_with_correct_key(monkeypatch, tmp_path):
    """Correct Bearer token → request passes through."""
    from app.storage.db import reset_engine

    client, provider, app = _make_client(
        monkeypatch, tmp_path, {"GATEWAY_API_KEY": "secret-key-123"}
    )
    try:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]},
            headers={"Authorization": "Bearer secret-key-123"},
        )
        assert response.status_code == 200, response.text
        assert provider.chat_called
    finally:
        client.__exit__(None, None, None)
        reset_engine()
        get_settings.cache_clear()


def test_auth_passes_with_api_key_header(monkeypatch, tmp_path):
    """Correct X-API-Key header → request passes through."""
    from app.storage.db import reset_engine

    client, provider, app = _make_client(
        monkeypatch, tmp_path, {"GATEWAY_API_KEY": "secret-key-123"}
    )
    try:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]},
            headers={"X-API-Key": "secret-key-123"},
        )
        assert response.status_code == 200, response.text
        assert provider.chat_called
    finally:
        client.__exit__(None, None, None)
        reset_engine()
        get_settings.cache_clear()


def test_no_auth_when_key_not_set(monkeypatch, tmp_path):
    """No GATEWAY_API_KEY configured → all unauthenticated requests pass."""
    from app.storage.db import reset_engine

    client, provider, app = _make_client(monkeypatch, tmp_path)
    try:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 200, response.text
        assert provider.chat_called
    finally:
        client.__exit__(None, None, None)
        reset_engine()
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Rate limiting tests
# ---------------------------------------------------------------------------


def test_rate_limit_triggers_429(monkeypatch, tmp_path):
    """RATE_LIMIT_RPM=1 → second request within a minute returns 429."""
    from app.storage.db import reset_engine

    client, provider, app = _make_client(
        monkeypatch, tmp_path, {"RATE_LIMIT_RPM": "1"}
    )
    payload = {"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]}
    try:
        r1 = client.post("/v1/chat/completions", json=payload)
        assert r1.status_code == 200, r1.text

        r2 = client.post("/v1/chat/completions", json=payload)
        assert r2.status_code == 429, r2.text
        body = r2.json()
        assert body["error"]["code"] == "rate_limit_exceeded"
    finally:
        client.__exit__(None, None, None)
        reset_engine()
        get_settings.cache_clear()


def test_rate_limit_disabled_by_default(monkeypatch, tmp_path):
    """RATE_LIMIT_RPM=0 (default) → no limiting, many requests all succeed."""
    from app.storage.db import reset_engine

    client, provider, app = _make_client(monkeypatch, tmp_path)
    payload = {"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]}
    try:
        for _ in range(5):
            r = client.post("/v1/chat/completions", json=payload)
            assert r.status_code == 200, r.text
    finally:
        client.__exit__(None, None, None)
        reset_engine()
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Secret redaction tests
# ---------------------------------------------------------------------------


def test_secret_redaction_in_logs():
    """Log a string containing a sk-* key — it must appear as [REDACTED] in output."""
    from io import StringIO

    from app.logging_setup import _SecretFilter

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(_SecretFilter(extra_secrets=["my-raw-api-key"]))
    handler.setFormatter(logging.Formatter("%(message)s"))

    test_logger = logging.getLogger("test_redaction")
    test_logger.handlers.clear()
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.DEBUG)
    test_logger.propagate = False

    test_logger.info("key is sk-abc12345 and also Bearer tokenvalue123")
    test_logger.info("raw secret my-raw-api-key should be gone too")

    output = stream.getvalue()
    assert "sk-abc12345" not in output, "sk- key leaked!"
    assert "Bearer tokenvalue123" not in output, "Bearer token leaked!"
    assert "my-raw-api-key" not in output, "raw API key leaked!"
    assert "[REDACTED]" in output


# ---------------------------------------------------------------------------
# Failure isolation tests
# ---------------------------------------------------------------------------


def test_upstream_failure_isolation(monkeypatch, tmp_path):
    """Archive failure must NOT prevent the main AI call from succeeding.

    We patch archive_request_async (the inner call) so that _archive_inbound's
    own try/except swallows the exception — proving isolation is working as designed.
    """
    from app.storage.db import reset_engine

    client, provider, app = _make_client(monkeypatch, tmp_path)
    try:
        # Patch the lower-level async archive to raise
        async def _boom(*args, **kwargs):
            raise RuntimeError("archive exploded")

        with patch("app.api.proxy.archive_request_async", side_effect=_boom):
            response = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]},
            )
        # Main AI should still be called and respond 200
        assert response.status_code == 200, response.text
        assert provider.chat_called
    finally:
        client.__exit__(None, None, None)
        reset_engine()
        get_settings.cache_clear()


def test_internal_error_safe_response(monkeypatch, tmp_path):
    """Unhandled exception in route → 500 with proper JSON, no traceback."""
    from app.storage.db import reset_engine

    client, provider, app = _make_client(monkeypatch, tmp_path)
    try:
        # Make _prepare_upstream_body raise unexpectedly
        async def _explode(*args, **kwargs):
            raise RuntimeError("totally unexpected crash")

        with patch("app.api.proxy._prepare_upstream_body", side_effect=_explode):
            response = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-test", "messages": [{"role": "user", "content": "hi"}]},
            )
        assert response.status_code == 500, response.text
        body = response.json()
        assert body["error"]["code"] == "internal_error"
        assert body["error"]["type"] == "gateway_error"
        # Must not leak traceback text
        assert "Traceback" not in response.text
        assert "RuntimeError" not in response.text
    finally:
        client.__exit__(None, None, None)
        reset_engine()
        get_settings.cache_clear()

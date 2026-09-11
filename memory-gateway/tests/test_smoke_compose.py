"""End-to-end docker compose smoke test.

Skipped by default — requires a running `docker compose up` environment.

To run manually:
    cd /workspaces/Remember/memory-gateway
    docker compose up -d
    # wait for the service to be healthy
    python -m pytest tests/test_smoke_compose.py -v --no-header -rN \\
        --override-ini="addopts=" -k "smoke"

Or un-skip by removing the pytest.mark.skip decorator below and ensuring
GATEWAY_SMOKE_URL is set (defaults to http://localhost:8000).
"""

from __future__ import annotations

import os

import pytest
import requests


GATEWAY_URL = os.environ.get("GATEWAY_SMOKE_URL", "http://localhost:8000")


@pytest.mark.skip(reason="requires docker compose — run manually (see module docstring)")
def test_smoke_health():
    """Gateway must return HTTP 200 on GET /health."""
    resp = requests.get(f"{GATEWAY_URL}/health", timeout=10)
    assert resp.status_code == 200, f"health returned {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("status") in ("ok", "degraded"), f"unexpected status: {body}"


@pytest.mark.skip(reason="requires docker compose — run manually (see module docstring)")
def test_smoke_models():
    """Gateway must proxy GET /v1/models and return HTTP 200."""
    resp = requests.get(f"{GATEWAY_URL}/v1/models", timeout=10)
    # Accept 200 or 401 (auth configured) — both indicate the gateway is up.
    assert resp.status_code in (200, 401), (
        f"/v1/models returned unexpected status {resp.status_code}: {resp.text}"
    )


@pytest.mark.skip(reason="requires docker compose — run manually (see module docstring)")
def test_smoke_chat_completions():
    """Gateway must proxy POST /v1/chat/completions (may fail with 4xx if no valid key)."""
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "ping"}],
    }
    headers = {}
    api_key = os.environ.get("GATEWAY_API_KEY") or os.environ.get("UPSTREAM_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    resp = requests.post(
        f"{GATEWAY_URL}/v1/chat/completions",
        json=payload,
        headers=headers,
        timeout=30,
    )
    # We only verify the gateway is alive and responds with parseable JSON.
    assert resp.status_code < 600, f"smoke: unexpected status {resp.status_code}"
    assert resp.headers.get("content-type", "").startswith("application/json"), (
        f"smoke: expected JSON, got {resp.headers.get('content-type')}"
    )

"""Sliding-window rate limiter dependency for /v1/* proxy routes.

Config: RATE_LIMIT_RPM (requests per minute, default 0 = disabled).
Keyed per client IP (X-Forwarded-For first, then client.host).
Returns 429 with OpenAI-compatible error JSON when limit is exceeded.
Async-safe via asyncio.Lock per IP bucket.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import get_settings

# Global state: per-IP deque of request timestamps (float seconds)
_buckets: dict[str, deque[float]] = {}
_bucket_locks: dict[str, asyncio.Lock] = {}
_global_lock = asyncio.Lock()


async def _get_bucket_lock(ip: str) -> asyncio.Lock:
    """Return (creating if needed) the per-IP asyncio.Lock."""
    async with _global_lock:
        if ip not in _bucket_locks:
            _bucket_locks[ip] = asyncio.Lock()
            _buckets[ip] = deque()
        return _bucket_locks[ip]


def _client_ip(request: Request) -> str:
    """Resolve client IP: prefer X-Forwarded-For, fall back to client.host."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _rate_limit_error() -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "message": "Rate limit exceeded; please retry after a minute",
                "type": "requests",
                "code": "rate_limit_exceeded",
            }
        },
        headers={"Retry-After": "60"},
    )


async def check_rate_limit(request: Request) -> JSONResponse | None:
    """FastAPI dependency: enforce RATE_LIMIT_RPM if configured.

    Uses a sliding 60-second window per IP. Returns None (allow) or
    a 429 JSONResponse (deny).
    """
    settings = get_settings()
    rpm = getattr(settings, "rate_limit_rpm", 0)
    if rpm <= 0:
        return None  # Disabled

    ip = _client_ip(request)
    lock = await _get_bucket_lock(ip)

    async with lock:
        now = time.monotonic()
        window_start = now - 60.0
        bucket = _buckets[ip]

        # Evict timestamps older than 60 seconds
        while bucket and bucket[0] < window_start:
            bucket.popleft()

        if len(bucket) >= rpm:
            return _rate_limit_error()

        bucket.append(now)
        return None


def reset_rate_limit_state() -> None:
    """Clear all rate limit buckets — intended for test teardown only."""
    global _buckets, _bucket_locks
    _buckets = {}
    _bucket_locks = {}

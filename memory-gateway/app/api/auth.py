"""API authentication dependency for /v1/* proxy routes.

If GATEWAY_API_KEY is set, require either:
  - Authorization: Bearer <key>
  - X-API-Key: <key>

If GATEWAY_API_KEY is not set, all requests are allowed (open mode).
Returns 401 with OpenAI-compatible error JSON on auth failure.
"""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from app.config import get_settings


def _auth_error() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "message": "Unauthorized: valid API key required",
                "type": "invalid_request_error",
                "code": "invalid_api_key",
            }
        },
    )


async def require_api_key(request: Request) -> JSONResponse | None:
    """FastAPI dependency: enforce GATEWAY_API_KEY if configured.

    Raises HTTP 401 (as a JSONResponse) when authentication fails.
    Returns None when auth is disabled or the key is valid.
    """
    settings = get_settings()
    expected = settings.gateway_api_key
    if not expected:
        # Open mode — no key configured, allow everything.
        return None

    # Check Authorization: Bearer <key>
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token == expected:
            return None

    # Check X-API-Key: <key>
    api_key_header = request.headers.get("x-api-key", "")
    if api_key_header == expected:
        return None

    return _auth_error()

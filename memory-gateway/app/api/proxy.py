"""OpenAI-compatible transparent proxy routes (Phase 1 — no memory yet)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.config import get_settings
from app.providers.base import AIProvider, ProviderResponse
from app.providers.openai_compatible import UpstreamError

router = APIRouter(prefix="/v1", tags=["proxy"])


def _get_provider(request: Request) -> AIProvider:
    provider = getattr(request.app.state, "upstream_provider", None)
    if provider is None:
        raise RuntimeError("upstream provider not configured")
    return provider


def _too_large() -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={
            "error": {
                "message": "Request body exceeds MAX_REQUEST_BYTES",
                "type": "invalid_request_error",
                "code": "request_too_large",
            }
        },
    )


def _bad_json() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "message": "Request body must be valid JSON",
                "type": "invalid_request_error",
                "code": "invalid_json",
            }
        },
    )


def _upstream_unavailable(_exc: UpstreamError) -> JSONResponse:
    # Do not leak API keys or internal URLs with credentials.
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "message": "Failed to reach upstream AI provider",
                "type": "upstream_error",
                "code": "upstream_unreachable",
            }
        },
    )


async def _read_json_body(request: Request) -> dict[str, Any] | JSONResponse:
    settings = get_settings()
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > settings.max_request_bytes:
                return _too_large()
        except ValueError:
            pass

    raw = await request.body()
    if len(raw) > settings.max_request_bytes:
        return _too_large()
    try:
        body = json.loads(raw.decode("utf-8") if raw else "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _bad_json()
    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": "Request body must be a JSON object",
                    "type": "invalid_request_error",
                    "code": "invalid_json",
                }
            },
        )
    return body


def _passthrough_response(result: ProviderResponse) -> Response:
    headers = dict(result.headers)
    media = result.media_type or headers.pop("content-type", None) or "application/json"
    headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
    return Response(
        content=result.content,
        status_code=result.status_code,
        headers=headers,
        media_type=media,
    )


@router.post("/chat/completions")
async def chat_completions(request: Request) -> Response:
    body = await _read_json_body(request)
    if isinstance(body, JSONResponse):
        return body

    provider = _get_provider(request)
    if body.get("stream"):
        return await _stream_proxy(provider, "/chat/completions", body)

    try:
        result = await provider.chat(body)
    except UpstreamError as exc:
        return _upstream_unavailable(exc)
    return _passthrough_response(result)


@router.post("/responses")
async def responses(request: Request) -> Response:
    body = await _read_json_body(request)
    if isinstance(body, JSONResponse):
        return body

    provider = _get_provider(request)
    if body.get("stream"):
        return await _stream_proxy(provider, "/responses", body)

    try:
        result = await provider.responses(body)
    except UpstreamError as exc:
        return _upstream_unavailable(exc)
    return _passthrough_response(result)


@router.get("/models")
async def models(request: Request) -> Response:
    provider = _get_provider(request)
    try:
        result = await provider.models()
    except UpstreamError as exc:
        return _upstream_unavailable(exc)
    return _passthrough_response(result)


async def _stream_proxy(
    provider: AIProvider,
    path: str,
    body: dict[str, Any],
) -> Response:
    open_stream = getattr(provider, "open_stream", None)
    if open_stream is None:
        return JSONResponse(
            status_code=501,
            content={
                "error": {
                    "message": "Streaming not supported by configured provider",
                    "type": "upstream_error",
                    "code": "stream_unsupported",
                }
            },
        )

    try:
        handle = await open_stream(path, body)
    except UpstreamError as exc:
        return _upstream_unavailable(exc)

    headers = {k: v for k, v in handle.headers.items() if k.lower() != "content-type"}
    media = handle.media_type or "text/event-stream"

    return StreamingResponse(
        handle.aiter_bytes(),
        status_code=handle.status_code,
        headers=headers,
        media_type=media,
    )

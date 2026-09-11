"""OpenAI-compatible transparent proxy routes (Phase 2: archive + delta, then forward).

Phase 7 additions:
- Auth dependency (require_api_key) on all /v1/* routes
- Rate-limit dependency (check_rate_limit) on all /v1/* routes
- Safe 500 catch-all in chat_completions() and responses()
- Strengthened failure isolation for archive / context preparation
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.api.auth import require_api_key
from app.api.rate_limit import check_rate_limit
from app.config import get_settings
from app.context.compiler import compile_context
from app.memory.isolation import derive_isolation_keys
from app.providers.base import AIProvider, ProviderResponse
from app.providers.openai_compatible import ProviderStream, UpstreamError
from app.storage.archive import archive_request, archive_request_async

logger = logging.getLogger(__name__)
trace_logger = logging.getLogger("gateway.trace")

router = APIRouter(prefix="/v1", tags=["proxy"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _archive_inbound(request: Request, body: dict[str, Any]) -> None:
    """Persist raw messages / compute delta. Never raises into the hot path."""
    try:
        memory_ai = getattr(request.app.state, "memory_ai_adapter", None)
        delta = await archive_request_async(body, headers=request.headers, memory_ai=memory_ai)
        if delta is not None and logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "archive conversation=%s new=%s dup=%s",
                delta.conversation_id,
                len(delta.new_messages),
                len(delta.duplicate_messages),
            )
    except Exception:
        # archive_request already fail-opens; belt-and-suspenders for the route.
        logger.exception("unexpected archive error")


def _clip_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n... [truncated {len(text) - limit} chars]"


def _log_upstream_context(path: str, body: dict[str, Any]) -> None:
    """Log the exact context (messages) being sent to the main AI."""
    settings = get_settings()
    if not settings.log_bodies or not trace_logger.isEnabledFor(logging.INFO):
        return
    messages = body.get("messages")
    count = len(messages) if isinstance(messages, list) else 0
    payload = (
        json.dumps(messages, ensure_ascii=False, indent=2, default=str)
        if isinstance(messages, list)
        else "<no messages field>"
    )
    trace_logger.info(
        "=== CONTEXT -> AI path=%s model=%s messages=%d\n%s",
        path,
        body.get("model"),
        count,
        _clip_text(payload, settings.log_payload_max_bytes),
    )


def _log_upstream_response(path: str, status_code: int, content: bytes) -> None:
    """Log the raw response received from the main AI."""
    settings = get_settings()
    if not settings.log_bodies or not trace_logger.isEnabledFor(logging.INFO):
        return
    trace_logger.info(
        "=== RESPONSE <- AI path=%s status=%s bytes=%d\n%s",
        path,
        status_code,
        len(content),
        _clip_text(content.decode("utf-8", "replace"), settings.log_payload_max_bytes),
    )


async def _trace_stream(
    handle: ProviderStream,
    path: str,
) -> AsyncIterator[bytes]:
    """Pass stream bytes through unchanged; log the full body once done."""
    chunks: list[bytes] = []
    try:
        async for chunk in handle.aiter_bytes():
            chunks.append(chunk)
            yield chunk
    finally:
        try:
            _log_upstream_response(path, handle.status_code, b"".join(chunks))
        except Exception:
            logger.exception("failed to log streamed response")
        try:
            await handle.aclose()
        except Exception:
            pass


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


def _internal_error() -> JSONResponse:
    """Return a safe 500 response that never leaks tracebacks or secrets."""
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": "Internal gateway error",
                "type": "gateway_error",
                "code": "internal_error",
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


async def _prepare_upstream_body(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Compile context; fall back to original body on ANY failure.

    Failure isolation: Memory AI / SQLite / retrieval failures must never
    prevent the main AI from being called.
    """
    messages = body.get("messages")
    if not isinstance(messages, list):
        return body

    try:
        conversation_id, _ = derive_isolation_keys(body, request.headers)
        memory_ai = getattr(request.app.state, "memory_ai_adapter", None)
        raw_budget = body.get("context_budget") or request.headers.get("x-context-budget")
        budget_val: int | None = None
        if raw_budget is not None:
            try:
                budget_val = int(raw_budget)
            except (ValueError, TypeError):
                pass

        compile_res = await compile_context(
            messages,
            conversation_id=conversation_id,
            budget=budget_val,
            memory_ai=memory_ai,
        )
        upstream_body = dict(body)
        upstream_body["messages"] = compile_res.messages
        return upstream_body
    except Exception:
        logger.exception("Context compilation failed; forwarding original body to main AI")
        return body


# ---------------------------------------------------------------------------
# Auth + rate-limit dependency helpers
# ---------------------------------------------------------------------------


async def _check_auth(request: Request) -> JSONResponse | None:
    """Thin wrapper so tests can monkeypatch require_api_key."""
    return await require_api_key(request)


async def _check_rate_limit(request: Request) -> JSONResponse | None:
    """Thin wrapper so tests can monkeypatch check_rate_limit."""
    return await check_rate_limit(request)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/chat/completions")
async def chat_completions(request: Request) -> Response:
    try:
        auth_resp = await _check_auth(request)
        if auth_resp is not None:
            return auth_resp
        rl_resp = await _check_rate_limit(request)
        if rl_resp is not None:
            return rl_resp

        body = await _read_json_body(request)
        if isinstance(body, JSONResponse):
            return body

        await _archive_inbound(request, body)
        upstream_body = await _prepare_upstream_body(request, body)
        _log_upstream_context("/chat/completions", upstream_body)

        provider = _get_provider(request)
        if upstream_body.get("stream"):
            return await _stream_proxy(provider, "/chat/completions", upstream_body)

        try:
            result = await provider.chat(upstream_body)
        except UpstreamError as exc:
            trace_logger.error("upstream call failed path=/chat/completions: %s", exc)
            return _upstream_unavailable(exc)
        _log_upstream_response("/chat/completions", result.status_code, result.content)
        return _passthrough_response(result)
    except Exception:
        logger.exception("unhandled exception in chat_completions")
        return _internal_error()


@router.post("/responses")
async def responses(request: Request) -> Response:
    try:
        auth_resp = await _check_auth(request)
        if auth_resp is not None:
            return auth_resp
        rl_resp = await _check_rate_limit(request)
        if rl_resp is not None:
            return rl_resp

        body = await _read_json_body(request)
        if isinstance(body, JSONResponse):
            return body

        await _archive_inbound(request, body)
        upstream_body = await _prepare_upstream_body(request, body)
        _log_upstream_context("/responses", upstream_body)

        provider = _get_provider(request)
        if upstream_body.get("stream"):
            return await _stream_proxy(provider, "/responses", upstream_body)

        try:
            result = await provider.responses(upstream_body)
        except UpstreamError as exc:
            trace_logger.error("upstream call failed path=/responses: %s", exc)
            return _upstream_unavailable(exc)
        _log_upstream_response("/responses", result.status_code, result.content)
        return _passthrough_response(result)
    except Exception:
        logger.exception("unhandled exception in responses")
        return _internal_error()


@router.get("/models")
async def models(request: Request) -> Response:
    auth_resp = await _check_auth(request)
    if auth_resp is not None:
        return auth_resp
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
        _trace_stream(handle, path),
        status_code=handle.status_code,
        headers=headers,
        media_type=media,
    )

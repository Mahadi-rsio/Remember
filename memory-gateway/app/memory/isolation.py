"""Conversation / user isolation key derivation."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _header_value(headers: Mapping[str, str], *names: str) -> str | None:
    lower = {k.lower(): v for k, v in headers.items()}
    for name in names:
        raw = lower.get(name.lower())
        if raw is not None:
            return _as_str(raw)
    return None


def extract_user_key(
    body: dict[str, Any],
    headers: Mapping[str, str] | None = None,
) -> str | None:
    """Stable user isolation key when the client supplies one."""
    headers = headers or {}
    for key in (
        _header_value(headers, "x-user-id", "x-user"),
        _as_str(body.get("user")),
        _as_str((body.get("metadata") or {}).get("user_id"))
        if isinstance(body.get("metadata"), dict)
        else None,
        _as_str((body.get("metadata") or {}).get("user"))
        if isinstance(body.get("metadata"), dict)
        else None,
    ):
        if key:
            return key
    return None


def extract_explicit_conversation_id(
    body: dict[str, Any],
    headers: Mapping[str, str] | None = None,
) -> str | None:
    headers = headers or {}
    meta = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    for key in (
        _header_value(headers, "x-conversation-id", "x-session-id"),
        _as_str(body.get("conversation_id")),
        _as_str(body.get("conversation")),
        _as_str(body.get("session_id")),
        _as_str(meta.get("conversation_id")),
        _as_str(meta.get("session_id")),
    ):
        if key:
            return key
    return None


def _fingerprint_messages(messages: list[Any]) -> str:
    """
    Deterministic fingerprint of the conversation seed (first message only).

    Using only the first turn keeps the derived id stable as the client
    appends later messages to the same thread.
    """
    seed = messages[:1]
    canonical = json.dumps(seed, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def derive_isolation_keys(
    body: dict[str, Any],
    headers: Mapping[str, str] | None = None,
) -> tuple[str, str | None]:
    """
    Return (conversation_id, user_key).

    Preference order for conversation_id:
    1. Explicit client/provider conversation id
    2. user_key + fingerprint of first messages (stable across growing turns)
    3. Fingerprint alone when no user key
    """
    headers = headers or {}
    user_key = extract_user_key(body, headers)
    explicit = extract_explicit_conversation_id(body, headers)
    if explicit:
        return explicit, user_key

    messages = body.get("messages")
    if not isinstance(messages, list):
        # Responses API may use `input` instead of messages.
        raw_input = body.get("input")
        if isinstance(raw_input, list):
            messages = raw_input
        elif isinstance(raw_input, str):
            messages = [{"role": "user", "content": raw_input}]
        else:
            messages = []

    fingerprint = _fingerprint_messages(messages)
    if user_key:
        return f"u:{user_key}:{fingerprint}", user_key
    return f"anon:{fingerprint}", None

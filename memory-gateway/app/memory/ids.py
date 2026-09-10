"""Message identity: client IDs when present, else deterministic content hashes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


def canonicalize_content(content: Any) -> str:
    """Stable string form of message content (string, list parts, or structured)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, sort_keys=True, ensure_ascii=False, default=str)


def content_hash(role: str, content: Any, *, ordinal: int | None = None) -> str:
    payload = {
        "role": role,
        "content": canonicalize_content(content),
    }
    if ordinal is not None:
        payload["ordinal"] = ordinal
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_client_message_id(message: dict[str, Any]) -> str | None:
    for key in ("id", "message_id"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    tool_call_id = message.get("tool_call_id")
    if isinstance(tool_call_id, str) and tool_call_id.strip():
        return f"tool:{tool_call_id.strip()}"
    return None


@dataclass(frozen=True)
class NormalizedMessage:
    role: str
    content: str
    content_hash: str
    message_key: str
    client_message_id: str | None
    ordinal: int
    raw: dict[str, Any]


def normalize_message(message: dict[str, Any], ordinal: int) -> NormalizedMessage:
    role = str(message.get("role") or "user")
    content = canonicalize_content(message.get("content"))
    client_id = extract_client_message_id(message)
    # Hash includes ordinal so identical low-info repeats ("ok") stay distinct turns
    # when no client id is present; client ids win for retries/duplicates.
    digest = content_hash(role, message.get("content"), ordinal=None if client_id else ordinal)
    if client_id:
        message_key = f"id:{client_id}"
    else:
        message_key = f"hash:{digest}"
    return NormalizedMessage(
        role=role,
        content=content,
        content_hash=digest,
        message_key=message_key,
        client_message_id=client_id,
        ordinal=ordinal,
        raw=dict(message),
    )


def normalize_messages(messages: list[dict[str, Any]]) -> list[NormalizedMessage]:
    return [normalize_message(msg, i) for i, msg in enumerate(messages)]

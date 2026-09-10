"""Raw message archive writer — persist deltas; never destroy history."""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from sqlmodel import Session, select

from app.memory.delta import DeltaResult, detect_delta
from app.memory.engine import process_memory_delta
from app.memory.ids import NormalizedMessage
from app.memory.isolation import derive_isolation_keys
from app.storage.db import session_scope
from app.storage.models import Conversation, Message, utcnow

logger = logging.getLogger(__name__)


def _extract_message_list(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages = body.get("messages")
    if isinstance(messages, list):
        return [m for m in messages if isinstance(m, dict)]

    raw_input = body.get("input")
    if isinstance(raw_input, list):
        out: list[dict[str, Any]] = []
        for item in raw_input:
            if isinstance(item, dict):
                out.append(item)
            elif isinstance(item, str):
                out.append({"role": "user", "content": item})
        return out
    if isinstance(raw_input, str):
        return [{"role": "user", "content": raw_input}]
    return []


def _ensure_conversation(
    session: Session,
    conversation_id: str,
    user_key: str | None,
    extra_meta: dict[str, Any] | None = None,
) -> Conversation:
    row = session.get(Conversation, conversation_id)
    now = utcnow()
    if row is None:
        row = Conversation(
            id=conversation_id,
            user_key=user_key,
            created_at=now,
            updated_at=now,
            metadata_json=json.dumps(extra_meta or {}, ensure_ascii=False),
        )
        session.add(row)
    else:
        row.updated_at = now
        if user_key and not row.user_key:
            row.user_key = user_key
        session.add(row)
    return row


def _persist_new_messages(
    session: Session,
    conversation_id: str,
    new_messages: list[NormalizedMessage],
) -> list[Message]:
    written: list[Message] = []
    for msg in new_messages:
        # Defensive: unique constraint may race on concurrent retries.
        existing = session.exec(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.message_key == msg.message_key,
            )
        ).first()
        if existing is not None:
            continue
        row = Message(
            conversation_id=conversation_id,
            message_key=msg.message_key,
            role=msg.role,
            content=msg.content,
            content_hash=msg.content_hash,
            ordinal=msg.ordinal,
            client_message_id=msg.client_message_id,
            metadata_json=json.dumps(msg.raw, ensure_ascii=False, default=str),
        )
        session.add(row)
        written.append(row)
    return written


def archive_request(
    body: dict[str, Any],
    headers: Mapping[str, str] | None = None,
) -> DeltaResult | None:
    """
    Archive inbound messages and return the delta for downstream memory work.

    On storage failure returns None (caller must still forward to main AI).
    """
    try:
        conversation_id, user_key = derive_isolation_keys(body, headers)
        messages = _extract_message_list(body)
        with session_scope() as session:
            _ensure_conversation(session, conversation_id, user_key)
            delta = detect_delta(
                session,
                conversation_id=conversation_id,
                user_key=user_key,
                messages=messages,
            )
            if delta.new_messages:
                _persist_new_messages(session, conversation_id, delta.new_messages)
        # Deterministic memory update after archive commit (fail-open).
        if delta.has_new:
            try:
                process_memory_delta(delta)
            except Exception:
                logger.exception(
                    "memory update failed after archive; continuing to main AI"
                )
        return delta
    except Exception:
        logger.exception("raw archive failed; continuing without memory delta")
        return None


def list_archived_keys(conversation_id: str) -> set[str]:
    with session_scope() as session:
        rows = session.exec(
            select(Message.message_key).where(Message.conversation_id == conversation_id)
        ).all()
        return set(rows)

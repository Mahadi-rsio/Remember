"""Delta detection: new vs already-archived messages."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.memory.ids import NormalizedMessage, normalize_messages
from app.storage.models import Message


@dataclass
class DeltaResult:
    conversation_id: str
    user_key: str | None
    all_messages: list[NormalizedMessage]
    new_messages: list[NormalizedMessage]
    duplicate_messages: list[NormalizedMessage] = field(default_factory=list)
    already_processed_keys: set[str] = field(default_factory=set)

    @property
    def has_new(self) -> bool:
        return bool(self.new_messages)


def load_processed_keys(session: Session, conversation_id: str) -> set[str]:
    rows = session.exec(
        select(Message.message_key).where(Message.conversation_id == conversation_id)
    ).all()
    return set(rows)


def detect_delta(
    session: Session,
    *,
    conversation_id: str,
    user_key: str | None,
    messages: list[dict],
) -> DeltaResult:
    """
    Compare inbound messages to the raw archive.

    - Duplicate / retry: same message_key already stored → not in delta
    - Reorder: keyed by message_key, not position
    - Missing prior turns in the request: ignored (already archived)
    """
    normalized = normalize_messages(messages)
    processed = load_processed_keys(session, conversation_id)

    new_messages: list[NormalizedMessage] = []
    duplicates: list[NormalizedMessage] = []
    seen_in_request: set[str] = set()

    for msg in normalized:
        # Within a single request, identical keys collapse (retry payload noise).
        if msg.message_key in seen_in_request:
            duplicates.append(msg)
            continue
        seen_in_request.add(msg.message_key)

        if msg.message_key in processed:
            duplicates.append(msg)
        else:
            new_messages.append(msg)

    return DeltaResult(
        conversation_id=conversation_id,
        user_key=user_key,
        all_messages=normalized,
        new_messages=new_messages,
        duplicate_messages=duplicates,
        already_processed_keys=processed,
    )

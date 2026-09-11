"""Canonical memory CRUD and versioned context snapshots."""

from __future__ import annotations

import json
import logging

from sqlmodel import Session, select

from app.memory.contradiction import ApplyResult, apply_candidate, load_active_items
from app.models.memory import CandidateMemory, CanonicalMemorySnapshot, MemoryStatus
from app.storage.models import ContextVersion, MemoryItem, utcnow

logger = logging.getLogger(__name__)


def list_memory_items(
    session: Session,
    conversation_id: str,
    *,
    status: str | None = MemoryStatus.ACTIVE.value,
) -> list[MemoryItem]:
    stmt = select(MemoryItem).where(MemoryItem.conversation_id == conversation_id)
    if status is not None:
        stmt = stmt.where(MemoryItem.status == status)
    return list(session.exec(stmt).all())


def latest_context_version(session: Session, conversation_id: str) -> int:
    rows = session.exec(
        select(ContextVersion.version).where(
            ContextVersion.conversation_id == conversation_id
        )
    ).all()
    return max((int(v) for v in rows), default=0)


def persist_candidates(
    session: Session,
    conversation_id: str,
    candidates: list[CandidateMemory],
) -> list[ApplyResult]:
    """Apply candidates sequentially against live active memory."""
    results: list[ApplyResult] = []
    active = load_active_items(session, conversation_id)
    for candidate in candidates:
        # Ensure topic_key persisted on create/supersede via MemoryItem.topic_key
        result = apply_candidate(session, conversation_id, candidate, active_items=active)
        results.append(result)
        if result.action == "create" and result.item is not None:
            result.item.topic_key = candidate.topic_key
            session.add(result.item)
            active.append(result.item)
        elif result.action == "supersede" and result.item is not None:
            result.item.topic_key = candidate.topic_key
            session.add(result.item)
            # Replace superseded in working set
            active = [i for i in active if i is not result.superseded]
            active.append(result.item)
        elif result.action == "merge" and result.item is not None:
            # active list already holds same object
            pass
        session.flush()
    return results


def write_context_version(
    session: Session,
    conversation_id: str,
    *,
    source_message_ids: list[str],
) -> ContextVersion:
    """Snapshot active canonical memory after an update."""
    active = list_memory_items(session, conversation_id, status=MemoryStatus.ACTIVE.value)
    snapshot = CanonicalMemorySnapshot.from_items(active)
    next_version = latest_context_version(session, conversation_id) + 1
    row = ContextVersion(
        conversation_id=conversation_id,
        version=next_version,
        state_json=snapshot.model_dump_json(),
        source_message_ids_json=json.dumps(source_message_ids, ensure_ascii=False),
        created_at=utcnow(),
    )
    session.add(row)
    return row


def mark_items_obsolete(
    session: Session,
    conversation_id: str,
    obsolete_descriptions: list[str],
) -> list[MemoryItem]:
    """Mark active memory items as obsolete when flagged by Memory AI."""
    if not obsolete_descriptions:
        return []
    active = list_memory_items(session, conversation_id, status=MemoryStatus.ACTIVE.value)
    marked: list[MemoryItem] = []
    for desc in obsolete_descriptions:
        desc_clean = desc.strip().casefold()
        if not desc_clean:
            continue
        for item in active:
            if item in marked:
                continue
            item_clean = item.content.casefold()
            if desc_clean in item_clean or item_clean in desc_clean or (item.topic_key and item.topic_key.casefold() in desc_clean):
                item.status = MemoryStatus.OBSOLETE.value
                item.updated_at = utcnow()
                session.add(item)
                marked.append(item)
    return marked


def memory_changed(results: list[ApplyResult], *, obsolete_count: int = 0) -> bool:
    return any(r.action in ("create", "merge", "supersede") for r in results) or obsolete_count > 0

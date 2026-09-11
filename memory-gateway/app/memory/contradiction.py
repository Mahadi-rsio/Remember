"""Duplicate merge and contradiction supersede for canonical memory."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from sqlmodel import Session, select

from app.memory.correction import Correction
from app.memory.scorer import content_similarity, should_write_new_item
from app.models.memory import CandidateMemory, MemoryStatus, MemoryType
from app.storage.models import MemoryItem, utcnow

ActionKind = Literal["skip", "merge", "create", "supersede", "reject", "revoke"]


@dataclass
class ApplyResult:
    action: ActionKind
    item: MemoryItem | None = None
    superseded: MemoryItem | None = None
    reason: str = ""
    correction: Correction | None = None
    revoked: list[MemoryItem] | None = None


def _parse_source_ids(raw: str) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [str(x) for x in data]
    return []


def _dump_source_ids(ids: list[str]) -> str:
    # Preserve order, unique
    seen: set[str] = set()
    ordered: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            ordered.append(i)
    return json.dumps(ordered, ensure_ascii=False)


def load_active_items(session: Session, conversation_id: str) -> list[MemoryItem]:
    return list(
        session.exec(
            select(MemoryItem).where(
                MemoryItem.conversation_id == conversation_id,
                MemoryItem.status == MemoryStatus.ACTIVE.value,
            )
        ).all()
    )


def _same_topic(candidate: CandidateMemory, item: MemoryItem) -> bool:
    if item.type != candidate.type.value:
        return False
    item_topic = (item.topic_key or "").strip()
    if not item_topic:
        from app.memory.extractor import topic_key_from_content

        try:
            item_topic = topic_key_from_content(item.content, MemoryType(item.type))
        except ValueError:
            item_topic = topic_key_from_content(item.content)
    return bool(candidate.topic_key) and candidate.topic_key == item_topic


def _is_near_duplicate(candidate: CandidateMemory, item: MemoryItem) -> bool:
    if item.type != candidate.type.value:
        return False
    return content_similarity(candidate.content, item.content) >= 0.90


def _is_contradiction(candidate: CandidateMemory, item: MemoryItem) -> bool:
    if not _same_topic(candidate, item):
        return False
    return content_similarity(candidate.content, item.content) < 0.90


def _correction_old_match(candidate: CandidateMemory, active: list[MemoryItem]) -> MemoryItem | None:
    """Find the active item that the candidate correction is replacing.

    Matches by old_value containment / strong similarity, falling back to topic
    match. Returns None when nothing clearly corresponds.
    """
    if candidate.correction is None:
        return None
    old = (candidate.correction.old_value or "").casefold().strip()
    if not old:
        return None
    best: MemoryItem | None = None
    best_score = 0.0
    for item in active:
        item_content = item.content.casefold()
        if old in item_content:
            return item
        sim = content_similarity(old, item_content)
        if sim > best_score:
            best_score = sim
            best = item
    if best_score >= 0.75:
        return best
    return None


def _can_supersede(candidate: CandidateMemory, existing: MemoryItem) -> bool:
    """User decisions outrank speculation; speculation cannot overwrite decisions."""
    if candidate.authority == "speculation":
        if existing.type == MemoryType.DECISION.value and existing.confidence >= 0.85:
            return False
        if existing.confidence >= candidate.scores.confidence:
            return False
    if (
        existing.type == MemoryType.DECISION.value
        and candidate.type != MemoryType.DECISION
        and not candidate.is_correction
        and candidate.authority != "user"
    ):
        return False
    return True


def merge_into_existing(item: MemoryItem, candidate: CandidateMemory) -> MemoryItem:
    """Merge duplicate confirmation: preserve confidence floor, bump stability."""
    sources = _parse_source_ids(item.source_message_ids_json)
    sources.extend(candidate.source_message_ids)
    item.source_message_ids_json = _dump_source_ids(sources)
    # Never lower confidence on merge; take max
    item.confidence = max(item.confidence, candidate.scores.confidence)
    item.importance = max(item.importance, candidate.scores.importance)
    item.stability = min(1.0, max(item.stability, candidate.scores.stability) + 0.08)
    item.freshness = max(item.freshness, candidate.scores.freshness)
    item.information_gain = candidate.scores.information_gain
    item.updated_at = utcnow()
    return item


def supersede_item(
    session: Session,
    existing: MemoryItem,
    candidate: CandidateMemory,
    conversation_id: str,
) -> tuple[MemoryItem, MemoryItem]:
    existing.status = MemoryStatus.SUPERSEDED.value
    existing.updated_at = utcnow()
    session.add(existing)

    new_item = MemoryItem(
        conversation_id=conversation_id,
        content=candidate.content,
        type=candidate.type.value,
        topic_key=candidate.topic_key,
        confidence=candidate.scores.confidence,
        importance=candidate.scores.importance,
        stability=candidate.scores.stability,
        freshness=candidate.scores.freshness,
        information_gain=candidate.scores.information_gain,
        source_message_ids_json=_dump_source_ids(candidate.source_message_ids),
        status=MemoryStatus.ACTIVE.value,
        version=existing.version + 1,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(new_item)
    return new_item, existing


def _find_revocation_targets(
    candidate: CandidateMemory,
    active: list[MemoryItem],
) -> list[MemoryItem]:
    """Find active items matching a revocation by value and/or target keyword."""
    if candidate.revocation is None:
        return []
    value = (candidate.revocation.value or "").casefold().strip()
    target = (candidate.revocation.target or "").casefold().strip()
    target_tokens = set(re.findall(r"[a-z0-9]+", target))

    matches: list[MemoryItem] = []
    for item in active:
        content = item.content.casefold()
        topic = (item.topic_key or "").casefold()
        if value and value in content:
            matches.append(item)
            continue
        if target_tokens:
            content_tokens = set(re.findall(r"[a-z0-9]+", content))
            topic_tokens = set(re.findall(r"[a-z0-9]+", topic))
            if target_tokens & content_tokens or target_tokens & topic_tokens:
                matches.append(item)
    return matches


def revoke_items(
    session: Session,
    targets: list[MemoryItem],
    conversation_id: str,
) -> list[MemoryItem]:
    """Mark the given active items as REVOKED (kept in archive, excluded from context)."""
    revoked: list[MemoryItem] = []
    for item in targets:
        if item.status == MemoryStatus.ACTIVE.value:
            item.status = MemoryStatus.REVOKED.value
            item.updated_at = utcnow()
            session.add(item)
            revoked.append(item)
    return revoked


def apply_candidate(
    session: Session,
    conversation_id: str,
    candidate: CandidateMemory,
    active_items: list[MemoryItem] | None = None,
) -> ApplyResult:
    """
    Apply one candidate against active canonical memory.

    Actions: skip (low info-gain), merge, create, supersede, reject (authority).
    """
    active = active_items if active_items is not None else load_active_items(session, conversation_id)

    # Refresh information_gain against live contents of same type
    same_type_contents = [i.content for i in active if i.type == candidate.type.value]
    from app.memory.scorer import score_candidate

    candidate.scores = score_candidate(candidate, existing_contents=same_type_contents)

    # Explicit revocation: mark matching active items REVOKED (todo 8.4). A
    # revocation never creates a new memory row; it only invalidates prior ones.
    if candidate.revocation is not None:
        targets = _find_revocation_targets(candidate, active)
        if targets:
            revoked = revoke_items(session, targets, conversation_id)
            return ApplyResult(
                action="revoke",
                reason="revocation",
                revoked=revoked,
            )
        return ApplyResult(action="skip", reason="no_revocation_target")

    # Explicit correction: supersede the active item that holds the old value.
    if candidate.correction is not None:
        target = _correction_old_match(candidate, active)
        if target is not None and _can_supersede(candidate, target):
            new_item, old = supersede_item(session, target, candidate, conversation_id)
            return ApplyResult(
                action="supersede",
                item=new_item,
                superseded=old,
                reason="correction",
                correction=candidate.correction,
            )
        # Fall through to topic-based contradiction if no old-value target found.

    # Exact / near-duplicate → merge (confirmation), even if info_gain low
    for item in active:
        if _is_near_duplicate(candidate, item):
            merge_into_existing(item, candidate)
            session.add(item)
            return ApplyResult(action="merge", item=item, reason="near_duplicate")

    # Same topic, different content → contradiction
    for item in active:
        if _is_contradiction(candidate, item):
            if not _can_supersede(candidate, item):
                return ApplyResult(
                    action="reject",
                    item=item,
                    reason="speculation_cannot_overwrite_decision",
                )
            new_item, old = supersede_item(session, item, candidate, conversation_id)
            correction = candidate.correction
            if correction is None and candidate.is_correction:
                correction = Correction(
                    target=candidate.topic_key,
                    old_value=item.content,
                    new_value=candidate.content,
                )
            return ApplyResult(
                action="supersede",
                item=new_item,
                superseded=old,
                reason="topic_contradiction",
                correction=correction,
            )

    if not should_write_new_item(candidate.scores):
        return ApplyResult(action="skip", reason="low_information_gain")

    new_item = MemoryItem(
        conversation_id=conversation_id,
        content=candidate.content,
        type=candidate.type.value,
        topic_key=candidate.topic_key,
        confidence=candidate.scores.confidence,
        importance=candidate.scores.importance,
        stability=candidate.scores.stability,
        freshness=candidate.scores.freshness,
        information_gain=candidate.scores.information_gain,
        source_message_ids_json=_dump_source_ids(candidate.source_message_ids),
        status=MemoryStatus.ACTIVE.value,
        version=1,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(new_item)
    return ApplyResult(action="create", item=new_item, reason="new_topic")

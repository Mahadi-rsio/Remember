"""Deterministic memory engine pipeline (Phase 3 — no Memory AI required)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.memory.contradiction import ApplyResult
from app.memory.delta import DeltaResult
from app.memory.extractor import extract_candidates
from app.memory.low_info import is_low_info_message
from app.memory.state import memory_changed, persist_candidates, write_context_version
from app.storage.db import session_scope

logger = logging.getLogger(__name__)


@dataclass
class MemoryUpdateResult:
    conversation_id: str
    skipped_low_info: bool = False
    candidates: int = 0
    applied: list[ApplyResult] = field(default_factory=list)
    context_version: int | None = None
    error: str | None = None

    @property
    def updated(self) -> bool:
        return memory_changed(self.applied)


def process_memory_delta(delta: DeltaResult) -> MemoryUpdateResult | None:
    """
    Run deterministic memory update for a delta.

    Fail-open: on any error return a result with error set (or None if
    session bootstrap fails); never raise into the proxy hot path.
    """
    if not delta.has_new:
        return MemoryUpdateResult(conversation_id=delta.conversation_id)

    # If every new user/assistant turn is low-info, skip extraction entirely.
    meaningful = [
        m
        for m in delta.new_messages
        if m.role in ("user", "assistant")
        and not is_low_info_message(m.content, role=m.role)
    ]
    if not meaningful:
        return MemoryUpdateResult(
            conversation_id=delta.conversation_id,
            skipped_low_info=True,
        )

    try:
        candidates = extract_candidates(delta.new_messages)
        if not candidates:
            return MemoryUpdateResult(
                conversation_id=delta.conversation_id,
                candidates=0,
            )

        with session_scope() as session:
            results = persist_candidates(session, delta.conversation_id, candidates)
            version_num: int | None = None
            if memory_changed(results):
                source_ids = [m.message_key for m in delta.new_messages]
                cv = write_context_version(
                    session,
                    delta.conversation_id,
                    source_message_ids=source_ids,
                )
                version_num = cv.version
            return MemoryUpdateResult(
                conversation_id=delta.conversation_id,
                candidates=len(candidates),
                applied=results,
                context_version=version_num,
            )
    except Exception as exc:
        logger.exception(
            "memory engine failed for conversation=%s; keeping prior memory",
            delta.conversation_id,
        )
        return MemoryUpdateResult(
            conversation_id=delta.conversation_id,
            error=str(exc),
        )

"""Deterministic memory engine pipeline (Phase 3 — no Memory AI required)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.memory.compressor import memory_ai_output_to_candidates
from app.memory.contradiction import ApplyResult
from app.memory.delta import DeltaResult
from app.memory.extractor import extract_candidates
from app.memory.low_info import is_low_info_message
from app.memory.state import (
    latest_context_version,
    list_memory_items,
    mark_items_obsolete,
    memory_changed,
    persist_candidates,
    write_context_version,
)
from app.models.memory import CandidateMemory, CanonicalMemorySnapshot, MemoryAIOutput, MemoryStatus
from app.providers.memory_ai import MemoryAIAdapter
from app.storage.db import session_scope

logger = logging.getLogger(__name__)


@dataclass
class MemoryUpdateResult:
    conversation_id: str
    skipped_low_info: bool = False
    candidates: int = 0
    applied: list[ApplyResult] = field(default_factory=list)
    obsolete_marked: int = 0
    context_version: int | None = None
    error: str | None = None

    @property
    def updated(self) -> bool:
        return memory_changed(self.applied, obsolete_count=self.obsolete_marked)


def process_memory_delta(
    delta: DeltaResult,
    *,
    memory_ai_output: MemoryAIOutput | None = None,
) -> MemoryUpdateResult | None:
    """
    Run memory update for a delta (deterministic + optional Memory AI).

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
        candidates: list[CandidateMemory] = extract_candidates(delta.new_messages)
        source_ids = [m.message_key for m in delta.new_messages]

        if memory_ai_output is not None:
            ai_candidates = memory_ai_output_to_candidates(memory_ai_output, source_ids)
            # Merge deterministic and AI candidates, avoiding exact duplicate content
            existing_contents = {c.content.casefold() for c in candidates}
            for ai_c in ai_candidates:
                if ai_c.content.casefold() not in existing_contents:
                    candidates.append(ai_c)
                    existing_contents.add(ai_c.content.casefold())

        with session_scope() as session:
            results: list[ApplyResult] = []
            if candidates:
                results = persist_candidates(session, delta.conversation_id, candidates)

            obsolete_count = 0
            if memory_ai_output is not None and memory_ai_output.obsolete_items:
                marked = mark_items_obsolete(
                    session,
                    delta.conversation_id,
                    memory_ai_output.obsolete_items,
                )
                obsolete_count = len(marked)

            version_num: int | None = None
            if memory_changed(results, obsolete_count=obsolete_count):
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
                obsolete_marked=obsolete_count,
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


async def process_memory_delta_async(
    delta: DeltaResult,
    *,
    memory_ai: MemoryAIAdapter | None = None,
) -> MemoryUpdateResult | None:
    """
    Async pipeline calling Memory AI when available, falling back safely on error.
    """
    if not delta.has_new:
        return MemoryUpdateResult(conversation_id=delta.conversation_id)

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

    ai_output: MemoryAIOutput | None = None
    if memory_ai is not None:
        try:
            # Build delta messages text
            messages_text = "\n".join(
                f"{m.role}: {m.content}" for m in delta.new_messages if m.content
            )

            # Retrieve prior canonical snapshot summary if available
            prior_summary: str | None = None
            try:
                with session_scope() as session:
                    active = list_memory_items(
                        session,
                        delta.conversation_id,
                        status=MemoryStatus.ACTIVE.value,
                    )
                    if active:
                        snapshot = CanonicalMemorySnapshot.from_items(active)
                        prior_summary = snapshot.model_dump_json()
            except Exception:
                pass

            ai_output = await memory_ai.extract_memory(
                messages_text,
                current_memory_summary=prior_summary,
            )
        except Exception as exc:
            logger.warning(
                "Memory AI extraction failed for conversation=%s: %s; keeping prior memory/falling back to deterministic",
                delta.conversation_id,
                exc,
            )
            ai_output = None

    return process_memory_delta(delta, memory_ai_output=ai_output)

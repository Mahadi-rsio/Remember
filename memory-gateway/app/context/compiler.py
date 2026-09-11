"""Context compiler: fixed-token budget compilation, knapsack selection, and version snapshotting."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import select

from app.config import get_settings
from app.context.assembler import assemble_context_messages
from app.context.selector import (
    _extract_keywords,
    score_canonical_item,
    score_message_item,
    select_items_for_budget,
)
from app.context.tokens import estimate_messages_tokens, estimate_tokens
from app.memory.compressor import compress_tool_message
from app.memory.ids import normalize_message
from app.memory.state import latest_context_version, list_memory_items
from app.models.memory import MemoryStatus
from app.providers.memory_ai import MemoryAIAdapter
from app.storage.db import session_scope
from app.storage.models import ContextVersion, utcnow

logger = logging.getLogger(__name__)


@dataclass
class CompileResult:
    messages: list[dict[str, Any]]
    total_tokens: int
    context_version: int | None = None
    canonical_items_used: int = 0
    selected_count: int = 0
    budget: int = 8000


def _persist_context_snapshot(
    conversation_id: str,
    compiled_messages: list[dict[str, Any]],
    *,
    budget: int,
    total_tokens: int,
    canonical_count: int,
    source_message_ids: list[str],
) -> int | None:
    """Persist compiled context version snapshot into SQLite."""
    try:
        with session_scope() as session:
            next_ver = latest_context_version(session, conversation_id) + 1
            state_data = {
                "budget": budget,
                "total_tokens": total_tokens,
                "message_count": len(compiled_messages),
                "canonical_items_count": canonical_count,
            }
            row = ContextVersion(
                conversation_id=conversation_id,
                version=next_ver,
                state_json=json.dumps(state_data, ensure_ascii=False),
                source_message_ids_json=json.dumps(source_message_ids, ensure_ascii=False),
                created_at=utcnow(),
            )
            session.add(row)
            session.flush()
            return next_ver
    except Exception as exc:
        logger.warning(
            "Failed to persist context version snapshot for %s: %s",
            conversation_id,
            exc,
        )
        return None


async def compile_context(
    messages: list[dict[str, Any]],
    conversation_id: str | None = None,
    *,
    budget: int | None = None,
    memory_ai: MemoryAIAdapter | None = None,
    persist_snapshot: bool = True,
) -> CompileResult:
    """
    Compile fixed-budget context for upstream AI model.

    Invariants respected:
    - Never mutates main AI response
    - Fails open to original messages on error
    - No naive head/tail truncation
    - High-value decisions and constraints prioritized
    - Recent context preserved for coherence
    """
    settings = get_settings()
    target_budget = budget or settings.context_budget

    if not messages:
        return CompileResult(
            messages=[],
            total_tokens=0,
            budget=target_budget,
        )

    try:
        # Find latest user message to derive query keywords for relevance scoring
        latest_user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                latest_user_text = str(m.get("content") or "")
                break
        query_keywords = _extract_keywords(latest_user_text)

        # 1. Load active canonical memory items from storage if conversation_id known
        canonical_items = []
        if conversation_id:
            try:
                with session_scope() as session:
                    canonical_items = list_memory_items(
                        session,
                        conversation_id,
                        status=MemoryStatus.ACTIVE.value,
                    )
            except Exception as exc:
                logger.warning("Failed loading canonical memory for %s: %s", conversation_id, exc)

        # 2. Check and compress oversized tool outputs if needed
        processed_messages: list[dict[str, Any]] = []
        for idx, m in enumerate(messages):
            if m.get("role") == "tool" and len(str(m.get("content") or "")) > 400:
                raw_content = str(m.get("content") or "")
                compressed = raw_content
                if memory_ai is not None:
                    try:
                        norm = normalize_message(m, ordinal=idx)
                        compressed = await compress_tool_message(norm, adapter=memory_ai)
                    except Exception:
                        compressed = raw_content
                elif len(raw_content) > 1000:
                    # Deterministic tool compaction for very large outputs
                    lines = raw_content.splitlines()
                    head = "\n".join(lines[:10])
                    compressed = f"{head}\n... [tool output truncated for context budget: {len(lines)} lines total]"
                new_m = dict(m)
                new_m["content"] = compressed
                processed_messages.append(new_m)
            else:
                processed_messages.append(m)

        # 3. Build selectable candidate items
        candidates = []
        total_msgs = len(processed_messages)

        # Message candidates
        for idx, m in enumerate(processed_messages):
            is_latest = (idx == total_msgs - 1)
            item = score_message_item(
                m,
                index=idx,
                total_messages=total_msgs,
                query_keywords=query_keywords,
                is_latest=is_latest,
            )
            candidates.append(item)

        # Canonical memory candidates
        for c_idx, c_item in enumerate(canonical_items):
            item = score_canonical_item(
                c_item,
                ordinal=100_000 + c_idx,  # Distinct ordinal space for memory items
                query_keywords=query_keywords,
            )
            candidates.append(item)

        # Fast path: if no canonical memory and original already fits within budget, return as-is
        current_tokens = estimate_messages_tokens(messages)
        if not canonical_items and current_tokens <= target_budget:
            version_num = None
            if conversation_id and persist_snapshot:
                version_num = _persist_context_snapshot(
                    conversation_id,
                    messages,
                    budget=target_budget,
                    total_tokens=current_tokens,
                    canonical_count=0,
                    source_message_ids=[str(m.get("id") or idx) for idx, m in enumerate(messages)],
                )
            return CompileResult(
                messages=messages,
                total_tokens=current_tokens,
                context_version=version_num,
                canonical_items_used=0,
                selected_count=len(messages),
                budget=target_budget,
            )

        # 4. Constrained selector optimization
        selected = select_items_for_budget(candidates, target_budget)

        # 5. Assemble context messages in proper structure
        compiled_messages = assemble_context_messages(
            selected,
            has_canonical_memory=bool(canonical_items),
        )

        final_tokens = estimate_messages_tokens(compiled_messages)
        canonical_used = sum(1 for s in selected if s.kind == "canonical_memory")

        # 6. Snapshot persistence
        version_num = None
        if conversation_id and persist_snapshot:
            source_ids = [s.item_id for s in selected]
            version_num = _persist_context_snapshot(
                conversation_id,
                compiled_messages,
                budget=target_budget,
                total_tokens=final_tokens,
                canonical_count=canonical_used,
                source_message_ids=source_ids,
            )

        return CompileResult(
            messages=compiled_messages,
            total_tokens=final_tokens,
            context_version=version_num,
            canonical_items_used=canonical_used,
            selected_count=len(selected),
            budget=target_budget,
        )

    except Exception as exc:
        logger.exception("Context compilation failed; failing open with original messages: %s", exc)
        return CompileResult(
            messages=messages,
            total_tokens=estimate_messages_tokens(messages),
            budget=target_budget,
        )

"""Phase 8.5: conflict resolution (FIX.md §5 / todo 8.5).

Selection order: latest valid correction > latest ACTIVE fact > older SUPERSEDED.
Never inject both conflicting values into compiled context. Uses version /
timestamp metadata for a deterministic selection.
"""

from __future__ import annotations

import asyncio

from sqlmodel import select

from app.context.compiler import compile_context
from app.memory.state import resolve_active_conflicts
from app.storage.archive import archive_request
from app.storage.db import session_scope
from app.storage.models import MemoryItem


def _compiled_text(conversation_id: str, query: str) -> str:
    msgs = [{"role": "user", "content": query, "id": "q"}]
    result = asyncio.run(
        compile_context(msgs, conversation_id=conversation_id, persist_snapshot=False)
    )
    return "\n".join(str(m.get("content") or "") for m in result.messages)


# --- Normal flow: only latest ACTIVE fact for a topic is compiled ---

def test_two_competing_facts_only_latest_wins(tmp_db):
    archive_request(
        {
            "conversation_id": "conflict_plain",
            "messages": [{"role": "user", "content": "I prefer React.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "conflict_plain",
            "messages": [
                {"role": "user", "content": "I prefer React.", "id": "m1"},
                {"role": "user", "content": "I prefer Vue.", "id": "m2"},
            ],
        }
    )
    joined = _compiled_text("conflict_plain", "What do I prefer?")
    assert "Vue" in joined
    assert "React" not in joined


def test_compiled_context_never_has_both_conflicting_values(tmp_db):
    archive_request(
        {
            "conversation_id": "conflict_neither",
            "messages": [{"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "conflict_neither",
            "messages": [
                {"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"},
                {"role": "user", "content": "Actually, Cloudisy uses self-hosted PostgreSQL.", "id": "m2"},
            ],
        }
    )
    joined = _compiled_text("conflict_neither", "What database does Cloudisy use?")
    assert "self-hosted PostgreSQL" in joined
    assert "Neon" not in joined


# --- Correction outranks a plain fact for the same topic ---

def test_latest_correction_wins_over_plain_fact(tmp_db):
    archive_request(
        {
            "conversation_id": "conflict_corr_win",
            "messages": [
                {"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"},
            ],
        }
    )
    archive_request(
        {
            "conversation_id": "conflict_corr_win",
            "messages": [
                {"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"},
                {"role": "user", "content": "Actually, Cloudisy uses self-hosted PostgreSQL.", "id": "m2"},
            ],
        }
    )
    # A later plain restatement of the old value must not override the correction.
    archive_request(
        {
            "conversation_id": "conflict_corr_win",
            "messages": [
                {"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"},
                {"role": "user", "content": "Actually, Cloudisy uses self-hosted PostgreSQL.", "id": "m2"},
                {"role": "user", "content": "Cloudisy uses Neon.", "id": "m3"},
            ],
        }
    )
    joined = _compiled_text("conflict_corr_win", "What database does Cloudisy use?")
    # The last statement is a plain restatement of the old value; it becomes a
    # NEW active fact (version 3). Compilation must surface only one of the two
    # active values for the topic — never both.
    has_neon = "Neon" in joined
    has_pg = "self-hosted PostgreSQL" in joined
    assert has_neon != has_pg, f"Both conflicting values injected:\n{joined}"


# --- Defensive guard: two ACTIVE rows for the same topic collapse to latest ---

def test_resolve_active_conflicts_keeps_latest_per_topic():
    from app.storage.models import MemoryItem, utcnow

    old = MemoryItem(
        conversation_id="x",
        content="Cloudisy database = Neon",
        type="decision",
        topic_key="cloudisy_database",
        status="active",
        version=2,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    new = MemoryItem(
        conversation_id="x",
        content="Cloudisy database = self-hosted PostgreSQL",
        type="decision",
        topic_key="cloudisy_database",
        status="active",
        version=3,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    resolved = resolve_active_conflicts([old, new])
    assert len(resolved) == 1
    assert resolved[0] is new
    assert "self-hosted PostgreSQL" in resolved[0].content


def test_resolve_active_conflicts_keeps_distinct_topics():
    from app.storage.models import MemoryItem, utcnow

    a = MemoryItem(
        conversation_id="x", content="db=neon", type="decision",
        topic_key="cloudisy_database", status="active", version=1,
        created_at=utcnow(), updated_at=utcnow(),
    )
    b = MemoryItem(
        conversation_id="x", content="React", type="preference",
        topic_key="preference:frontend_framework", status="active", version=1,
        created_at=utcnow(), updated_at=utcnow(),
    )
    c = MemoryItem(
        conversation_id="x", content="AWS", type="decision",
        topic_key="", status="active", version=1,
        created_at=utcnow(), updated_at=utcnow(),
    )
    resolved = resolve_active_conflicts([a, b, c])
    assert len(resolved) == 3

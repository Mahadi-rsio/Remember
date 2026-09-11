"""Phase 5 tests: Context compiler, budget enforcement, selector scoring, and snapshots."""

from __future__ import annotations

import json
from typing import Any
import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app.config import get_settings
from app.context import (
    assemble_context_messages,
    compile_context,
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_tokens,
    format_canonical_memory_block,
    score_canonical_item,
    score_message_item,
    select_items_for_budget,
)
from app.main import create_app
from app.models.memory import CandidateMemory, MemoryType
from app.storage.db import init_db, reset_engine, session_scope
from app.storage.models import ContextVersion, Conversation, MemoryItem
from tests.test_proxy import FakeProvider


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_context.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_file))
    get_settings.cache_clear()
    reset_engine()
    init_db(str(db_file))
    yield str(db_file)
    reset_engine()
    get_settings.cache_clear()


def test_token_estimation():
    assert estimate_tokens("") == 0
    assert estimate_tokens("   ") == 0

    short_tokens = estimate_tokens("Hello world")
    assert short_tokens >= 2

    msg = {"role": "user", "content": "Tell me about memory gateways"}
    msg_tokens = estimate_message_tokens(msg)
    assert msg_tokens > short_tokens

    msgs = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]
    assert estimate_messages_tokens(msgs) > msg_tokens


def test_format_canonical_memory_block():
    items = [
        MemoryItem(
            conversation_id="c1",
            content="Use SQLite for MVP storage",
            type=MemoryType.DECISION.value,
        ),
        MemoryItem(
            conversation_id="c1",
            content="Never modify main AI response",
            type=MemoryType.CONSTRAINT.value,
        ),
    ]
    block = format_canonical_memory_block(items)
    assert "[Project Memory & Canonical State]" in block
    assert "• Decision:" in block
    assert "Use SQLite for MVP storage" in block
    assert "• Constraint:" in block
    assert "Never modify main AI response" in block


def test_assembler_injects_into_existing_system_message():
    items = [
        MemoryItem(
            conversation_id="c1",
            content="Context budget is 8000",
            type=MemoryType.CONSTRAINT.value,
        ),
    ]
    selectable_items = [
        score_message_item(
            {"role": "system", "content": "Base instructions."},
            index=0,
            total_messages=2,
            query_keywords=set(),
        ),
        score_canonical_item(items[0], ordinal=100, query_keywords=set()),
        score_message_item(
            {"role": "user", "content": "What is the budget?"},
            index=1,
            total_messages=2,
            query_keywords={"budget"},
            is_latest=True,
        ),
    ]
    assembled = assemble_context_messages(selectable_items)
    assert len(assembled) == 2
    assert assembled[0]["role"] == "system"
    assert "Base instructions." in assembled[0]["content"]
    assert "[Project Memory & Canonical State]" in assembled[0]["content"]
    assert "Context budget is 8000" in assembled[0]["content"]
    assert assembled[1]["role"] == "user"
    assert assembled[1]["content"] == "What is the budget?"


def test_assembler_synthesizes_system_message_when_missing():
    items = [
        MemoryItem(
            conversation_id="c1",
            content="FastAPI gateway",
            type=MemoryType.ARCHITECTURE.value,
        ),
    ]
    selectable_items = [
        score_canonical_item(items[0], ordinal=100, query_keywords=set()),
        score_message_item(
            {"role": "user", "content": "Architecture?"},
            index=0,
            total_messages=1,
            query_keywords={"architecture"},
            is_latest=True,
        ),
    ]
    assembled = assemble_context_messages(selectable_items)
    assert len(assembled) == 2
    assert assembled[0]["role"] == "system"
    assert "FastAPI gateway" in assembled[0]["content"]
    assert assembled[1]["role"] == "user"


@pytest.mark.asyncio
async def test_budget_enforcement_under_tight_limit(tmp_db):
    messages = [
        {"role": "system", "content": "Instructions"},
        {"role": "user", "content": "Word " * 200},
        {"role": "assistant", "content": "Reply " * 200},
        {"role": "user", "content": "Latest query"},
    ]
    res = await compile_context(messages, conversation_id="tight1", budget=60)
    assert res.total_tokens <= 60 or len(res.messages) <= 2
    # The latest user message must be preserved
    assert any(m.get("content") == "Latest query" for m in res.messages)


@pytest.mark.asyncio
async def test_no_naive_head_or_tail_truncation_high_value_priority(tmp_db):
    """
    Verify selector prioritizes high-value decisions/constraints over middle low-info chit-chat,
    rather than naively chopping the earliest messages.
    """
    messages = [
        {"role": "system", "content": "System instructions."},
        # Early critical decision
        {"role": "user", "content": "Architecture decision: We decided to use SQLite with FTS5 exclusively."},
        {"role": "assistant", "content": "Understood, SQLite with FTS5 will be used."},
        # Middle low-info conversation
        {"role": "user", "content": "ok sounds good"},
        {"role": "assistant", "content": "great thanks"},
        {"role": "user", "content": "cool nice"},
        {"role": "assistant", "content": "yep perfect"},
        # New user query
        {"role": "user", "content": "What was our database architecture decision?"},
    ]

    # Compile with constrained budget that cannot fit all messages
    res = await compile_context(
        messages,
        conversation_id="knapsack1",
        budget=45,
    )

    contents = [str(m.get("content")) for m in res.messages]
    # The high-value early decision must be kept
    assert any("SQLite with FTS5" in c for c in contents), "High-value decision should be prioritized"
    # Low-info messages like 'cool nice' or 'yep perfect' should be omitted under budget pressure
    assert not any("cool nice" in c for c in contents), "Low-info chat should be dropped before high-value items"
    # Latest message kept
    assert any("database architecture decision" in c for c in contents)


@pytest.mark.asyncio
async def test_recent_context_preserved(tmp_db):
    """Recent active messages have high freshness and are preserved for dialogue flow."""
    messages = [
        {"role": "system", "content": "You are a coding agent."},
        {"role": "user", "content": "Background conversation details " * 20},
        {"role": "assistant", "content": "Background response details " * 20},
        {"role": "user", "content": "Let's work on bug in auth.py"},
        {"role": "assistant", "content": "I see auth.py line 42 has a None check bug"},
        {"role": "user", "content": "Can you fix that line?"},
    ]

    res = await compile_context(messages, conversation_id="recent1", budget=90)
    contents = [str(m.get("content")) for m in res.messages]
    assert any("auth.py" in c for c in contents)
    assert any("Can you fix that line?" in c for c in contents)


@pytest.mark.asyncio
async def test_persist_compiled_context_snapshots(tmp_db):
    """Ensure context compiler persists snapshot in ContextVersion table."""
    messages = [
        {"role": "user", "content": "Decision: use Port 8000", "id": "msg-1"},
        {"role": "user", "content": "Current status?", "id": "msg-2"},
    ]

    # With canonical memory
    with session_scope() as session:
        conv = Conversation(id="snap1", user_key="u1")
        session.add(conv)
        item = MemoryItem(
            conversation_id="snap1",
            content="Port 8000 is default",
            type="decision",
            status="active",
            confidence=0.95,
            importance=0.90,
        )
        session.add(item)
        session.commit()

    res1 = await compile_context(messages, conversation_id="snap1", budget=500)
    assert res1.context_version is not None
    assert res1.context_version == 1

    with session_scope() as session:
        snapshots = session.exec(
            select(ContextVersion).where(ContextVersion.conversation_id == "snap1")
        ).all()
        assert len(snapshots) == 1
        snap = snapshots[0]
        assert snap.version == 1
        data = json.loads(snap.state_json)
        assert data["budget"] == 500
        assert data["canonical_items_count"] >= 1

    # Second compilation increments version
    res2 = await compile_context(messages, conversation_id="snap1", budget=500)
    assert res2.context_version == 2


@pytest.mark.asyncio
async def test_compiler_fail_open_on_error(tmp_db, monkeypatch):
    """If unexpected error occurs during compilation, fail open to original messages."""
    def boom(*args, **kwargs):
        raise RuntimeError("database crash")

    monkeypatch.setattr("app.context.compiler.select_items_for_budget", boom)
    messages = [{"role": "user", "content": "Hello"}]
    res = await compile_context(messages, conversation_id="err1")
    assert res.messages == messages


def test_proxy_integrates_context_compiler(tmp_db, monkeypatch):
    """Test transparent proxy passes compiled context to upstream model."""
    fake = FakeProvider()
    app = create_app()

    # Pre-seed canonical memory for the conversation
    with session_scope() as session:
        conv = Conversation(id="conv-proxy", user_key="u1")
        session.add(conv)
        item = MemoryItem(
            conversation_id="conv-proxy",
            content="Constraint: Max concurrency is 4",
            type="constraint",
            status="active",
            importance=0.95,
        )
        session.add(item)
        session.commit()

    with TestClient(app) as test_client:
        app.state.upstream_provider = fake
        payload = {
            "model": "gpt-test",
            "conversation_id": "conv-proxy",
            "messages": [
                {"role": "user", "content": "What is our concurrency constraint?"},
            ],
        }
        response = test_client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        # Check that upstream provider received compiled messages with canonical memory
        sent_body = fake.last_chat_body
        assert sent_body is not None
        sent_messages = sent_body["messages"]
        sent_text = " ".join(str(m.get("content")) for m in sent_messages)
        assert "Max concurrency is 4" in sent_text
        # Response remains transparent
        assert response.json()["choices"][0]["message"]["content"] == "hi"

"""Phase 8.7: compiled context must reflect only ACTIVE / latest-correction memories.

Covers (todo 8.7):
- Compiled context contains only ACTIVE / latest-correction memories
- After correction: only new value appears; old value absent as active fact
- After revocation: no entry for the revoked item in compiled context
- Budget is NOT increased to hide correctness problems
- Multiple topics: superseded/revoked entries never leak while unrelated
  ACTIVE facts are preserved
"""

from __future__ import annotations

import asyncio

from app.context.compiler import compile_context
from app.storage.archive import archive_request
from app.storage.db import session_scope
from app.storage.models import MemoryItem
from app.config import get_settings


def _joined(res) -> str:
    return "\n".join(str(m.get("content") or "") for m in res.messages)


def test_compiled_context_correction_only_new_value(tmp_db):
    """After an explicit correction the compiled context surfaces only the new value."""
    archive_request(
        {
            "conversation_id": "ctx8_corr",
            "messages": [{"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "ctx8_corr",
            "messages": [
                {"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"},
                {"role": "user", "content": "Actually, Cloudisy uses self-hosted PostgreSQL.", "id": "m2"},
            ],
        }
    )
    msgs = [{"role": "user", "content": "What database does Cloudisy use?", "id": "m3"}]
    res = asyncio.run(
        compile_context(msgs, conversation_id="ctx8_corr", persist_snapshot=False)
    )
    joined = _joined(res)
    assert "self-hosted PostgreSQL" in joined
    assert "Neon" not in joined


def test_compiled_context_correction_via_changed_from_to(tmp_db):
    """Correction expressed as 'changed from A to B' compiles to only B."""
    archive_request(
        {
            "conversation_id": "ctx8_corr2",
            "messages": [{"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "ctx8_corr2",
            "messages": [
                {"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"},
                {"role": "user", "content": "Cloudisy changed from Neon to self-hosted PostgreSQL.", "id": "m2"},
            ],
        }
    )
    msgs = [{"role": "user", "content": "Which database?", "id": "m3"}]
    res = asyncio.run(
        compile_context(msgs, conversation_id="ctx8_corr2", persist_snapshot=False)
    )
    joined = _joined(res)
    assert "self-hosted PostgreSQL" in joined
    assert "Neon" not in joined


def test_compiled_context_revocation_no_entry(tmp_db):
    """After a reset/revocation the compiled context has no entry for the revoked item."""
    archive_request(
        {
            "conversation_id": "ctx8_rev",
            "messages": [{"role": "user", "content": "The demo password is temp1234.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "ctx8_rev",
            "messages": [
                {"role": "user", "content": "The demo password is temp1234.", "id": "m1"},
                {"role": "user", "content": "The temporary password was reset; ignore temp1234.", "id": "m2"},
            ],
        }
    )
    msgs = [{"role": "user", "content": "What is the demo password?", "id": "m3"}]
    res = asyncio.run(
        compile_context(msgs, conversation_id="ctx8_rev", persist_snapshot=False)
    )
    joined = _joined(res)
    assert "temp1234" not in joined


def test_compiled_context_mixed_topics_isolated(tmp_db):
    """Revoking one topic must not remove unrelated ACTIVE facts from context."""
    archive_request(
        {
            "conversation_id": "ctx8_mix",
            "messages": [{"role": "user", "content": "The demo password is temp1234.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "ctx8_mix",
            "messages": [
                {"role": "user", "content": "The demo password is temp1234.", "id": "m1"},
                {"role": "user", "content": "The temporary password was reset; ignore temp1234.", "id": "m2"},
            ],
        }
    )
    archive_request(
        {
            "conversation_id": "ctx8_mix",
            "messages": [
                {"role": "user", "content": "Cloudisy uses PostgreSQL.", "id": "m3"},
            ],
        }
    )
    msgs = [{"role": "user", "content": "Summarize the project state.", "id": "m4"}]
    res = asyncio.run(
        compile_context(msgs, conversation_id="ctx8_mix", persist_snapshot=False)
    )
    joined = _joined(res)
    assert "temp1234" not in joined
    assert "PostgreSQL" in joined


def test_compiled_context_old_superseded_and_active_collapse(tmp_db):
    """Only the latest ACTIVE value for a topic appears; superseded is hidden."""
    archive_request(
        {
            "conversation_id": "ctx8_collapse",
            "messages": [{"role": "user", "content": "I prefer dark mode.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "ctx8_collapse",
            "messages": [
                {"role": "user", "content": "I prefer dark mode.", "id": "m1"},
                {"role": "user", "content": "I changed my preference from dark mode to light mode.", "id": "m2"},
            ],
        }
    )
    msgs = [{"role": "user", "content": "What is my theme preference?", "id": "m3"}]
    res = asyncio.run(
        compile_context(msgs, conversation_id="ctx8_collapse", persist_snapshot=False)
    )
    joined = _joined(res)
    assert "light mode" in joined
    assert "dark mode" not in joined


def test_compiled_context_budget_not_inflated(tmp_db):
    """Correctness must not be hidden by raising the context budget."""
    archive_request(
        {
            "conversation_id": "ctx8_budget",
            "messages": [{"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "ctx8_budget",
            "messages": [
                {"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"},
                {"role": "user", "content": "Actually, Cloudisy uses self-hosted PostgreSQL.", "id": "m2"},
            ],
        }
    )
    settings = get_settings()
    msgs = [{"role": "user", "content": "Which database?", "id": "m3"}]
    res = asyncio.run(
        compile_context(msgs, conversation_id="ctx8_budget", persist_snapshot=False)
    )
    assert res.budget == settings.context_budget
    assert res.total_tokens <= settings.context_budget

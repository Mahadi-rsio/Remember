"""Phase 8.8: comprehensive regression suite.

End-to-end tests through the archive -> memory -> compile pipeline that exercise
the full set of memory-correctness behaviors with varied, natural-language wording
(rather than a single hardcoded benchmark phrase set).

Covered scenarios (todo 8.8):
  - Basic facts persist
  - Corrections surface only the new value
  - Revocation removes the old value from compiled context
  - Questions never become memories
  - Contradictions collapse to the latest ACTIVE value
  - Stale information is never compiled once superseded
  - Unrelated memories are not injected into unrelated context
  - Conversation A memories never leak into conversation B
"""

from __future__ import annotations

import asyncio

from sqlmodel import select

from app.context.compiler import compile_context
from app.storage.archive import archive_request
from app.storage.db import session_scope
from app.storage.models import MemoryItem


def _compiled_text(conversation_id: str, query: str) -> str:
    msgs = [{"role": "user", "content": query, "id": "q"}]
    result = asyncio.run(
        compile_context(msgs, conversation_id=conversation_id, persist_snapshot=False)
    )
    return "\n".join(str(m.get("content") or "") for m in result.messages)


def _memory_contents(conversation_id: str) -> list[str]:
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == conversation_id)
        ).all()
        return [i.content for i in items]


def _active_contents(conversation_id: str) -> list[str]:
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(
                MemoryItem.conversation_id == conversation_id,
                MemoryItem.status == "active",
            )
        ).all()
        return [i.content for i in items]


# ---------------------------------------------------------------------------
# 1. Basic facts: declarative statements are persisted
# ---------------------------------------------------------------------------

def test_regression_basic_facts_are_persisted(tmp_db):
    archive_request(
        {
            "conversation_id": "reg_facts",
            "messages": [
                {"role": "user", "content": "I am building Cloudisy.", "id": "m1"},
                {"role": "user", "content": "Cloudisy uses PostgreSQL.", "id": "m2"},
                {"role": "user", "content": "I prefer TypeScript.", "id": "m3"},
            ],
        }
    )
    contents = _memory_contents("reg_facts")
    assert any("Cloudisy" in c for c in contents)
    assert any("PostgreSQL" in c for c in contents)
    assert any("TypeScript" in c for c in contents)


def test_regression_basic_facts_with_varied_wording(tmp_db):
    archive_request(
        {
            "conversation_id": "reg_facts_varied",
            "messages": [
                {"role": "user", "content": "We're putting together an app called NotesApp.", "id": "m1"},
                {"role": "user", "content": "The backend is written in Go.", "id": "m2"},
                {"role": "user", "content": "My favorite editor is Neovim.", "id": "m3"},
            ],
        }
    )
    contents = " ".join(_memory_contents("reg_facts_varied"))
    assert "NotesApp" in contents
    assert "Go" in contents
    assert "Neovim" in contents


# ---------------------------------------------------------------------------
# 2. Corrections: only the new value is compiled
# ---------------------------------------------------------------------------

def test_regression_correction_only_new_value_compiled(tmp_db):
    archive_request(
        {
            "conversation_id": "reg_corr",
            "messages": [{"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "reg_corr",
            "messages": [
                {"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"},
                {"role": "user", "content": "Actually, Cloudisy uses self-hosted PostgreSQL.", "id": "m2"},
            ],
        }
    )
    joined = _compiled_text("reg_corr", "What database does Cloudisy use?")
    assert "self-hosted PostgreSQL" in joined
    assert "Neon" not in joined


def test_regression_correction_varied_wording(tmp_db):
    archive_request(
        {
            "conversation_id": "reg_corr_var",
            "messages": [{"role": "user", "content": "Cloudisy relies on Neon for storage.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "reg_corr_var",
            "messages": [
                {"role": "user", "content": "Cloudisy relies on Neon for storage.", "id": "m1"},
                {"role": "user", "content": "Cloudisy now uses Postgres instead of Neon for storage.", "id": "m2"},
            ],
        }
    )
    joined = _compiled_text("reg_corr_var", "What storage engine does Cloudisy use?")
    assert "Postgres" in joined
    assert "Neon" not in joined


# ---------------------------------------------------------------------------
# 3. Revocation: revoked value excluded from compiled context
# ---------------------------------------------------------------------------

def test_regression_revocation_removes_value_from_context(tmp_db):
    archive_request(
        {
            "conversation_id": "reg_rev",
            "messages": [{"role": "user", "content": "The demo password is temp1234.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "reg_rev",
            "messages": [
                {"role": "user", "content": "The demo password is temp1234.", "id": "m1"},
                {"role": "user", "content": "The temporary password was reset; ignore temp1234.", "id": "m2"},
            ],
        }
    )
    joined = _compiled_text("reg_rev", "What is the demo password?")
    assert "temp1234" not in joined


def test_regression_revocation_varied_wording(tmp_db):
    archive_request(
        {
            "conversation_id": "reg_rev_var",
            "messages": [{"role": "user", "content": "The API key for staging is sk_live_abc.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "reg_rev_var",
            "messages": [
                {"role": "user", "content": "The API key for staging is sk_live_abc.", "id": "m1"},
                {"role": "user", "content": "That staging key has been revoked; forget sk_live_abc.", "id": "m2"},
            ],
        }
    )
    joined = _compiled_text("reg_rev_var", "What is the staging API key?")
    assert "sk_live_abc" not in joined


# ---------------------------------------------------------------------------
# 4. Questions: never become memories
# ---------------------------------------------------------------------------

def test_regression_questions_never_stored(tmp_db):
    archive_request(
        {
            "conversation_id": "reg_q",
            "messages": [
                {"role": "user", "content": "What is my name?", "id": "m1"},
                {"role": "user", "content": "What database do we use?", "id": "m2"},
            ],
        }
    )
    assert _memory_contents("reg_q") == []


def test_regression_questions_varied_wording(tmp_db):
    archive_request(
        {
            "conversation_id": "reg_q_var",
            "messages": [
                {"role": "user", "content": "Can you remind me what the deadline is?", "id": "m1"},
                {"role": "user", "content": "Which cloud provider hosts our service?", "id": "m2"},
            ],
        }
    )
    assert _memory_contents("reg_q_var") == []


# ---------------------------------------------------------------------------
# 5. Contradictions: only the latest ACTIVE value is compiled
# ---------------------------------------------------------------------------

def test_regression_contradiction_latest_wins(tmp_db):
    archive_request(
        {
            "conversation_id": "reg_contra",
            "messages": [{"role": "user", "content": "I prefer React.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "reg_contra",
            "messages": [
                {"role": "user", "content": "I prefer React.", "id": "m1"},
                {"role": "user", "content": "Actually, I prefer Vue.", "id": "m2"},
            ],
        }
    )
    joined = _compiled_text("reg_contra", "What frontend framework do I prefer?")
    assert "Vue" in joined
    assert "React" not in joined


def test_regression_contradiction_never_injects_both(tmp_db):
    archive_request(
        {
            "conversation_id": "reg_contra_both",
            "messages": [{"role": "user", "content": "The ORM we use is Sequelize.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "reg_contra_both",
            "messages": [
                {"role": "user", "content": "The ORM we use is Sequelize.", "id": "m1"},
                {"role": "user", "content": "Actually we moved to Prisma for the ORM.", "id": "m2"},
            ],
        }
    )
    joined = _compiled_text("reg_contra_both", "What ORM does the project use?")
    has_prisma = "Prisma" in joined
    has_sequelize = "Sequelize" in joined
    assert has_prisma != has_sequelize, f"Both conflicting values injected:\n{joined}"


# ---------------------------------------------------------------------------
# 6. Stale information: only the current value is compiled
# ---------------------------------------------------------------------------

def test_regression_stale_information_not_compiled(tmp_db):
    archive_request(
        {
            "conversation_id": "reg_stale",
            "messages": [{"role": "user", "content": "The deployment target is AWS Lambda.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "reg_stale",
            "messages": [
                {"role": "user", "content": "The deployment target is AWS Lambda.", "id": "m1"},
                {"role": "user", "content": "The deployment target is now GCP Cloud Run.", "id": "m2"},
            ],
        }
    )
    joined = _compiled_text("reg_stale", "Where is the app deployed?")
    assert "GCP Cloud Run" in joined
    assert "AWS Lambda" not in joined


def test_regression_stale_information_chain(tmp_db):
    """A three-step chain of updates must compile only the final value."""
    archive_request(
        {
            "conversation_id": "reg_stale_chain",
            "messages": [{"role": "user", "content": "The region is us-east-1.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "reg_stale_chain",
            "messages": [
                {"role": "user", "content": "The region is us-east-1.", "id": "m1"},
                {"role": "user", "content": "The region is now eu-west-1.", "id": "m2"},
            ],
        }
    )
    archive_request(
        {
            "conversation_id": "reg_stale_chain",
            "messages": [
                {"role": "user", "content": "The region is us-east-1.", "id": "m1"},
                {"role": "user", "content": "The region is now eu-west-1.", "id": "m2"},
                {"role": "user", "content": "The region is now ap-south-1.", "id": "m3"},
            ],
        }
    )
    joined = _compiled_text("reg_stale_chain", "What region are we in?")
    assert "ap-south-1" in joined
    assert "eu-west-1" not in joined
    assert "us-east-1" not in joined


# ---------------------------------------------------------------------------
# 7. Unrelated memories: not injected into unrelated context
# ---------------------------------------------------------------------------

def test_regression_unrelated_memory_not_injected(tmp_db):
    """Under budget pressure, a query-related memory wins over an unrelated one."""
    archive_request(
        {
            "conversation_id": "reg_unrel",
            "messages": [
                {"role": "user", "content": "My favorite color is teal.", "id": "m1"},
                {"role": "user", "content": "Cloudisy uses PostgreSQL.", "id": "m2"},
            ],
        }
    )
    # Constrain the budget so the selector must choose which canonical memory to
    # keep. The query is about the database, so the unrelated "teal" memory must
    # be deprioritized and dropped, while the related PostgreSQL memory is kept.
    msgs = [{"role": "user", "content": "What database does Cloudisy use?", "id": "q"}]
    result = asyncio.run(
        compile_context(msgs, conversation_id="reg_unrel", budget=30, persist_snapshot=False)
    )
    joined = "\n".join(str(m.get("content") or "") for m in result.messages)
    assert "PostgreSQL" in joined
    assert "teal" not in joined


def test_regression_related_memory_is_injected(tmp_db):
    """A query that does relate to a remembered fact should surface it."""
    archive_request(
        {
            "conversation_id": "reg_rel",
            "messages": [
                {"role": "user", "content": "Cloudisy uses PostgreSQL for its database.", "id": "m1"},
            ],
        }
    )
    joined = _compiled_text("reg_rel", "What database does Cloudisy use?")
    assert "PostgreSQL" in joined


# ---------------------------------------------------------------------------
# 8. Isolation: conversation A memories never appear in conversation B
# ---------------------------------------------------------------------------

def test_regression_conversation_isolation(tmp_db):
    archive_request(
        {
            "conversation_id": "reg_iso_a",
            "messages": [{"role": "user", "content": "I am building Cloudisy.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "reg_iso_b",
            "messages": [{"role": "user", "content": "I am building SomethingElse.", "id": "m1"}],
        }
    )
    # Conversation B's context must contain nothing from conversation A.
    joined_b = _compiled_text("reg_iso_b", "What project am I building?")
    assert "SomethingElse" in joined_b
    assert "Cloudisy" not in joined_b

    # And A's context must not contain B's fact.
    joined_a = _compiled_text("reg_iso_a", "What project am I building?")
    assert "Cloudisy" in joined_a
    assert "SomethingElse" not in joined_a


def test_regression_conversation_isolation_same_phrasing(tmp_db):
    """Identical wording in two conversations must stay isolated."""
    shared = "Cloudisy uses PostgreSQL."
    archive_request(
        {
            "conversation_id": "reg_iso_same_a",
            "messages": [{"role": "user", "content": shared, "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "reg_iso_same_b",
            "messages": [{"role": "user", "content": "Cloudisy uses MongoDB.", "id": "m1"}],
        }
    )
    joined_b = _compiled_text("reg_iso_same_b", "What database does Cloudisy use?")
    assert "MongoDB" in joined_b
    assert "PostgreSQL" not in joined_b

    joined_a = _compiled_text("reg_iso_same_a", "What database does Cloudisy use?")
    assert "PostgreSQL" in joined_a
    assert "MongoDB" not in joined_a

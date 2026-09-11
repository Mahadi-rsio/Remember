"""Phase 8.4: revocation / reset semantics (FIX.md §4 / todo 8.4)."""

from __future__ import annotations

import asyncio

from sqlmodel import select

from app.context.compiler import compile_context
from app.memory.extractor import extract_from_message
from app.memory.ids import normalize_message
from app.memory.revocation import parse_revocation
from app.models.memory import MemoryStatus
from app.storage.archive import archive_request
from app.storage.db import session_scope
from app.storage.models import MemoryItem


# --- Phrase detection unit tests ---

def test_parse_revocation_phrases():
    cases = [
        ("The demo password was reset.", "demo password"),
        ("The temporary password was reset; ignore temp1234.", "temporary password"),
        ("Ignore the previous password.", "password"),
        ("That password is no longer valid.", "password"),
        ("The API key has been revoked.", "API key"),
        ("Forget the previous value.", "value"),
        ("The temporary demo password was reset; ignore temp1234.", "temporary demo password"),
    ]
    for text, expected_target in cases:
        r = parse_revocation(text)
        assert r is not None, f"No revocation parsed for: {text!r}"
        assert expected_target.casefold() in r.target.casefold(), f"target mismatch: {text!r}"


def test_parse_revocation_value():
    r = parse_revocation("The temporary password was reset; ignore temp1234.")
    assert r is not None
    assert r.value == "temp1234"


def test_non_revocation_not_parsed():
    assert parse_revocation("Cloudisy uses PostgreSQL.") is None
    assert parse_revocation("I prefer TypeScript.") is None
    assert parse_revocation("The deployment target is AWS Lambda.") is None
    assert parse_revocation("We no longer use Neon.") is None


def test_revocation_extracts_as_revocation_candidate():
    for text in [
        "The demo password was reset.",
        "Ignore the previous password.",
        "That password is no longer valid.",
        "The API key has been revoked.",
        "Forget the previous value.",
        "The temporary password was reset; ignore temp1234.",
    ]:
        msg = normalize_message({"role": "user", "content": text, "id": "m"}, ordinal=0)
        cands = extract_from_message(msg)
        assert len(cands) == 1, f"No revocation candidate for: {text!r}"
        assert cands[0].revocation is not None, f"Expected revocation flag for: {text!r}"


# --- End-to-end revocation tests ---

def test_password_reset_marks_revoked(tmp_db):
    archive_request(
        {
            "conversation_id": "rev_password",
            "messages": [{"role": "user", "content": "The demo password is temp1234.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "rev_password",
            "messages": [
                {"role": "user", "content": "The demo password is temp1234.", "id": "m1"},
                {"role": "user", "content": "The temporary password was reset; ignore temp1234.", "id": "m2"},
            ],
        }
    )
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "rev_password")
        ).all()
        assert len(items) == 1
        assert items[0].status == MemoryStatus.REVOKED.value
        assert "temp1234" in items[0].content


def test_revoked_memory_excluded_from_compiled_context(tmp_db):
    """After reset, a later query must NOT return the revoked value."""
    archive_request(
        {
            "conversation_id": "rev_compile",
            "messages": [{"role": "user", "content": "The demo password is temp1234.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "rev_compile",
            "messages": [
                {"role": "user", "content": "The demo password is temp1234.", "id": "m1"},
                {"role": "user", "content": "The temporary password was reset; ignore temp1234.", "id": "m2"},
            ],
        }
    )
    msgs = [{"role": "user", "content": "What is the demo password?", "id": "m3"}]
    result = asyncio.run(
        compile_context(msgs, conversation_id="rev_compile", persist_snapshot=False)
    )
    joined = "\n".join(str(m.get("content") or "") for m in result.messages)
    assert "temp1234" not in joined


def test_ignore_previous_revokes(tmp_db):
    archive_request(
        {
            "conversation_id": "rev_ignore",
            "messages": [{"role": "user", "content": "The demo password is temp1234.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "rev_ignore",
            "messages": [
                {"role": "user", "content": "The demo password is temp1234.", "id": "m1"},
                {"role": "user", "content": "Ignore the previous password.", "id": "m2"},
            ],
        }
    )
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "rev_ignore")
        ).all()
        assert len(items) == 1
        assert items[0].status == MemoryStatus.REVOKED.value


def test_revocation_does_not_create_new_memory(tmp_db):
    """A revocation marks the old item revoked and adds no new row."""
    archive_request(
        {
            "conversation_id": "rev_nocreate",
            "messages": [{"role": "user", "content": "The demo password is temp1234.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "rev_nocreate",
            "messages": [
                {"role": "user", "content": "The demo password is temp1234.", "id": "m1"},
                {"role": "user", "content": "The temporary password was reset.", "id": "m2"},
            ],
        }
    )
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "rev_nocreate")
        ).all()
        assert len(items) == 1
        assert items[0].status == MemoryStatus.REVOKED.value

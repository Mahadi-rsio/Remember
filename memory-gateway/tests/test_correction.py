"""Phase 8.3: explicit correction semantics (FIX.md §3 / todo 8.3)."""

from __future__ import annotations

import json

from sqlmodel import select

from app.memory.correction import parse_correction, strip_correction_prefix
from app.memory.extractor import extract_from_message
from app.memory.ids import normalize_message
from app.models.memory import MemoryStatus
from app.storage.archive import archive_request
from app.storage.db import session_scope
from app.storage.models import CorrectionRecord, MemoryItem


# --- Phrase detection unit tests ---

def test_strip_correction_prefix():
    assert strip_correction_prefix("Actually, Cloudisy uses Neon.") == ("Cloudisy uses Neon.", True)
    assert strip_correction_prefix("Correction: it's PostgreSQL.") == ("it's PostgreSQL.", True)
    assert strip_correction_prefix("No, the target is AWS.") == ("the target is AWS.", True)
    assert strip_correction_prefix("Cloudisy uses Neon.") == ("Cloudisy uses Neon.", False)


def test_parse_changed_from_to():
    c = parse_correction("Cloudisy changed from Neon PostgreSQL to self-hosted PostgreSQL.")
    assert c is not None
    assert c.target == "Cloudisy"
    assert c.old_value == "Neon PostgreSQL"
    assert c.new_value == "self-hosted PostgreSQL"


def test_parse_uses_instead_of():
    c = parse_correction("Cloudisy now uses self-hosted PostgreSQL instead of Neon.")
    assert c is not None
    assert c.target == "Cloudisy"
    assert c.old_value == "Neon"
    assert c.new_value == "self-hosted PostgreSQL"


def test_parse_was_changed_to():
    c = parse_correction("The database was changed to self-hosted PostgreSQL.")
    assert c is not None
    assert c.target == "database"
    assert c.new_value == "self-hosted PostgreSQL"
    assert c.old_value == ""


def test_parse_changed_preference():
    c = parse_correction("I changed my preference from dark mode to light mode.")
    assert c is not None
    assert c.target == "preference"
    assert c.old_value == "dark mode"
    assert c.new_value == "light mode"


def test_parse_deployment_target_changed():
    c = parse_correction("The deployment target changed to AWS Lambda.")
    assert c is not None
    assert c.target == "deployment target"
    assert c.new_value == "AWS Lambda"


def test_non_correction_not_parsed():
    assert parse_correction("Cloudisy uses PostgreSQL.") is None
    assert parse_correction("I prefer TypeScript.") is None
    assert parse_correction("The deployment target is AWS Lambda.") is None


# --- Extraction tests ---

def test_correction_phrases_extract_as_corrections():
    cases = [
        "Actually, Cloudisy uses self-hosted PostgreSQL.",
        "Cloudisy changed from Neon to self-hosted PostgreSQL.",
        "Cloudisy now uses self-hosted PostgreSQL instead of Neon.",
        "The database was changed to self-hosted PostgreSQL.",
    ]
    for text in cases:
        msg = normalize_message({"role": "user", "content": text, "id": "m"}, ordinal=0)
        cands = extract_from_message(msg)
        assert len(cands) == 1, f"No correction candidate for: {text!r}"
        assert cands[0].is_correction, f"Expected correction flag for: {text!r}"


def test_preference_correction_extracts():
    msg = normalize_message(
        {"role": "user", "content": "I changed my preference from dark mode to light mode.", "id": "m"},
        ordinal=0,
    )
    cands = extract_from_message(msg)
    assert len(cands) == 1
    assert cands[0].is_correction
    assert cands[0].content == "light mode"
    assert cands[0].topic_key == "preference:theme"


# --- End-to-end supersede + structured record tests ---

def test_cloudisy_neon_to_postgres_correction(tmp_db):
    archive_request(
        {
            "conversation_id": "corr_cloudisy",
            "messages": [{"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "corr_cloudisy",
            "messages": [
                {"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"},
                {"role": "user", "content": "Actually, Cloudisy uses self-hosted PostgreSQL.", "id": "m2"},
            ],
        }
    )
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "corr_cloudisy")
        ).all()
        by_status = {i.status: i for i in items}
        assert MemoryStatus.SUPERSEDED.value in by_status
        assert MemoryStatus.ACTIVE.value in by_status
        assert "Neon" in by_status[MemoryStatus.SUPERSEDED.value].content
        assert "self-hosted PostgreSQL" in by_status[MemoryStatus.ACTIVE.value].content
        records = session.exec(
            select(CorrectionRecord).where(CorrectionRecord.conversation_id == "corr_cloudisy")
        ).all()
        assert len(records) >= 1
        assert "Neon" in records[0].old_value
        assert "self-hosted PostgreSQL" in records[0].new_value


def test_changed_from_to_correction(tmp_db):
    archive_request(
        {
            "conversation_id": "corr_changed",
            "messages": [{"role": "user", "content": "Cloudisy uses Neon PostgreSQL.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "corr_changed",
            "messages": [
                {"role": "user", "content": "Cloudisy uses Neon PostgreSQL.", "id": "m1"},
                {"role": "user", "content": "Cloudisy changed from Neon to self-hosted PostgreSQL.", "id": "m2"},
            ],
        }
    )
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "corr_changed")
        ).all()
        by_status = {i.status: i for i in items}
        assert "Neon" in by_status[MemoryStatus.SUPERSEDED.value].content
        assert "self-hosted PostgreSQL" in by_status[MemoryStatus.ACTIVE.value].content
        records = session.exec(
            select(CorrectionRecord).where(CorrectionRecord.conversation_id == "corr_changed")
        ).all()
        assert len(records) == 1
        assert records[0].old_value == "Neon"
        assert records[0].new_value == "self-hosted PostgreSQL"


def test_compiled_context_excludes_superseded(tmp_db):
    """The compiler must surface only the new value, never the superseded one."""
    archive_request(
        {
            "conversation_id": "corr_compile",
            "messages": [{"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "corr_compile",
            "messages": [
                {"role": "user", "content": "Cloudisy uses Neon.", "id": "m1"},
                {"role": "user", "content": "Actually, Cloudisy uses self-hosted PostgreSQL.", "id": "m2"},
            ],
        }
    )
    import asyncio

    from app.context.compiler import compile_context

    msgs = [{"role": "user", "content": "What database does Cloudisy use?", "id": "m3"}]
    result = asyncio.run(
        compile_context(msgs, conversation_id="corr_compile", persist_snapshot=False)
    )
    joined = "\n".join(str(m.get("content") or "") for m in result.messages)
    assert "self-hosted PostgreSQL" in joined
    assert "Neon" not in joined


def test_preference_correction_supersedes(tmp_db):
    archive_request(
        {
            "conversation_id": "corr_pref",
            "messages": [{"role": "user", "content": "I prefer dark mode.", "id": "m1"}],
        }
    )
    archive_request(
        {
            "conversation_id": "corr_pref",
            "messages": [
                {"role": "user", "content": "I prefer dark mode.", "id": "m1"},
                {"role": "user", "content": "I changed my preference from dark mode to light mode.", "id": "m2"},
            ],
        }
    )
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "corr_pref")
        ).all()
        by_status = {i.status: i for i in items}
        assert MemoryStatus.ACTIVE.value in by_status
        assert MemoryStatus.SUPERSEDED.value in by_status
        assert "dark mode" in by_status[MemoryStatus.SUPERSEDED.value].content
        assert "light mode" in by_status[MemoryStatus.ACTIVE.value].content
        records = session.exec(
            select(CorrectionRecord).where(CorrectionRecord.conversation_id == "corr_pref")
        ).all()
        assert len(records) >= 1

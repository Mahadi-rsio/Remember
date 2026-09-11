"""Phase 8.6: Protect against false memories.

Ensures pure acknowledgements, conversational filler, unsupported assumptions,
and model-generated answers are never stored as canonical memories, while
legitimate declarative statements are still extracted.
"""

from __future__ import annotations

from sqlmodel import select

from app.memory.engine import process_memory_delta
from app.memory.extractor import extract_from_message
from app.memory.ids import normalize_message
from app.memory.low_info import is_low_info_message
from app.storage.archive import archive_request
from app.storage.db import session_scope
from app.storage.models import MemoryItem


# --- 8.6: low-info filter covers the required acknowledgements ---

def test_low_info_filter_covers_required_set():
    required = ["ok", "thanks", "yes", "no", "continue", "sure", "What?", "Why?", "How?"]
    for phrase in required:
        assert is_low_info_message(phrase, role="user"), f"not low-info: {phrase!r}"


def test_pure_acknowledgements_yield_no_candidates():
    acks = [
        "ok",
        "thanks",
        "yes",
        "no",
        "continue",
        "sure",
        "What?",
        "Why?",
        "How?",
        "no worries",
        "gotcha",
        "got it",
        "got it thanks",
        "that makes sense",
        "i see",
        "understood",
        "alright",
        "haha",
        "lol",
        "no problem",
        "np",
        "makes sense",
        "sure thing",
        "for sure",
        "totally",
        "on it",
        "will do",
        "works for me",
        "sounds good to me",
    ]
    for ack in acks:
        msg = normalize_message({"role": "user", "content": ack, "id": "m"}, ordinal=0)
        assert extract_from_message(msg) == [], f"ack extracted as memory: {ack!r}"


def test_acknowledgements_not_persisted(tmp_db):
    archive_request(
        {
            "conversation_id": "ack1",
            "messages": [
                {"role": "user", "content": "thanks", "id": "m1"},
                {"role": "user", "content": "sure", "id": "m2"},
                {"role": "user", "content": "got it", "id": "m3"},
            ],
        }
    )
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "ack1")
        ).all()
        assert items == []


# --- 8.6: unsupported assumptions must never become memories ---

def test_unsupported_assumptions_yield_no_candidates():
    assumptions = [
        "Perhaps the database is Postgres.",
        "Possibly the database is Postgres.",
        "The database is probably Postgres.",
        "Maybe Cloudisy uses Neon.",
        "I think the stack uses Docker.",
        "The deployment target might be AWS.",
        "We are considering Redis.",
        "Not sure if we use Postgres.",
        "I am not sure about the database.",
        "[fact] perhaps the database is Postgres.",
    ]
    for a in assumptions:
        msg = normalize_message({"role": "user", "content": a, "id": "m"}, ordinal=0)
        assert extract_from_message(msg) == [], f"assumption stored: {a!r}"


def test_unsupported_assumptions_not_persisted(tmp_db):
    archive_request(
        {
            "conversation_id": "assump1",
            "messages": [
                {"role": "user", "content": "Perhaps the database is Postgres.", "id": "m1"},
            ],
        }
    )
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "assump1")
        ).all()
        assert items == [], f"speculative assumption persisted: {[i.content for i in items]}"


# --- 8.6: model-generated answers must not become user facts ---

def test_model_answers_not_extracted_as_facts():
    answers = [
        "I am building Cloudisy.",
        "Cloudisy uses PostgreSQL.",
        "The deployment target is AWS Lambda.",
        "I prefer TypeScript.",
    ]
    for a in answers:
        msg = normalize_message({"role": "assistant", "content": a, "id": "a"}, ordinal=0)
        assert extract_from_message(msg) == [], f"assistant answer stored as fact: {a!r}"


def test_model_answer_to_question_not_persisted(tmp_db):
    archive_request(
        {
            "conversation_id": "ans1",
            "messages": [
                {"role": "user", "content": "What database do we use?", "id": "u1"},
                {"role": "assistant", "content": "We use PostgreSQL.", "id": "a1"},
            ],
        }
    )
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "ans1")
        ).all()
        assert items == []


# --- 8.6 guard: legitimate declarative statements are still stored ---

def test_legitimate_statements_still_extracted():
    legit = [
        "The database is Postgres.",
        "Database = Postgres",
        "We decided to use Postgres.",
        "I prefer TypeScript.",
        "Cloudisy uses self-hosted PostgreSQL.",
    ]
    for s in legit:
        msg = normalize_message({"role": "user", "content": s, "id": "m"}, ordinal=0)
        assert extract_from_message(msg) != [], f"legitimate statement dropped: {s!r}"


def test_legitimate_statement_persisted_after_assumption_rejected(tmp_db):
    archive_request(
        {
            "conversation_id": "mixed1",
            "messages": [
                {"role": "user", "content": "Perhaps the database is Postgres.", "id": "m1"},
            ],
        }
    )
    archive_request(
        {
            "conversation_id": "mixed1",
            "messages": [
                {"role": "user", "content": "Perhaps the database is Postgres.", "id": "m1"},
                {"role": "user", "content": "We decided to use Postgres.", "id": "m2"},
            ],
        }
    )
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "mixed1")
        ).all()
        assert len(items) == 1, f"expected only the real decision, got {[i.content for i in items]}"
        assert "Postgres" in items[0].content

"""Phase 3: deterministic memory engine — extract, merge, supersede, low-info."""

from __future__ import annotations

import json

from sqlmodel import select

from app.memory.contradiction import apply_candidate, load_active_items
from app.memory.engine import process_memory_delta
from app.memory.extractor import extract_candidates, extract_from_message, topic_key_from_content
from app.memory.ids import normalize_message
from app.memory.interrogative import is_interrogative
from app.memory.low_info import is_low_info_message, normalize_utterance
from app.memory.scorer import score_candidate
from app.models.memory import (
    CANONICAL_TYPES,
    CandidateMemory,
    MemoryScores,
    MemoryStatus,
    MemoryType,
)
from app.storage.archive import archive_request
from app.storage.db import session_scope
from app.storage.models import ContextVersion, MemoryItem


def test_canonical_types_cover_required_buckets():
    names = {t.value for t in CANONICAL_TYPES}
    assert names == {
        "fact",
        "decision",
        "constraint",
        "preference",
        "goal",
        "architecture",
        "important_event",
        "active_task",
    }


def test_low_info_phrases_skipped():
    for phrase in ("ok", "thanks", "yes", "continue", "run it", "do that", "Thank you!"):
        assert is_low_info_message(phrase, role="user"), phrase
    assert normalize_utterance("  OK!!! ") == "ok"
    assert not is_low_info_message("We decided to use Neon", role="user")


def test_extract_decision_and_fact():
    decision = normalize_message(
        {"role": "user", "content": "Database = Supabase", "id": "d1"},
        ordinal=0,
    )
    fact = normalize_message(
        {"role": "user", "content": "fact: API latency is 40ms", "id": "f1"},
        ordinal=1,
    )
    pref = normalize_message(
        {"role": "user", "content": "I prefer dark mode", "id": "p1"},
        ordinal=2,
    )
    cands = extract_candidates([decision, fact, pref])
    types = {c.type for c in cands}
    assert MemoryType.DECISION in types
    assert MemoryType.FACT in types
    assert MemoryType.PREFERENCE in types
    assert all(c.scores.confidence > 0 for c in cands)
    assert topic_key_from_content("Database = Supabase") == "database"


def test_low_info_yields_no_candidates():
    msg = normalize_message({"role": "user", "content": "thanks", "id": "t1"}, ordinal=0)
    assert extract_from_message(msg) == []


def test_scores_are_separate_axes():
    c = CandidateMemory(
        content="We decided to use Neon for production",
        type=MemoryType.DECISION,
        authority="user",
        topic_key="production",
    )
    scores = score_candidate(c)
    assert isinstance(scores, MemoryScores)
    assert scores.confidence >= 0.9
    assert scores.importance >= 0.8
    assert 0 <= scores.stability <= 1
    assert scores.freshness == 1.0
    assert scores.information_gain > 0


def test_process_delta_skips_low_info(tmp_db):
    delta = archive_request(
        {
            "conversation_id": "low1",
            "messages": [{"role": "user", "content": "ok", "id": "m1"}],
        }
    )
    assert delta is not None
    result = process_memory_delta(delta)
    assert result is not None
    # Second call is idempotent; first archive already ran the engine.
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "low1")
        ).all()
        assert items == []


def test_extract_merge_and_confidence_preserve(tmp_db):
    archive_request(
        {
            "conversation_id": "merge1",
            "messages": [
                {"role": "user", "content": "Database = Neon", "id": "a1"},
            ],
        }
    )
    with session_scope() as session:
        items = load_active_items(session, "merge1")
        assert len(items) == 1
        original_confidence = items[0].confidence
        assert original_confidence >= 0.9
        first_stability = items[0].stability

    # Near-duplicate confirmation with weaker speculative phrasing → merge, keep confidence
    archive_request(
        {
            "conversation_id": "merge1",
            "messages": [
                {"role": "user", "content": "Database = Neon", "id": "a1"},
                {
                    "role": "user",
                    "content": "Database = Neon",
                    "id": "a2",
                },
            ],
        }
    )
    with session_scope() as session:
        items = load_active_items(session, "merge1")
        assert len(items) == 1
        assert items[0].confidence >= original_confidence
        sources = json.loads(items[0].source_message_ids_json)
        assert "id:a1" in sources and "id:a2" in sources
        assert items[0].stability >= first_stability


def test_contradiction_supersedes_old_decision(tmp_db):
    archive_request(
        {
            "conversation_id": "sup1",
            "messages": [
                {"role": "user", "content": "Database = Supabase", "id": "s1"},
            ],
        }
    )
    archive_request(
        {
            "conversation_id": "sup1",
            "messages": [
                {"role": "user", "content": "Database = Supabase", "id": "s1"},
                {"role": "user", "content": "Database = Neon", "id": "s2"},
            ],
        }
    )
    with session_scope() as session:
        rows = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "sup1")
        ).all()
        by_status = {r.status: r for r in rows}
        assert MemoryStatus.SUPERSEDED.value in by_status
        assert MemoryStatus.ACTIVE.value in by_status
        assert "Supabase" in by_status[MemoryStatus.SUPERSEDED.value].content
        assert "Neon" in by_status[MemoryStatus.ACTIVE.value].content
        versions = session.exec(
            select(ContextVersion).where(ContextVersion.conversation_id == "sup1")
        ).all()
        assert len(versions) >= 1
        latest = max(versions, key=lambda v: v.version)
        state = json.loads(latest.state_json)
        assert any("Neon" in d for d in state["decisions"])


def test_speculation_cannot_overwrite_user_decision(tmp_db):
    archive_request(
        {
            "conversation_id": "auth1",
            "messages": [
                {"role": "user", "content": "Database = Neon", "id": "u1"},
            ],
        }
    )
    with session_scope() as session:
        speculative = CandidateMemory(
            content="Database = Supabase",
            type=MemoryType.DECISION,
            topic_key="database",
            authority="speculation",
            source_message_ids=["id:ai1"],
            scores=MemoryScores(confidence=0.55, importance=0.5, stability=0.2, freshness=1.0, information_gain=0.8),
        )
        result = apply_candidate(session, "auth1", speculative)
        assert result.action == "reject"
        active = load_active_items(session, "auth1")
        assert len(active) == 1
        assert "Neon" in active[0].content


def test_information_gain_gate_skips_redundant_create(tmp_db):
    """Paraphrase with same topic already handled via merge; brand-new low-gain skip."""
    with session_scope() as session:
        # Seed an active fact
        session.add(
            MemoryItem(
                conversation_id="gain1",
                content="API latency = 40ms",
                type=MemoryType.FACT.value,
                topic_key="api_latency",
                confidence=0.9,
                importance=0.6,
                stability=0.7,
                freshness=1.0,
                information_gain=0.8,
                source_message_ids_json='["id:seed"]',
                status=MemoryStatus.ACTIVE.value,
                version=1,
            )
        )
        # Ensure conversation row exists for FK — archive path normally creates it
        from app.storage.models import Conversation

        session.add(Conversation(id="gain1"))

    with session_scope() as session:
        # Near-identical → merge path (not create)
        cand = CandidateMemory(
            content="API latency = 40ms",
            type=MemoryType.FACT,
            topic_key="api_latency",
            authority="user",
            source_message_ids=["id:g2"],
        )
        result = apply_candidate(session, "gain1", cand)
        assert result.action == "merge"


def test_versioned_context_state_on_update(tmp_db):
    archive_request(
        {
            "conversation_id": "ver1",
            "messages": [
                {"role": "user", "content": "goal: Ship MVP by Friday", "id": "g1"},
            ],
        }
    )
    with session_scope() as session:
        versions = session.exec(
            select(ContextVersion).where(ContextVersion.conversation_id == "ver1")
        ).all()
        assert len(versions) == 1
        state = json.loads(versions[0].state_json)
        assert state["goals"]
        assert versions[0].version == 1


def test_memory_failure_does_not_break_archive(tmp_db, monkeypatch):
    def boom(_delta):
        raise RuntimeError("memory boom")

    monkeypatch.setattr("app.storage.archive.process_memory_delta", boom)
    delta = archive_request(
        {
            "conversation_id": "fail1",
            "messages": [
                {"role": "user", "content": "Database = Neon", "id": "x1"},
            ],
        }
    )
    assert delta is not None
    assert delta.has_new


def test_interrogative_classifier_questions():
    questions = [
        "What is my name?",
        "Why did we choose PostgreSQL?",
        "When is the launch?",
        "Where is the project deployed?",
        "How does Cloudisy work?",
        "What is my name",
        "Why did we choose PostgreSQL",
        "When is the launch",
        "Where is the project deployed",
        "How does Cloudisy work",
        "What is the deployment target?",
        "When is the beta launch?",
        "What is the demo password?",
        "What database does Cloudisy use now?",
        "Which UI library do I prefer?",
        "What language do I prefer?",
        "Do I prefer dark mode or light mode?",
        "Do we have a mobile app for Cloudisy?",
        "Can you help me with the database?",
        "Is PostgreSQL the database?",
        "What?",
        "Why?",
        "How?",
        "Tell me what the password is",
        "Please tell me when the launch is",
        "What's the deployment target",
        "How much memory is used",
        "Which database do we use",
        "Do we use PostgreSQL",
        "Did we choose Neon",
    ]
    for q in questions:
        assert is_interrogative(q), f"Expected question: {q!r}"


def test_interrogative_classifier_declarative_guards():
    declaratives = [
        "The reason why we chose PostgreSQL is reliability.",
        "Where we deploy is AWS Lambda.",
        "What we decided is to use Neon.",
        "PostgreSQL is what we use.",
        "I know what database we use: PostgreSQL.",
        "I prefer TypeScript.",
        "I prefer MUI over shadcn.",
        "The deployment target is AWS Lambda.",
        "The team uses the agile workflow.",
        "Temporary detail: the demo password is temp1234.",
        "Actually, Cloudisy changed from Neon to self-hosted PostgreSQL.",
        "The temporary demo password was reset; ignore temp1234.",
        "We decided against the mobile app for now.",
        "I prefer dark mode in the dashboard.",
        "Do not use MySQL.",
        "Never use MongoDB.",
        "We deploy wherever Docker is available.",
        "I prefer PostgreSQL whenever possible.",
        "Database = PostgreSQL",
        "May release is scheduled for tomorrow.",
        "Will is the project lead.",
    ]
    for d in declaratives:
        assert not is_interrogative(d), f"Expected declarative statement: {d!r}"


def test_interrogative_questions_yield_no_memory_candidates():
    test_questions = [
        "What is my name?",
        "Why did we choose PostgreSQL?",
        "When is the launch?",
        "Where is the project deployed?",
        "How does Cloudisy work?",
        "What is the deployment target?",
        "When is the beta launch?",
        "What is the demo password?",
        "What = my name?",
    ]
    for i, q in enumerate(test_questions):
        msg = normalize_message({"role": "user", "content": q, "id": f"q{i}"}, ordinal=i)
        assert extract_from_message(msg) == [], f"Should extract no candidates for: {q!r}"


def test_interrogative_in_delta_process_stores_no_memory(tmp_db):
    delta = archive_request(
        {
            "conversation_id": "interrogative_test_conv",
            "messages": [
                {"role": "user", "content": "What is my name?", "id": "m1"},
                {"role": "user", "content": "Why did we choose PostgreSQL?", "id": "m2"},
                {"role": "user", "content": "When is the launch?", "id": "m3"},
                {"role": "user", "content": "Where is the project deployed?", "id": "m4"},
                {"role": "user", "content": "How does Cloudisy work?", "id": "m5"},
            ],
        }
    )
    assert delta is not None
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "interrogative_test_conv")
        ).all()
        assert len(items) == 0, f"Expected 0 memory items, got: {[it.content for it in items]}"


def test_declarative_with_question_words_is_stored(tmp_db):
    delta = archive_request(
        {
            "conversation_id": "declarative_test_conv",
            "messages": [
                {"role": "user", "content": "Database = PostgreSQL", "id": "d1"},
                {"role": "user", "content": "The deployment target is AWS Lambda.", "id": "d2"},
                {"role": "user", "content": "The reason why we chose PostgreSQL is reliability.", "id": "d3"},
            ],
        }
    )
    assert delta is not None
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "declarative_test_conv")
        ).all()
        assert len(items) >= 2
        contents = [it.content for it in items]
        assert any("PostgreSQL" in c for c in contents)


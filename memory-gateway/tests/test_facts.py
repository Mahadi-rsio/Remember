"""Unit tests for Phase 8.2: Natural-language fact extraction & normalization."""

import pytest

from app.memory.extractor import extract_candidates, extract_from_message
from app.memory.facts import (
    extract_building,
    extract_possessive,
    extract_preference,
    extract_structured_fact,
    extract_the_y_is_x,
    extract_uses,
)
from app.memory.ids import normalize_message
from app.models.memory import MemoryType


# --- 1. Pattern: "I am building X." ---

def test_pattern_building():
    cases = [
        ("I am building Cloudisy.", "Cloudisy", "Cloudisy"),
        ("I'm building an AI gateway.", "an AI gateway", "an AI gateway"),
        ("We are building MobileHub.", "MobileHub", "MobileHub"),
        ("We're building a web app called Cloudisy.", "Cloudisy", "Cloudisy"),
        ("Building Remember.", "Remember", "Remember"),
    ]
    for text, expected_entity, expected_val in cases:
        fact = extract_building(text)
        assert fact is not None, f"Failed for: {text}"
        assert fact.entity == expected_entity
        assert fact.attribute == "project"
        assert fact.value == expected_val
        assert fact.memory_type == MemoryType.FACT
        assert fact.to_topic_key() == "project"
        assert "Project = " in fact.to_content()


# --- 2. Pattern: "X uses Y." ---

def test_pattern_uses():
    cases = [
        ("Cloudisy uses Neon PostgreSQL.", "Cloudisy", "database", "Neon PostgreSQL", MemoryType.DECISION, "cloudisy_database"),
        ("Cloudisy uses self-hosted PostgreSQL.", "Cloudisy", "database", "self-hosted PostgreSQL", MemoryType.DECISION, "cloudisy_database"),
        ("The team uses the agile workflow.", "team", "workflow", "the agile workflow", MemoryType.FACT, "team_workflow"),
        ("The stack uses Postgres for project 1.", "stack", "database", "Postgres for project 1", MemoryType.DECISION, "stack_database"),
        ("Cloudisy uses Redis for caching.", "Cloudisy", "caching", "Redis for caching", MemoryType.DECISION, "cloudisy_caching"),
        ("MyApp uses React.", "MyApp", "frontend", "React", MemoryType.DECISION, "myapp_frontend"),
        ("MyApp uses Docker.", "MyApp", "technology", "Docker", MemoryType.FACT, "myapp_technology"),
    ]
    for text, expected_entity, expected_attr, expected_val, expected_type, expected_topic in cases:
        fact = extract_uses(text)
        assert fact is not None, f"Failed for: {text}"
        assert fact.entity == expected_entity
        assert fact.attribute == expected_attr
        assert fact.value == expected_val
        assert fact.memory_type == expected_type
        assert fact.to_topic_key() == expected_topic
        assert fact.to_content() == f"{expected_entity} {expected_attr} = {expected_val}"


# --- 3. Pattern: "X's Z is …" ---

def test_pattern_possessive():
    cases = [
        ("Cloudisy's beta launch is scheduled for next month.", "Cloudisy", "beta launch", "scheduled for next month", MemoryType.FACT, "cloudisy_beta_launch"),
        ("The project's deadline is Friday.", "The project", "deadline", "Friday", MemoryType.FACT, "the_project_deadline"),
        ("System's architecture is event-driven microservices.", "System", "architecture", "event-driven microservices", MemoryType.ARCHITECTURE, "system_architecture"),
        ("Team's goal is 99.9% uptime.", "Team", "goal", "99.9% uptime", MemoryType.GOAL, "team_goal"),
    ]
    for text, expected_entity, expected_attr, expected_val, expected_type, expected_topic in cases:
        fact = extract_possessive(text)
        assert fact is not None, f"Failed for: {text}"
        assert fact.entity == expected_entity
        assert fact.attribute == expected_attr
        assert fact.value == expected_val
        assert fact.memory_type == expected_type
        assert fact.to_topic_key() == expected_topic
        assert fact.to_content() == f"{expected_entity} {expected_attr} = {expected_val}"


# --- 4. Pattern: "I prefer X over Y." / "I prefer X." ---

def test_pattern_preference():
    cases = [
        ("I prefer MUI over shadcn.", "MUI over shadcn", "ui_library", "preference:ui_library"),
        ("I prefer TypeScript.", "TypeScript", "language", "preference:language"),
        ("I prefer dark mode in the dashboard.", "dark mode in the dashboard", "theme", "preference:theme"),
        ("I would rather use Vue than React.", "Vue over React", "frontend_framework", "preference:frontend_framework"),
        ("Preference: Tailwind over Bootstrap.", "Tailwind over Bootstrap", "ui_library", "preference:ui_library"),
    ]
    for text, expected_val, expected_attr, expected_topic in cases:
        fact = extract_preference(text)
        assert fact is not None, f"Failed for: {text}"
        assert fact.entity == "user"
        assert fact.attribute == expected_attr
        assert fact.value == expected_val
        assert fact.memory_type == MemoryType.PREFERENCE
        assert fact.to_topic_key() == expected_topic
        assert fact.to_content() == expected_val


# --- 5. Pattern: "The Y is X." ---

def test_pattern_the_y_is_x():
    cases = [
        ("The deployment target is AWS Lambda.", "deployment target", "AWS Lambda", MemoryType.DECISION, "deployment_target"),
        ("The demo password is temp1234.", "demo password", "temp1234", MemoryType.FACT, "demo_password"),
        ("Temporary detail: the demo password is temp1234.", "demo password", "temp1234", MemoryType.FACT, "demo_password"),
        ("The region is eu-west-1.", "region", "eu-west-1", MemoryType.FACT, "region"),
        ("The alert channel is #team-1.", "alert channel", "#team-1", MemoryType.FACT, "alert_channel"),
        ("The budget is 5000 dollars.", "budget", "5000 dollars", MemoryType.FACT, "budget"),
        ("The deadline is Q2.", "deadline", "Q2", MemoryType.FACT, "deadline"),
        ("The owner is Alice.", "owner", "Alice", MemoryType.FACT, "owner"),
        ("My name is Mahadi.", "name", "Mahadi", MemoryType.FACT, "name"),
    ]
    for text, expected_attr, expected_val, expected_type, expected_topic in cases:
        fact = extract_the_y_is_x(text)
        assert fact is not None, f"Failed for: {text}"
        assert fact.attribute == expected_attr
        assert fact.value == expected_val
        assert fact.memory_type == expected_type
        assert fact.to_topic_key() == expected_topic


# --- End-to-end extract_from_message tests ---

def test_extract_from_message_all_natural_patterns():
    statements = [
        ("I am building Cloudisy.", MemoryType.FACT, "Project = Cloudisy", "project"),
        ("Cloudisy uses Neon PostgreSQL.", MemoryType.DECISION, "Cloudisy database = Neon PostgreSQL", "cloudisy_database"),
        ("Cloudisy's beta launch is scheduled for next month.", MemoryType.FACT, "Cloudisy beta launch = scheduled for next month", "cloudisy_beta_launch"),
        ("I prefer MUI over shadcn.", MemoryType.PREFERENCE, "MUI over shadcn", "preference:ui_library"),
        ("The deployment target is AWS Lambda.", MemoryType.DECISION, "Deployment target = AWS Lambda", "deployment_target"),
        ("I prefer TypeScript.", MemoryType.PREFERENCE, "TypeScript", "preference:language"),
        ("My name is Mahadi.", MemoryType.FACT, "Name = Mahadi", "name"),
        ("Temporary detail: the demo password is temp1234.", MemoryType.FACT, "Demo password = temp1234", "demo_password"),
    ]
    for text, expected_type, expected_content, expected_topic in statements:
        msg = normalize_message({"role": "user", "content": text, "id": "m1"}, ordinal=0)
        cands = extract_from_message(msg)
        assert len(cands) == 1, f"Expected 1 candidate for: {text!r}, got {len(cands)}"
        c = cands[0]
        assert c.type == expected_type, f"Type mismatch for {text}: {c.type} != {expected_type}"
        assert c.content == expected_content, f"Content mismatch for {text}: {c.content} != {expected_content}"
        assert c.topic_key == expected_topic, f"Topic mismatch for {text}: {c.topic_key} != {expected_topic}"
        assert c.structured_fact is not None, f"Expected structured_fact on {text}"


def test_assistant_natural_language_not_extracted():
    msg = normalize_message({"role": "assistant", "content": "I am building Cloudisy.", "id": "a1"}, ordinal=0)
    assert extract_from_message(msg) == []

    msg2 = normalize_message({"role": "assistant", "content": "Cloudisy uses PostgreSQL.", "id": "a2"}, ordinal=0)
    assert extract_from_message(msg2) == []


def test_interrogatives_never_yield_facts():
    questions = [
        "What is my name?",
        "What am I building?",
        "What database does Cloudisy use now?",
        "Which UI library do I prefer?",
        "What is the deployment target for Cloudisy?",
        "What language do I prefer?",
        "When is Cloudisy's beta launch?",
        "What is the demo password?",
        "Why did we choose PostgreSQL?",
        "How does Cloudisy work?",
    ]
    for q in questions:
        msg = normalize_message({"role": "user", "content": q, "id": "q1"}, ordinal=0)
        assert extract_from_message(msg) == [], f"Question extracted as fact: {q!r}"


def test_natural_fact_superseding(tmp_db):
    from app.storage.archive import archive_request
    from app.storage.db import session_scope
    from sqlmodel import select
    from app.storage.models import MemoryItem
    from app.models.memory import MemoryStatus

    archive_request(
        {
            "conversation_id": "nat_sup1",
            "messages": [
                {"role": "user", "content": "Cloudisy uses Neon PostgreSQL.", "id": "m1"},
            ],
        }
    )
    archive_request(
        {
            "conversation_id": "nat_sup1",
            "messages": [
                {"role": "user", "content": "Cloudisy uses Neon PostgreSQL.", "id": "m1"},
                {"role": "user", "content": "Cloudisy uses self-hosted PostgreSQL.", "id": "m2"},
            ],
        }
    )
    with session_scope() as session:
        items = session.exec(
            select(MemoryItem).where(MemoryItem.conversation_id == "nat_sup1")
        ).all()
        by_status = {i.status: i for i in items}
        assert MemoryStatus.SUPERSEDED.value in by_status
        assert MemoryStatus.ACTIVE.value in by_status
        assert "Neon" in by_status[MemoryStatus.SUPERSEDED.value].content
        assert "self-hosted" in by_status[MemoryStatus.ACTIVE.value].content

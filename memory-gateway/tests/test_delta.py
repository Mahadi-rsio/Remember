"""Phase 2: delta detection, archive writer, isolation keys."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app.config import get_settings
from app.main import create_app
from app.memory.delta import detect_delta
from app.memory.ids import normalize_message, normalize_messages
from app.memory.isolation import derive_isolation_keys
from app.storage.archive import archive_request, list_archived_keys
from app.storage.db import session_scope
from app.storage.models import Conversation, Message
from tests.test_proxy import FakeProvider


def test_normalize_prefers_client_message_id():
    msg = normalize_message(
        {"role": "user", "content": "hello", "id": "msg-1"},
        ordinal=0,
    )
    assert msg.message_key == "id:msg-1"
    assert msg.client_message_id == "msg-1"


def test_normalize_hash_fallback_is_stable():
    a = normalize_message({"role": "user", "content": "hello"}, ordinal=0)
    b = normalize_message({"role": "user", "content": "hello"}, ordinal=0)
    c = normalize_message({"role": "user", "content": "hello"}, ordinal=1)
    assert a.message_key == b.message_key
    assert a.message_key.startswith("hash:")
    # Same content at different ordinals without ids are distinct turns
    assert a.message_key != c.message_key


def test_isolation_explicit_conversation_and_user():
    conv_id, user = derive_isolation_keys(
        {
            "conversation_id": "conv-42",
            "user": "alice",
            "messages": [{"role": "user", "content": "hi"}],
        }
    )
    assert conv_id == "conv-42"
    assert user == "alice"


def test_isolation_header_overrides_missing_body_id():
    conv_id, user = derive_isolation_keys(
        {"messages": [{"role": "user", "content": "hi"}], "user": "bob"},
        headers={"X-Conversation-Id": "from-header"},
    )
    assert conv_id == "from-header"
    assert user == "bob"


def test_isolation_fingerprint_stable_as_history_grows():
    first = {"messages": [{"role": "user", "content": "start"}], "user": "u1"}
    grown = {
        "user": "u1",
        "messages": [
            {"role": "user", "content": "start"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "more"},
        ],
    }
    a, _ = derive_isolation_keys(first)
    b, _ = derive_isolation_keys(grown)
    assert a == b
    assert a.startswith("u:u1:")


def test_delta_new_then_duplicate_ignored(tmp_db):
    body = {
        "conversation_id": "c1",
        "messages": [
            {"role": "user", "content": "one", "id": "m1"},
            {"role": "assistant", "content": "two", "id": "m2"},
        ],
    }
    first = archive_request(body)
    assert first is not None
    assert first.has_new
    assert len(first.new_messages) == 2
    assert list_archived_keys("c1") == {"id:m1", "id:m2"}

    second = archive_request(body)
    assert second is not None
    assert not second.has_new
    assert len(second.duplicate_messages) == 2
    assert list_archived_keys("c1") == {"id:m1", "id:m2"}


def test_delta_retry_with_extra_new_message(tmp_db):
    archive_request(
        {
            "conversation_id": "c2",
            "messages": [{"role": "user", "content": "hi", "id": "a"}],
        }
    )
    delta = archive_request(
        {
            "conversation_id": "c2",
            "messages": [
                {"role": "user", "content": "hi", "id": "a"},
                {"role": "assistant", "content": "hello", "id": "b"},
                {"role": "user", "content": "again", "id": "c"},
            ],
        }
    )
    assert delta is not None
    assert [m.client_message_id for m in delta.new_messages] == ["b", "c"]
    assert [m.client_message_id for m in delta.duplicate_messages] == ["a"]


def test_delta_reorder_does_not_reprocess(tmp_db):
    msgs = [
        {"role": "user", "content": "x", "id": "1"},
        {"role": "user", "content": "y", "id": "2"},
    ]
    archive_request({"conversation_id": "c3", "messages": msgs})
    reordered = [
        {"role": "user", "content": "y", "id": "2"},
        {"role": "user", "content": "x", "id": "1"},
    ]
    delta = archive_request({"conversation_id": "c3", "messages": reordered})
    assert delta is not None
    assert not delta.has_new


def test_delta_hash_retry_without_ids(tmp_db):
    payload = {
        "conversation_id": "c4",
        "messages": [
            {"role": "user", "content": "plain"},
            {"role": "assistant", "content": "reply"},
        ],
    }
    first = archive_request(payload)
    assert first is not None and len(first.new_messages) == 2
    retry = archive_request(payload)
    assert retry is not None and not retry.has_new


def test_conversations_isolated_by_key(tmp_db):
    archive_request(
        {
            "conversation_id": "left",
            "messages": [{"role": "user", "content": "same", "id": "shared"}],
        }
    )
    archive_request(
        {
            "conversation_id": "right",
            "messages": [{"role": "user", "content": "same", "id": "shared"}],
        }
    )
    assert list_archived_keys("left") == {"id:shared"}
    assert list_archived_keys("right") == {"id:shared"}
    with session_scope() as session:
        count = len(session.exec(select(Message)).all())
        assert count == 2
        users = {c.id for c in session.exec(select(Conversation)).all()}
        assert users == {"left", "right"}


def test_detect_delta_missing_prior_turn_ok(tmp_db):
    """Client omits older messages; already-archived keys stay processed."""
    archive_request(
        {
            "conversation_id": "c5",
            "messages": [
                {"role": "user", "content": "old", "id": "old"},
                {"role": "user", "content": "new", "id": "new"},
            ],
        }
    )
    with session_scope() as session:
        delta = detect_delta(
            session,
            conversation_id="c5",
            user_key=None,
            messages=[{"role": "user", "content": "new", "id": "new"}],
        )
    assert not delta.has_new
    assert list_archived_keys("c5") == {"id:old", "id:new"}


def test_proxy_archives_without_changing_response(tmp_db):
    get_settings.cache_clear()
    app = create_app()
    fake = FakeProvider()
    with TestClient(app) as client:
        app.state.upstream_provider = fake
        payload = {
            "model": "gpt-test",
            "conversation_id": "proxy-conv",
            "messages": [{"role": "user", "content": "hi", "id": "p1"}],
        }
        response = client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        assert response.content == fake.chat_result.content
        assert list_archived_keys("proxy-conv") == {"id:p1"}

        # Retry must still passthrough identically and not duplicate archive rows.
        response2 = client.post("/v1/chat/completions", json=payload)
        assert response2.content == fake.chat_result.content
        with session_scope() as session:
            rows = session.exec(
                select(Message).where(Message.conversation_id == "proxy-conv")
            ).all()
            assert len(rows) == 1


def test_archive_failure_does_not_break_proxy(tmp_db, monkeypatch):
    get_settings.cache_clear()
    app = create_app()
    fake = FakeProvider()

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("app.api.proxy.archive_request", boom)
    with TestClient(app) as client:
        app.state.upstream_provider = fake
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-test", "messages": [{"role": "user", "content": "x"}]},
        )
    assert response.status_code == 200
    assert response.content == fake.chat_result.content


def test_tool_role_archived(tmp_db):
    delta = archive_request(
        {
            "conversation_id": "tools",
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "run"},
                {
                    "role": "tool",
                    "content": json.dumps({"ok": True}),
                    "tool_call_id": "call_1",
                },
            ],
        }
    )
    assert delta is not None
    roles = [m.role for m in delta.new_messages]
    assert roles == ["system", "user", "tool"]
    assert "id:tool:call_1" in list_archived_keys("tools")


def test_normalize_messages_preserves_order():
    msgs = normalize_messages(
        [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]
    )
    assert [m.ordinal for m in msgs] == [0, 1]

"""Tests for Phase 6: FTS retrieval and version-aware cache."""
from __future__ import annotations

import pytest
from app.storage.db import init_db, reset_engine, session_scope
from app.storage.models import Conversation, Message, MemoryItem
from app.retrieval.fts import FTSRetriever
from app.retrieval.embeddings import EmbeddingRetriever
from app.cache.memory_cache import InMemoryCache, make_cache_key, make_request_key


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_retrieval.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_file))
    from app.config import get_settings
    get_settings.cache_clear()
    reset_engine()
    init_db(str(db_file))
    yield db_file
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def seeded_db(tmp_db):
    """DB with one conversation, two messages, one memory item."""
    with session_scope() as session:
        conv = Conversation(id="conv-1", user_key="user-a")
        session.add(conv)
        session.flush()
        m1 = Message(
            conversation_id="conv-1",
            message_key="msg-001",
            role="user",
            content="What is the capital of France?",
            content_hash="aaa",
            ordinal=0,
        )
        m2 = Message(
            conversation_id="conv-1",
            message_key="msg-002",
            role="assistant",
            content="The capital of France is Paris.",
            content_hash="bbb",
            ordinal=1,
        )
        mi = MemoryItem(
            conversation_id="conv-1",
            content="User prefers concise answers about geography",
            type="preferences",
            topic_key="geography",
            status="active",
        )
        session.add_all([m1, m2, mi])
    return tmp_db


# ── FTS retrieval tests ───────────────────────────────────────────────────────

class TestFTSRetriever:
    def test_search_messages_finds_match(self, seeded_db):
        retriever = FTSRetriever()
        results = retriever.search_messages("France", "conv-1")
        assert len(results) >= 1
        assert any("France" in r.content for r in results)

    def test_search_messages_no_match(self, seeded_db):
        retriever = FTSRetriever()
        results = retriever.search_messages("quantum mechanics", "conv-1")
        assert results == []

    def test_search_memory_finds_match(self, seeded_db):
        retriever = FTSRetriever()
        results = retriever.search_memory("geography", "conv-1")
        assert len(results) >= 1
        assert any("geography" in r.content or r.topic_key == "geography" for r in results)

    def test_search_memory_no_match(self, seeded_db):
        retriever = FTSRetriever()
        results = retriever.search_memory("astrophysics", "conv-1")
        assert results == []

    def test_search_all_combines(self, seeded_db):
        retriever = FTSRetriever()
        results = retriever.search_all("France", "conv-1")
        sources = {r.source for r in results}
        assert "messages" in sources

    def test_empty_query_returns_empty(self, seeded_db):
        retriever = FTSRetriever()
        assert retriever.search_messages("", "conv-1") == []
        assert retriever.search_memory("  ", "conv-1") == []

    def test_wrong_conversation_returns_empty(self, seeded_db):
        retriever = FTSRetriever()
        results = retriever.search_messages("France", "conv-NONEXISTENT")
        assert results == []


class TestEmbeddingRetrieverStub:
    def test_stub_returns_empty(self):
        r = EmbeddingRetriever()
        assert r.search_messages("anything", "conv-1") == []
        assert r.search_memory("anything", "conv-1") == []
        assert r.search_all("anything", "conv-1") == []


# ── cache tests ───────────────────────────────────────────────────────────────

class TestInMemoryCache:
    def test_set_and_get(self):
        cache = InMemoryCache()
        cache.set("k1", {"data": 42})
        assert cache.get("k1") == {"data": 42}

    def test_miss_returns_none(self):
        cache = InMemoryCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self):
        import time
        cache = InMemoryCache()
        cache.set("k", "val", ttl_seconds=1)
        assert cache.get("k") == "val"
        time.sleep(1.1)
        assert cache.get("k") is None

    def test_delete(self):
        cache = InMemoryCache()
        cache.set("k", "val")
        cache.delete("k")
        assert cache.get("k") is None

    def test_clear_prefix(self):
        cache = InMemoryCache()
        cache.set("conv-1:v2:abc", 1)
        cache.set("conv-1:v2:def", 2)
        cache.set("conv-2:v1:ghi", 3)
        cache.clear_prefix("conv-1")
        assert cache.get("conv-1:v2:abc") is None
        assert cache.get("conv-1:v2:def") is None
        assert cache.get("conv-2:v1:ghi") == 3

    def test_max_size_eviction(self):
        cache = InMemoryCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # evicts 'a'
        assert cache.get("a") is None
        assert cache.get("d") == 4


class TestCacheKeys:
    def test_make_cache_key_stable(self):
        k1 = make_cache_key("extraction", "conv-1", 5, {"a": 1})
        k2 = make_cache_key("extraction", "conv-1", 5, {"a": 1})
        assert k1 == k2

    def test_different_context_version_differs(self):
        k1 = make_cache_key("retrieval", "conv-1", 5, "query")
        k2 = make_cache_key("retrieval", "conv-1", 6, "query")
        assert k1 != k2

    def test_different_namespace_differs(self):
        k1 = make_cache_key("compilation", "conv-1", 1, "x")
        k2 = make_cache_key("request", "conv-1", 1, "x")
        assert k1 != k2

    def test_make_request_key(self):
        body = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
        k1 = make_request_key("conv-1", 3, body)
        k2 = make_request_key("conv-1", 3, body)
        assert k1 == k2
        k3 = make_request_key("conv-1", 4, body)  # different context version
        assert k1 != k3

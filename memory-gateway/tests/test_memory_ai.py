"""Tests for Phase 4: Optional Memory AI compressor, schema validation, and failure isolation."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.memory.compressor import compress_tool_message, memory_ai_output_to_candidates
from app.memory.delta import DeltaResult
from app.memory.engine import process_memory_delta, process_memory_delta_async
from app.memory.ids import NormalizedMessage
from app.memory.state import list_memory_items
from app.models.memory import MemoryAIOutput, MemoryStatus, MemoryType
from app.providers.base import AIProvider, ProviderResponse
from app.providers.memory_ai import MemoryAIAdapter, create_memory_ai_adapter, extract_json_text
from app.storage.archive import archive_request_async
from app.storage.db import session_scope
from app.storage.models import Message


class StubMainProvider(AIProvider):
    """Stub main upstream AI provider (mandatory for answers)."""

    def __init__(self, answer: str = "Hello from main AI"):
        self.answer = answer
        self.chat_calls: list[dict[str, Any]] = []

    async def chat(self, body: dict[str, Any]) -> ProviderResponse:
        self.chat_calls.append(body)
        payload = {
            "id": "chatcmpl-main",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": self.answer}}],
        }
        return ProviderResponse(
            status_code=200,
            content=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
        )

    async def responses(self, body: dict[str, Any]) -> ProviderResponse:
        return await self.chat(body)

    async def models(self) -> ProviderResponse:
        return ProviderResponse(
            status_code=200,
            content=b'{"data": [{"id": "gpt-4o"}]}',
            headers={"content-type": "application/json"},
        )

    async def stream(self, path: str, body: dict[str, Any]):
        yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        yield b"data: [DONE]\n\n"

    async def aclose(self) -> None:
        pass


def test_memory_ai_config_defaults_and_factory(monkeypatch):
    """Verify settings defaults and adapter factory toggle."""
    monkeypatch.delenv("MEMORY_AI_ENABLED", raising=False)
    get_settings.cache_clear()
    cfg = get_settings()
    assert cfg.memory_ai_enabled is False
    assert create_memory_ai_adapter(cfg) is None

    monkeypatch.setenv("MEMORY_AI_ENABLED", "true")
    monkeypatch.setenv("MEMORY_AI_MODEL", "meta-llama/llama-3-8b-instruct")
    monkeypatch.setenv("MEMORY_AI_TIMEOUT", "15.0")
    get_settings.cache_clear()
    cfg2 = get_settings()
    assert cfg2.memory_ai_enabled is True
    assert cfg2.memory_ai_model == "meta-llama/llama-3-8b-instruct"
    assert cfg2.memory_ai_timeout == 15.0
    adapter = create_memory_ai_adapter(cfg2)
    assert adapter is not None
    assert isinstance(adapter, MemoryAIAdapter)
    assert adapter._timeout == 15.0


def test_extract_json_text_helper():
    """Verify JSON block extraction handles markdown fences and raw text."""
    raw = '```json\n{"summary": "test", "confidence": 0.9}\n```'
    assert extract_json_text(raw) == '{"summary": "test", "confidence": 0.9}'

    surrounded = 'Prefix text\n```\n{"summary": "nested"}\n```\nSuffix'
    assert extract_json_text(surrounded) == '{"summary": "nested"}'

    plain = '   {"summary": "plain"}   '
    assert extract_json_text(plain) == '{"summary": "plain"}'


@pytest.mark.asyncio
async def test_memory_ai_adapter_success():
    """Mocked Memory AI returning valid structured JSON."""
    valid_payload = {
        "summary": "Decided to use SQLite for MVP persistence.",
        "facts": ["OS is Linux Ubuntu 22.04"],
        "decisions": ["Use SQLite for MVP persistence"],
        "constraints": ["Do not use Redis for Phase 1-4"],
        "preferences": ["Prefer async/await syntax"],
        "goals": ["Build an OpenAI-compatible context compression gateway"],
        "architecture": ["FastAPI + SQLite + OpenAI compatible proxy"],
        "important_events": ["Completed Phase 3 deterministic engine"],
        "active_tasks": ["Implement Phase 4 Memory AI"],
        "obsolete_items": [],
        "contradictions": [],
        "confidence": 0.95,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        data = {
            "choices": [{"message": {"role": "assistant", "content": json.dumps(valid_payload)}}]
        }
        return httpx.Response(200, json=data)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://mock.memory.ai/v1")
    adapter = MemoryAIAdapter(
        base_url="https://mock.memory.ai/v1",
        api_key="secret",
        model="cheap-model",
        client=client,
    )

    output = await adapter.extract_memory("User: We decided to use SQLite for MVP")
    assert output is not None
    assert output.summary == "Decided to use SQLite for MVP persistence."
    assert output.decisions == ["Use SQLite for MVP persistence"]
    assert output.confidence == 0.95
    assert output.active_tasks == ["Implement Phase 4 Memory AI"]


@pytest.mark.asyncio
async def test_memory_ai_adapter_retry_once_recovery():
    """Verify adapter retries once on parse error and succeeds if second attempt is valid."""
    attempts = 0

    valid_payload = {
        "summary": "Recovered after retry",
        "facts": ["Fact 1"],
        "decisions": [],
        "constraints": [],
        "preferences": [],
        "goals": [],
        "architecture": [],
        "important_events": [],
        "active_tasks": [],
        "obsolete_items": [],
        "contradictions": [],
        "confidence": 0.9,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            # First attempt: invalid JSON
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "Not JSON at all"}}]})
        # Second attempt (retry): valid JSON
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": json.dumps(valid_payload)}}]})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://mock.memory.ai/v1")
    adapter = MemoryAIAdapter(
        base_url="https://mock.memory.ai/v1",
        api_key="secret",
        model="cheap-model",
        retry_once=True,
        client=client,
    )

    output = await adapter.extract_memory("User message")
    assert attempts == 2
    assert output is not None
    assert output.summary == "Recovered after retry"
    assert output.facts == ["Fact 1"]


@pytest.mark.asyncio
async def test_memory_ai_adapter_retry_once_failure_isolation():
    """Verify adapter returns None without throwing when retry also fails."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "{broken json..."}}]})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://mock.memory.ai/v1")
    adapter = MemoryAIAdapter(
        base_url="https://mock.memory.ai/v1",
        api_key="secret",
        model="cheap-model",
        retry_once=True,
        client=client,
    )

    output = await adapter.extract_memory("User message")
    assert attempts == 2
    assert output is None  # Keeps prior memory, does not raise


@pytest.mark.asyncio
async def test_memory_ai_adapter_network_failure_isolation():
    """Verify HTTP 500 / connection failure returns None and does not crash."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"Internal Server Error")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://mock.memory.ai/v1")
    adapter = MemoryAIAdapter(
        base_url="https://mock.memory.ai/v1",
        api_key="secret",
        model="cheap-model",
        client=client,
    )

    output = await adapter.extract_memory("User message")
    assert output is None


@pytest.mark.asyncio
async def test_tool_output_compression(tmp_db):
    """Verify tool output compression produces a concise summary and preserves raw in archive."""
    tool_summary_payload = {
        "summary": "Ran test suite; 42 passed in 1.8s.",
        "key_points": ["42 passed", "1 warning"],
        "status": "success",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": json.dumps(tool_summary_payload)}}]})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://mock.memory.ai/v1")
    adapter = MemoryAIAdapter(
        base_url="https://mock.memory.ai/v1",
        api_key="secret",
        model="cheap-model",
        client=client,
    )

    long_output = "pytest execution log:\n" + ("PASSED test_step\n" * 50) + "42 passed, 1 warning in 1.8s"
    norm_msg = NormalizedMessage(
        role="tool",
        content=long_output,
        message_key="tool_msg_1",
        content_hash="hash1",
        client_message_id="tool_1",
        ordinal=1,
        raw={"name": "bash_test_runner"},
    )

    compressed = await compress_tool_message(norm_msg, adapter=adapter)
    assert "[Tool: bash_test_runner | success]" in compressed
    assert "Ran test suite; 42 passed in 1.8s." in compressed
    assert len(compressed) < len(long_output)

    # Verify short tool output is not unnecessarily altered
    short_msg = NormalizedMessage(
        role="tool",
        content="success",
        message_key="tool_msg_2",
        content_hash="hash2",
        client_message_id="tool_2",
        ordinal=2,
        raw={"name": "git_status"},
    )
    short_compressed = await compress_tool_message(short_msg, adapter=adapter)
    assert short_compressed == "success"


@pytest.mark.asyncio
async def test_process_memory_delta_with_memory_ai(tmp_db):
    """Verify end-to-end memory delta processing with Memory AI output."""
    conv_id = "test-conv-ai"
    m1 = NormalizedMessage(
        role="user",
        content="We are migrating from Postgres to CockroachDB for global multi-region.",
        message_key="m1",
        content_hash="h1",
        client_message_id=None,
        ordinal=0,
        raw={"role": "user", "content": "We are migrating from Postgres to CockroachDB for global multi-region."},
    )
    delta = DeltaResult(
        conversation_id=conv_id,
        user_key=None,
        all_messages=[m1],
        new_messages=[m1],
    )

    ai_output = MemoryAIOutput(
        summary="User decided to migrate to CockroachDB for multi-region.",
        decisions=["Migrate to CockroachDB for global multi-region"],
        architecture=["CockroachDB multi-region"],
        confidence=0.96,
    )

    result = process_memory_delta(delta, memory_ai_output=ai_output)
    assert result is not None
    assert result.updated is True
    assert result.context_version == 1

    with session_scope() as session:
        active = list_memory_items(session, conv_id, status=MemoryStatus.ACTIVE.value)
        contents = [item.content for item in active]
        assert "Migrate to CockroachDB for global multi-region" in contents
        assert "CockroachDB multi-region" in contents

    # Second turn with obsolete item flagging
    m2 = NormalizedMessage(
        role="user",
        content="CockroachDB was too expensive. We decided to stick with Postgres.",
        message_key="m2",
        content_hash="h2",
        client_message_id=None,
        ordinal=1,
        raw={"role": "user", "content": "CockroachDB was too expensive. We decided to stick with Postgres."},
    )
    delta2 = DeltaResult(
        conversation_id=conv_id,
        user_key=None,
        all_messages=[m1, m2],
        new_messages=[m2],
    )
    ai_output2 = MemoryAIOutput(
        summary="Switched back to Postgres.",
        decisions=["Use Postgres database"],
        obsolete_items=["CockroachDB"],
        confidence=0.98,
    )

    result2 = process_memory_delta(delta2, memory_ai_output=ai_output2)
    assert result2 is not None
    assert result2.obsolete_marked >= 1
    assert result2.context_version == 2

    with session_scope() as session:
        obsolete = list_memory_items(session, conv_id, status=MemoryStatus.OBSOLETE.value)
        assert len(obsolete) >= 1
        active2 = list_memory_items(session, conv_id, status=MemoryStatus.ACTIVE.value)
        active_contents = [i.content for i in active2]
        assert "Use Postgres database" in active_contents


@pytest.mark.asyncio
async def test_low_info_skips_memory_ai(tmp_db):
    """Verify that low-information turns skip calling Memory AI."""
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"choices": []})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://mock.memory.ai/v1")
    adapter = MemoryAIAdapter(
        base_url="https://mock.memory.ai/v1",
        api_key="secret",
        model="cheap-model",
        client=client,
    )

    m = NormalizedMessage(
        role="user",
        content="ok, thanks!",
        message_key="k1",
        content_hash="h1",
        client_message_id=None,
        ordinal=0,
        raw={"role": "user", "content": "ok, thanks!"},
    )
    delta = DeltaResult(
        conversation_id="c-low",
        user_key=None,
        all_messages=[m],
        new_messages=[m],
    )

    result = await process_memory_delta_async(delta, memory_ai=adapter)
    assert result is not None
    assert result.skipped_low_info is True
    assert called is False  # Memory AI was correctly not called


def test_memory_ai_never_used_as_main_answer_generator(tmp_db):
    """
    CRITICAL INVARIANT TEST:
    Verify that Memory AI is NEVER called to generate the client's answer.
    The response to /v1/chat/completions must come strictly from upstream_provider.
    """
    app = create_app()
    main_provider = StubMainProvider(answer="Answer directly from MAIN upstream model!")
    app.state.upstream_provider = main_provider

    # Configure a Memory AI adapter that would produce something totally different
    def memory_ai_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": '{"summary": "memory only"}'}}]},
        )

    mem_transport = httpx.MockTransport(memory_ai_handler)
    mem_client = httpx.AsyncClient(transport=mem_transport, base_url="https://mock.memory.ai/v1")
    app.state.memory_ai_adapter = MemoryAIAdapter(
        base_url="https://mock.memory.ai/v1",
        api_key="secret",
        model="cheap-model",
        client=mem_client,
    )

    client = TestClient(app)
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "What is 2+2?"}]},
    )

    assert resp.status_code == 200
    data = resp.json()
    # Main provider answered the user
    assert data["choices"][0]["message"]["content"] == "Answer directly from MAIN upstream model!"
    assert len(main_provider.chat_calls) == 1

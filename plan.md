# Implementation Plan — AI Memory Gateway

## Product Summary

Build a production-oriented **AI Memory Gateway / Context Compression Proxy** in Python. It sits transparently between OpenAI-compatible clients (OpenCode, Codex, etc.) and the real upstream AI API. The gateway optimizes what is sent **to** the main model and must never alter what comes **back**.

## Guiding Principles

1. **Transparent proxy** — client only changes `base_url`; no MCP, custom tools, or SDK changes.
2. **Main AI is mandatory** — gateway never replaces the reasoning model.
3. **Not conventional RAG** — primary loop is `Context[n] + delta → Memory Update → Context[n+1]` with a fixed-size active context.
4. **Raw archive is authoritative** — compact memory is derived and repairable.
5. **Failure isolation** — memory failures must not break main AI forwarding.
6. **Response transparency** — upstream response (including streams) is returned unchanged.

## Phased Delivery

### Phase 0 — Project skeleton (Day 1)

- Create `memory-gateway/` layout (FastAPI, packages, tests, Docker).
- Config via env (`.env.example`): upstream provider, memory AI, budget, auth, SQLite path.
- Health endpoint and basic app bootstrap.
- `docker compose up` runs with SQLite only (no Redis/vector DB required).

**Exit criteria:** empty FastAPI app starts; env loads; Docker builds.

### Phase 1 — Transparent OpenAI-compatible proxy (Days 1–3)

- Implement:
  - `POST /v1/chat/completions`
  - `POST /v1/responses`
  - `GET /v1/models`
- Provider abstraction (`AIProvider`: `chat`, `responses`, `stream`).
- First adapter: OpenAI-compatible (configurable `UPSTREAM_BASE_URL`).
- Pass-through auth headers / upstream API key from config.
- Streaming SSE proxy without full buffering.
- Request size limits and safe error mapping.
- Tests: forward correctness, header handling, streaming identity, upstream error passthrough.

**Exit criteria:** point OpenCode/Codex at gateway; responses match direct upstream (no memory yet).

### Phase 2 — Persistence & delta detection (Days 3–5)

- SQLite schema: conversations, raw messages, canonical memory, context versions, cache metadata.
- Raw archive for user/assistant/tool/system messages + metadata.
- Stable message IDs; fallback deterministic hashes (content + role + order).
- Delta detection: duplicates, retries, reorders, missing messages.
- Conversation / user isolation keys.
- Tests for delta edge cases.

**Exit criteria:** every request archives raw messages; only new deltas are flagged for processing.

### Phase 3 — Memory engine (MVP, deterministic-first) (Days 5–8)

- Three layers: Raw Archive, Canonical Memory, Recent Context.
- Memory item model: content, type, confidence, importance, stability, freshness, information_gain, status, version, source IDs.
- Pipeline: deterministic rules → candidate extraction → duplicate detection → contradiction handling → optional cheap AI → versioned state.
- Skip Memory AI for low-information messages (`ok`, `thanks`, `yes`, …).
- Contradiction: supersede old items; never silently overwrite confirmed user decisions with speculation.
- Information-gain gating before writes.
- Failure path: keep previous canonical memory on parse/AI failure.
- Tests: facts, merge, supersede, confidence preservation, low-info skip.

**Exit criteria:** memory updates from deltas without requiring Memory AI for trivial turns.

### Phase 4 — Optional Memory AI compressor (Days 8–10)

- Memory AI adapter (same provider interface pattern; separate config).
- Structured JSON output + schema validation (Pydantic).
- Retry-once on parse failure; otherwise leave memory unchanged.
- Tool-output compression into compact summaries; originals stay in raw archive.
- Pluggable providers: OpenRouter, OpenAI, Gemini, Anthropic, local OpenAI-compatible.
- Tests with mocked Memory AI; malformed JSON isolation.

**Exit criteria:** `MEMORY_AI_ENABLED=true` improves compression; disabled path still works.

### Phase 5 — Context compiler (Days 10–12)

- Assemble: system instructions + canonical memory + recent context + important tool results + new user message.
- Token budget (`CONTEXT_BUDGET`); selection as value/token_cost (relevance, confidence, importance, freshness, stability, information_gain).
- No naive head/tail truncation.
- Versioned context snapshots (`conversation_id`, version, state, timestamps, source IDs).
- Tests: budget compliance, priority of high-value items, recent-task preservation.

**Exit criteria:** compiled context ≤ budget; main model still receives coherent prompts.

### Phase 6 — Retrieval & cache (Days 12–14)

- SQLite FTS5 over raw history and memory.
- `Retriever` interface ready for future pgvector/Qdrant/etc.; embeddings optional and off critical path.
- Version-aware caches: request, extraction, compilation, retrieval (SQLite first; Redis optional).
- Cache keys include conversation + context version + request hash; never serve stale over newer version.
- Background hooks for embeddings, deep consolidation, repair (async, non-blocking).

**Exit criteria:** FTS search works; caches are version-safe; MVP runs without Redis.

### Phase 7 — Hardening, security, docs (Days 14–16)

- API auth hooks, rate-limit hooks, secret redaction, no key logging, retention config.
- Latency path: delta → load memory → deterministic → optional Memory AI → compile → upstream → unchanged response.
- Full test suite green; streaming + non-streaming response identity tests.
- README: install, env, OpenCode/Codex/OpenAI client setup, providers, budget, streaming, troubleshooting, security.
- Docker Compose polish for one-command MVP.

**Exit criteria:** production-oriented MVP checklist from PROMT § Final Implementation Requirement is met.

### Phase 8 — Memory Correctness (Post-MVP, FIX.md)

**Context:** The comprehensive benchmark (2026-09-11) shows the gateway is sound in isolation, streaming, token reduction (~92%), and fail-open behavior — but memory correctness is only 70% with correction accuracy failing and false/noisy memories present.

**Goal:** Fix the deterministic memory engine so it correctly handles natural-language facts, corrections, revocations, interrogative noise, stale memory, and contradictions. Do **not** redesign the proxy, storage, streaming, or fail-open architecture. Keep Memory-AI compressor disabled for this phase.

**Targets:**
- Memory correctness ≥ 95%
- Correction accuracy ≥ 95%
- False-memory rate ≈ 0%
- Interrogative noise = 0%
- Cross-conversation leakage = 0%

**Tasks (see `todo.md` §Phase 8):**
1. Fix interrogative noise — classify questions before they can become memories.
2. Expand deterministic extraction — `I am building X`, `X uses Y`, `X's Z is …`, `The Y is X`.
3. Correction semantics — detect and store `{type, target, old_value, new_value}` records; supersede old facts.
4. Revocation / reset semantics — `ACTIVE | SUPERSEDED | REVOKED | EXPIRED` state model.
5. Conflict resolution — compiled context selects latest valid correction > latest ACTIVE fact.
6. False-memory protection — block acknowledgements, filler, model answers, unsupported assumptions.
7. Context compiler update — only ACTIVE / latest-correction entries in compiled context.
8. Comprehensive regression tests (varied wording; no benchmark-phrase hardcoding).
9. Re-run existing benchmark without methodology changes; compare Before/After.
10. Regression gate — all 78+ existing tests must remain passing.
11. Final report — update `benchmarks/COMPREHENSIVE_RESULTS.md`.

**Engineering constraints:**
- Preserve existing architecture.
- Prefer small, composable changes.
- Do not rewrite memory system unnecessarily.
- Do not sacrifice isolation or fail-open behavior.
- Do not treat LLM-generated answers as user facts.
- Historical memories may stay in archive; SUPERSEDED/REVOKED must not appear in active context.
- Run full test suite before finishing.

**Exit criteria:** memory correctness ≥ 95%, correction accuracy ≥ 95%, false-memory rate ≈ 0%, interrogative noise = 0%, 78+ existing tests pass, `COMPREHENSIVE_RESULTS.md` updated.

## Non-Goals (MVP)

- Requiring vector DB / Redis / embeddings.
- Replacing the main model with the memory model.
- Conventional RAG as the primary architecture.
- Rewriting or enriching client-visible assistant responses.
- Native Anthropic/Gemini request formats (OpenAI-compatible first; native adapters later).

## Risk Register

| Risk | Mitigation |
|------|------------|
| Memory AI latency on hot path | Deterministic-first; skip low info; async post-stream extraction |
| Corrupt memory from bad JSON | Schema validation; retry once; keep prior state |
| Context quality regressions | Versioned state; repair from raw archive; budget-aware scoring |
| Client incompatibilities | Strict OpenAI-compatible shapes; response byte/stream identity tests |
| Storage growth | Retention config; tool output archive + compact summaries |

## Success Metrics (MVP)

- Client base URL swap works without code changes.
- Upstream response identity (non-stream + stream).
- Active context stays within configured token budget.
- Memory failures fall back without failing the main request.
- `docker compose up` alone is enough to run.

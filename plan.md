# Implementation Plan — AI Memory Gateway

## Product Summary

Build a production-oriented **AI Memory Gateway / Context Compression Proxy** in **TypeScript** on **Cloudflare Workers** (Hono + Turso + Upstash Redis). It sits transparently between OpenAI-compatible clients (OpenCode, Codex, etc.) and the real upstream AI API. The gateway optimizes what is sent **to** the main model and must never alter what comes **back**.

## Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Cloudflare Workers |
| Framework | Hono |
| Database | Turso (libSQL / SQLite-compatible) |
| Cache | Upstash Redis (optional) |
| ORM | Drizzle ORM |
| Language | TypeScript |
| Package manager | Bun |
| Tests | Bun test |

## Guiding Principles

1. **Transparent proxy** — client only changes `base_url`; no MCP, custom tools, or SDK changes.
2. **Main AI is mandatory** — gateway never replaces the reasoning model.
3. **Not conventional RAG** — primary loop is `Context[n] + delta → Memory Update → Context[n+1]` with a fixed-size active context.
4. **Raw archive is authoritative** — compact memory is derived and repairable.
5. **Failure isolation** — memory failures must not break main AI forwarding.
6. **Response transparency** — upstream response (including streams) is returned unchanged.

## Phased Delivery

### Phase 0 — Project skeleton ✅

- Hono app entry (`src/index.ts`) + env bindings via `wrangler.jsonc`.
- Config via `.dev.vars`: upstream provider, memory AI, budget, auth, Turso URL/token.
- Health endpoint and basic app bootstrap.
- `wrangler dev` runs locally with Turso over HTTP (no Redis required).

**Exit criteria:** Hono app starts; env loads; `bun run dev` works.

### Phase 1 — Transparent OpenAI-compatible proxy ✅

- Implement:
  - `POST /v1/chat/completions`
  - `POST /v1/responses`
  - `GET /v1/models`
- Provider abstraction (`OpenAICompatibleProvider`: `chat`, `responses`, `openStream`).
- First adapter: OpenAI-compatible (configurable `UPSTREAM_BASE_URL`).
- Pass-through auth headers / upstream API key from config.
- Streaming SSE proxy without full buffering.
- Request size limits and safe error mapping.

**Exit criteria:** point OpenCode/Codex at gateway; responses match direct upstream (no memory yet).

### Phase 2 — Persistence & delta detection ✅

- Drizzle ORM + D1 schema: conversations, raw messages, canonical memory, context versions, cache metadata.
- Raw archive for user/assistant/tool/system messages + metadata.
- Stable message IDs; fallback deterministic hashes (content + role + order).
- Delta detection: duplicates, retries, reorders, missing messages.
- Conversation / user isolation keys (from `X-Conversation-Id` header or deterministic fingerprint).

**Exit criteria:** every request archives raw messages; only new deltas are flagged for processing.

### Phase 3 — Memory engine (MVP, deterministic-first) ✅

- Three layers: Raw Archive, Canonical Memory, Recent Context.
- Memory item model: content, type, confidence, importance, stability, freshness, information_gain, status, version, source IDs.
- Pipeline: deterministic rules → candidate extraction → duplicate detection → contradiction handling → optional cheap AI → versioned state.
- Skip Memory AI for low-information messages (`ok`, `thanks`, `yes`, …).
- Contradiction: supersede old items; never silently overwrite confirmed user decisions with speculation.
- Information-gain gating before writes.

**Exit criteria:** memory updates from deltas without requiring Memory AI for trivial turns.

### Phase 4 — Optional Memory AI compressor ✅

- Memory AI adapter (same provider interface pattern; separate config).
- Structured JSON output + Zod schema validation.
- Retry-once on parse failure; otherwise leave memory unchanged.
- Tool-output compression into compact summaries; originals stay in raw archive.

**Exit criteria:** `MEMORY_AI_ENABLED=true` improves compression; disabled path still works.

### Phase 5 — Context compiler ✅

- Assemble: system instructions + canonical memory + recent context + important tool results + new user message.
- Token budget (`CONTEXT_BUDGET`); selection as value/token_cost (relevance, confidence, importance, freshness, stability, information_gain).
- No naive head/tail truncation.
- Versioned context snapshots (`conversation_id`, version, state, timestamps, source IDs).

**Exit criteria:** compiled context ≤ budget; main model still receives coherent prompts.

### Phase 6 — Retrieval & cache ✅

- D1 FTS (SQLite-compatible) over raw history and memory.
- `Retriever` interface ready for future backends.
- Version-aware caches: request, extraction, compilation, retrieval (Upstash Redis optional).
- Cache keys include conversation + context version + request hash; never serve stale over newer version.

**Exit criteria:** FTS search works; caches are version-safe; MVP runs without Redis.

### Phase 7 — Hardening, security, docs ✅

- API auth hooks, rate-limit hooks (Upstash Ratelimit), secret redaction, no key logging, retention config.
- Full test suite green; streaming + non-streaming response identity tests.
- README: install, env, OpenCode/Codex/OpenAI client setup, providers, budget, streaming, troubleshooting, security.
- `wrangler deploy` one-command production deploy.

**Exit criteria:** production-oriented MVP checklist from PROMT § Final Implementation Requirement is met.

### Phase 8 — Memory Correctness (Post-MVP, FIX.md) ✅

**Goal:** Fix the deterministic memory engine so it correctly handles natural-language facts, corrections, revocations, interrogative noise, stale memory, and contradictions.

**Targets:**
- Memory correctness ≥ 95%
- Correction accuracy ≥ 95%
- False-memory rate ≈ 0%
- Interrogative noise = 0%
- Cross-conversation leakage = 0%

**Tasks:**
1. Fix interrogative noise — classify questions before they can become memories.
2. Expand deterministic extraction — `I am building X`, `X uses Y`, `X's Z is …`, `The Y is X`.
3. Correction semantics — detect and store `{type, target, old_value, new_value}` records; supersede old facts.
4. Revocation / reset semantics — `ACTIVE | SUPERSEDED | REVOKED | EXPIRED` state model.
5. Conflict resolution — compiled context selects latest valid correction > latest ACTIVE fact.
6. False-memory protection — block acknowledgements, filler, model answers, unsupported assumptions.
7. Context compiler update — only ACTIVE / latest-correction entries in compiled context.
8. Comprehensive regression tests (varied wording; no benchmark-phrase hardcoding).

**Exit criteria:** memory correctness ≥ 95%, correction accuracy ≥ 95%, false-memory rate ≈ 0%, interrogative noise = 0%, all existing tests pass.

### Phase 9 — TypeScript Test Suite Parity (Current)

**Goal:** Validate the TypeScript implementation with a comprehensive test suite equivalent to the Python version's 158 tests. The codebase has all modules written but none are battle-tested.

**Tasks:**
- [ ] Proxy identity tests (stream + non-stream) with mocked upstream
- [ ] Delta detection unit tests (new, duplicate, retry, reorder)
- [ ] Memory engine unit tests (extract, merge, supersede, low-info skip)
- [ ] Correction / revocation integration tests
- [ ] Context compiler unit tests (budget, scoring, ACTIVE-only output)
- [ ] Interrogative noise tests
- [ ] Conversation isolation tests
- [ ] Fail-open behavior tests (D1 error, Memory AI error)
- [ ] Auth + rate limit tests
- [ ] End-to-end smoke against `wrangler dev`

**Exit criteria:** all tests pass with `bun test`; coverage matches Python version's 158 tests.

## Non-Goals

- Docker / server deployment (Cloudflare Workers only).
- Python runtime.
- Requiring vector DB / Redis / embeddings.
- Replacing the main model with the memory model.
- Conventional RAG as the primary architecture.
- Rewriting or enriching client-visible assistant responses.

## Risk Register

| Risk | Mitigation |
|------|------------|
| D1 FTS5 support gaps | Test FTS in Workers Vitest; fallback to LIKE query |
| Memory AI latency on hot path | Deterministic-first; skip low info; async post-stream via `waitUntil` |
| Corrupt memory from bad JSON | Zod validation; retry once; keep prior state |
| Context quality regressions | Versioned state; repair from raw archive; budget-aware scoring |
| Client incompatibilities | Strict OpenAI-compatible shapes; response byte/stream identity tests |

## Success Metrics

- Client base URL swap works without code changes.
- Upstream response identity (non-stream + stream).
- Active context stays within configured token budget.
- Memory failures fall back without failing the main request.
- `wrangler dev` alone is enough to run locally.
- `wrangler deploy` alone is enough to go to production.

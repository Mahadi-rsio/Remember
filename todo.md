# TODO — AI Memory Gateway

Track work against `plan.md`. Check items as they land.

## Phase 0 — Skeleton ✅

- [x] Create `src/` package layout (`routes`, `providers`, `memory`, `context`, `storage`, `retrieval`, `cache`, `models`, `db`)
- [x] Hono app entry (`src/index.ts`) + env bindings via `wrangler.jsonc`
- [x] `.dev.vars.example`, `package.json`, `wrangler.jsonc`
- [x] Health check route
- [x] Verify `wrangler dev` starts with D1 only

## Phase 1 — Transparent Proxy ✅

- [x] `POST /v1/chat/completions` passthrough
- [x] `POST /v1/responses` passthrough
- [x] `GET /v1/models` passthrough
- [x] `OpenAICompatibleProvider` (`chat`, `responses`, `openStream`)
- [x] Non-streaming forward + error mapping
- [x] Streaming SSE proxy (no full buffer)
- [x] Request size limits
- [x] Auth middleware (`checkAuth`)
- [x] Rate limit middleware (`checkRateLimit` via Upstash)

## Phase 2 — Persistence & Delta ✅

- [x] Drizzle ORM models: conversations, messages, memory items, context versions
- [x] Raw archive writer (`storage/archive.ts`)
- [x] Message ID extraction + deterministic hash fallback (`memory/ids.ts`)
- [x] Delta detection (`memory/delta.ts`)
- [x] Conversation / user isolation keys (`memory/isolation.ts`)

## Phase 3 — Memory Engine (Deterministic) ✅

- [x] Canonical memory schema (facts, decisions, constraints, preferences, goals, architecture, important_events, active_tasks)
- [x] Per-item scores: confidence, importance, stability, freshness, information_gain
- [x] Deterministic low-info message skip (`memory/low-info.ts`)
- [x] Duplicate / merge detection
- [x] Contradiction handling with supersede (`memory/contradiction.ts`)
- [x] Explicit user decision authority vs speculation
- [x] Information-gain gate before writes
- [x] Versioned context state on each update (`memory/state.ts`)
- [x] Memory engine pipeline (`memory/engine.ts`)

## Phase 4 — Memory AI (Optional) ✅

- [x] Memory AI config (`MEMORY_AI_ENABLED`, provider, model, key)
- [x] Memory AI adapter (`providers/memory-ai.ts`)
- [x] Structured JSON prompt + Zod validation
- [x] Retry-once on parse failure; keep prior memory otherwise
- [x] Tool-output compression → compact summary; raw preserved
- [x] Ensure Memory AI never used as main answer generator

## Phase 5 — Context Compiler ✅

- [x] Assembler: system + canonical + recent + tool results + new message (`context/assembler.ts`)
- [x] Token budget enforcement (`CONTEXT_BUDGET`) (`context/tokens.ts`)
- [x] Selector scoring (`value / token_cost`) (`context/selector.ts`)
- [x] No naive head/tail truncation
- [x] Persist compiled context version snapshots (`context/compiler.ts`)

## Phase 6 — Retrieval & Cache ✅

- [x] D1 FTS indexes for raw history + memory (`retrieval/`)
- [x] `Retriever` interface + D1 FTS backend
- [x] Version-aware caches (`cache/`)
- [x] Cache key includes conversation + context version + request hash
- [x] Optional Upstash Redis adapter

## Phase 7 — Hardening & Docs ✅

- [x] API authentication hooks (`routes/auth.ts`)
- [x] Rate limiting hooks (`routes/rate-limit.ts`)
- [x] Secret redaction; never log API keys
- [x] Safe client error responses (502 upstream, 400 bad JSON)
- [x] Failure isolation: Memory AI / D1 / retrieval failures → still call main AI
- [x] README: install, env, client setup, providers, budget, streaming, troubleshooting, security
- [x] `wrangler deploy` one-command deploy

## Phase 8 — Memory Correctness ✅

> **Baseline (2026-09-11):** Memory correctness 70% | Correction accuracy FAIL | False-memory rate present | Interrogative noise present
> **Targets:** Memory correctness ≥95% | Correction accuracy ≥95% | False-memory rate ~0% | Interrogative noise 0% | Cross-conversation leakage 0%
> Memory-AI compressor remains disabled for this phase.

### 8.1 Fix Interrogative Noise
- [x] Robust interrogative classifier (`memory/interrogative.ts`)
- [x] Tests: questions never become factual memories
- [x] Guard: declarative statements containing question-like words must still be stored

### 8.2 Expand Deterministic Fact Extraction
- [x] Patterns: `I am building X.` / `X uses Y.` / `X's Z is …` / `I prefer X over Y.` / `The Y is X.`
- [x] Normalize into structured memory (entity, attribute, value) (`memory/facts.ts`)
- [x] Tests: all new natural-language forms covered

### 8.3 Implement Correction Semantics
- [x] Detect correction phrases (`memory/correction.ts`)
- [x] Store structured correction record: `{type, target, old_value, new_value, timestamp, status}`
- [x] Supersede old fact when correction stored
- [x] Context compiler surfaces `new_value` only; hides SUPERSEDED entries
- [x] Tests: correction path validated

### 8.4 Implement Revocation / Reset Semantics
- [x] Detect revocation phrases (`memory/revocation.ts`)
- [x] Memory state model: `ACTIVE | SUPERSEDED | REVOKED | EXPIRED`
- [x] Revoked items kept in archive but excluded from compiled context
- [x] Tests: revoked items absent from compiled context

### 8.5 Improve Conflict Resolution
- [x] Conflict selection order: latest valid correction > latest ACTIVE fact > older SUPERSEDED fact
- [x] Do not inject both conflicting values into compiled context
- [x] Use existing timestamp/version/source metadata (`memory/contradiction.ts`)

### 8.6 Protect Against False Memories
- [x] Low-info filter covers pure acknowledgements and conversational filler
- [x] Do not store: model-generated answers as user facts, unsupported assumptions

### 8.7 Update Context Compilation
- [x] Compiled context contains only ACTIVE / latest-correction memories
- [x] After correction: only new value appears; old value absent
- [x] After revocation: no entry in compiled context

### 8.8 Comprehensive Regression Tests
- [x] Basic facts, corrections, revocations, questions, contradictions, stale info, isolation

---

## Phase 9 — TypeScript Test Suite Parity (Current)

> **Goal:** Validate the TypeScript implementation with a test suite equivalent to the Python version's 158 tests. All modules are written but untested systematically.

### 9.1 Proxy Tests
- [ ] Non-streaming forward identity (request/response body unchanged)
- [ ] Streaming SSE proxy identity (chunks pass through unmodified)
- [ ] Upstream error codes mapped correctly (4xx, 5xx → 502)
- [ ] Bad JSON → 400 response
- [ ] Auth rejection when `GATEWAY_API_KEY` set

### 9.2 Delta Detection Tests
- [ ] New messages flagged as delta
- [ ] Duplicate message IDs ignored
- [ ] Retry (same content, new ID) detected correctly
- [ ] Out-of-order messages handled

### 9.3 Memory Engine Unit Tests
- [x] Fact extraction: `I am building X.`, `X uses Y.`, `I prefer X.`
- [x] Multi-fact extraction: one message → multiple atomic facts (sentence split + multi-clause `uses` list)
- [x] Stack update: "switched X to Y" supersedes the old value (e.g. Turso → Neon)
- [ ] Low-info skip: `ok`, `thanks`, `yes`, `continue`, `sure`
- [ ] Interrogative skip: `What is my name?`, `Where is the server?`
- [ ] Merge: same fact → update, not duplicate
- [ ] Supersede: contradiction detected → old fact SUPERSEDED
- [ ] Confidence preserved across updates

### 9.4 Correction & Revocation Tests
- [ ] Correction phrase detected and stored
- [ ] Old fact set to SUPERSEDED; new value ACTIVE
- [ ] Revocation phrase detected; item set to REVOKED
- [ ] Revoked item absent from compiled context

### 9.5 Context Compiler Tests
- [ ] Output stays within `CONTEXT_BUDGET`
- [ ] High-importance items prioritized over low-importance
- [ ] SUPERSEDED items excluded
- [ ] REVOKED items excluded
- [ ] Recent context preserved over old stale items

### 9.6 Isolation Tests
- [ ] Memories from conversation A never appear in conversation B
- [ ] `X-Conversation-Id` header correctly scopes state
- [ ] Deterministic fingerprint fallback consistent across calls

### 9.7 Fail-Open Tests
- [ ] DB error → main AI still called; error logged but not surfaced
- [ ] Memory AI error → fallback to deterministic; main AI still called
- [ ] Retrieval error → still call main AI

### 9.8 End-to-End Smoke
- [ ] `bun run dev` + real upstream: chat works
- [ ] Memory persisted across turns (same `X-Conversation-Id`)
- [ ] `GET /health` returns 200
- [ ] `GET /v1/models` proxies upstream models list

---

## Explicit Non-Goals

- [ ] ~~Docker / server deployment~~ (Cloudflare Workers only)
- [ ] ~~Python runtime~~
- [ ] ~~Require Redis / vector DB / embeddings~~ (optional only)
- [ ] ~~Build conventional RAG as primary architecture~~
- [ ] ~~Rewrite or post-process main model responses~~
- [ ] ~~Replace main model with Memory AI~~
- [ ] ~~Require MCP / custom client SDKs~~

## Definition of Done

- [ ] Client only changes base URL to use the gateway
- [ ] Main upstream always generates the answer
- [ ] Fixed-budget context from persistent state + delta
- [ ] Raw archive recoverable; compact memory repairable
- [ ] Streaming and non-streaming responses unchanged
- [ ] Tests pass with `bun test`
- [ ] `wrangler deploy` ships to production

# TODO — AI Memory Gateway MVP

Track work against `PROMT.md`. Check items as they land.

## Phase 0 — Skeleton

- [x] Create `memory-gateway/` package layout (`app/api`, `providers`, `memory`, `context`, `storage`, `retrieval`, `cache`, `models`)
- [x] FastAPI app entry (`main.py`) + settings via Pydantic/env
- [x] `.env.example`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`
- [x] Health check route
- [x] Verify `docker compose up` with SQLite only

## Phase 1 — Transparent Proxy

- [x] `POST /v1/chat/completions` passthrough
- [x] `POST /v1/responses` passthrough
- [x] `GET /v1/models` passthrough
- [x] `AIProvider` interface (`chat`, `responses`, `stream`)
- [x] OpenAI-compatible upstream adapter (`UPSTREAM_BASE_URL`, API key)
- [x] Non-streaming forward + error mapping
- [x] Streaming SSE proxy (no full buffer)
- [x] Request size limits
- [x] Tests: forward correctness, streaming identity, upstream errors

## Phase 2 — Persistence & Delta

- [x] SQLModel/SQLAlchemy models: conversations, messages, memory items, context versions
- [x] Raw archive writer (user / assistant / tool / system + metadata)
- [x] Message ID extraction + deterministic hash fallback
- [x] Delta detection (duplicates, retries, reorder, missing)
- [x] Conversation / user isolation keys
- [x] Tests: new delta, duplicate ignore, retry handling

## Phase 3 — Memory Engine (Deterministic)

- [x] Canonical memory schema (facts, decisions, constraints, preferences, goals, architecture, important_events, active_tasks)
- [x] Per-item scores: confidence, importance, stability, freshness, information_gain
- [x] Deterministic low-info message skip (`ok`, `thanks`, `yes`, `continue`, …)
- [x] Duplicate / merge detection
- [x] Contradiction handling with supersede (status transitions)
- [x] Explicit user decision authority vs speculation
- [x] Information-gain gate before writes
- [x] Versioned context state on each update
- [x] Tests: extract, merge, supersede, confidence preserve, low-info skip

## Phase 4 — Memory AI (Optional)

- [x] Memory AI config (`MEMORY_AI_ENABLED`, provider, model, key)
- [x] Memory AI adapter (OpenRouter / OpenAI / compatible)
- [x] Structured JSON prompt + Pydantic validation
- [x] Retry-once on parse failure; keep prior memory otherwise
- [x] Tool-output compression → compact summary; raw preserved
- [x] Ensure Memory AI never used as main answer generator
- [x] Tests: mocked AI success/failure; malformed JSON isolation

## Phase 5 — Context Compiler

- [x] Assembler: system + canonical + recent + tool results + new message
- [x] Token budget enforcement (`CONTEXT_BUDGET`)
- [x] Selector scoring (`value / token_cost`)
- [x] No naive head/tail truncation
- [x] Persist compiled context version snapshots
- [x] Tests: within budget, high-value priority, recent context kept

## Phase 6 — Retrieval & Cache

- [x] SQLite FTS5 indexes for raw history + memory
- [x] `Retriever` interface + FTS backend
- [x] Stub/optional embedding path (off hot path)
- [x] Version-aware caches (request, extraction, compilation, retrieval)
- [x] Cache key includes conversation + context version + request hash
- [x] Optional Redis adapter (not required for MVP)
- [x] Background job hooks: embeddings, consolidation, repair

## Phase 7 — Hardening & Docs

- [x] API authentication hooks
- [x] Rate limiting hooks
- [x] Secret redaction; never log API keys; never store upstream keys in raw logs
- [x] Trace logging: log compiled context sent to AI + response received (stream + non-stream), optional file sink
- [x] Tiny chat CLI (`cli.py`) for live gateway testing (streaming, sessions, memory recall)
- [x] Retention / cleanup config
- [x] Safe client error responses
- [x] Failure isolation: Memory AI / SQLite / retrieval failures → still call main AI
- [x] Response transparency tests: upstream == gateway (stream + non-stream)
- [x] README: install, env, OpenCode, Codex, OpenAI clients, providers, budget, streaming, troubleshooting, security
- [x] Live benchmark (`benchmarks/bench.py`): proxy overhead, TTFT, memory-write cost, compaction
- [x] End-to-end smoke with `docker compose up`

## Phase 8 — Memory Correctness (FIX.md)

> **Baseline (2026-09-11):** Memory correctness 70% | Correction accuracy FAIL | False-memory rate present | Interrogative noise present
> **Targets:** Memory correctness ≥95% | Correction accuracy ≥95% | False-memory rate ~0% | Interrogative noise 0% | Cross-conversation leakage 0%
> Do NOT redesign proxy/streaming/storage/fail-open. Keep Memory-AI compressor disabled for this phase.

### 8.1 Fix Interrogative Noise
- [x] Add robust interrogative classifier (questions must never become factual memories)
- [x] Tests: `What is my name?`, `Why did we choose PostgreSQL?`, `When is the launch?`, `Where is the project deployed?`, `How does Cloudisy work?` → no memory extracted
- [x] Guard: declarative statements containing question-like words must still be stored

### 8.2 Expand Deterministic Fact Extraction
- [x] Pattern: `I am building X.` / `X uses Y.` / `X's Z is …` / `I prefer X over Y.` / `The Y is X.`
- [x] Normalize into structured memory (entity, attribute, value)
- [x] Keep extraction modular and testable; avoid brittle mega-regex
- [x] Tests: cover all new natural-language forms above

### 8.3 Implement Correction Semantics
- [ ] Detect correction phrases: `X changed from A to B`, `X now uses Y instead of Z`, `We no longer use X`, `The Y was changed to X`, `Actually, …`, `I changed my preference from X to Y`
- [ ] Store structured correction record: `{type, target, old_value, new_value, timestamp, status}`
- [ ] Supersede old fact when correction is stored (status → SUPERSEDED)
- [ ] Context compiler must surface `new_value` only; hide SUPERSEDED entries
- [ ] Tests: Cloudisy Neon → self-hosted PostgreSQL correction path

### 8.4 Implement Revocation / Reset Semantics
- [ ] Detect revocation phrases: `was reset`, `ignore the previous`, `no longer valid`, `has been revoked`, `forget the previous value`
- [ ] Memory state model: `ACTIVE | SUPERSEDED | REVOKED | EXPIRED`
- [ ] Revoked items: kept in archive but excluded from compiled context
- [ ] Tests: `temp1234 → REVOKED` after reset; a subsequent query must NOT return `temp1234`

### 8.5 Improve Conflict Resolution
- [ ] Conflict selection order: latest valid correction > latest ACTIVE fact > older SUPERSEDED fact
- [ ] Do not inject both conflicting values into compiled context (unless historical view requested)
- [ ] Use existing timestamp/version/source metadata
- [ ] Tests: two competing facts for same entity → only latest ACTIVE wins

### 8.6 Protect Against False Memories
- [ ] Ensure existing low-info filter covers: `ok`, `thanks`, `yes`, `no`, `continue`, `sure`, `What?`, `Why?`, `How?`
- [ ] Do not store: pure acknowledgements, conversational filler, model-generated answers as user facts, unsupported assumptions
- [ ] Tests: all items above → no memory extraction

### 8.7 Update Context Compilation
- [ ] Compiled context must contain only ACTIVE / latest-correction memories
- [ ] After correction: only new value appears; old value absent as active fact
- [ ] After revocation: no entry for the revoked item in compiled context
- [ ] Do not increase `CONTEXT_BUDGET` to hide correctness problems
- [ ] Tests: correction → compiled context has new value only; revocation → no entry

### 8.8 Add Comprehensive Regression Tests
- [ ] Basic facts: `I am building Cloudisy.`, `Cloudisy uses PostgreSQL.`, `I prefer TypeScript.`
- [ ] Corrections: `Cloudisy uses Neon.` → `Actually, Cloudisy uses self-hosted PostgreSQL.`
- [ ] Revocation: `The temporary password is temp1234.` → `The password was reset.`
- [ ] Questions: `What is my name?`, `What database do we use?` → no memory stored
- [ ] Contradictions: `I prefer React.` → `Actually, I prefer Vue.`
- [ ] Stale information: old fact + later update → only current value compiled
- [ ] Unrelated memories: not injected into unrelated context
- [ ] Isolation: memories from conversation A never appear in conversation B
- [ ] Use varied natural-language wording; do not hardcode benchmark phrases

### 8.9 Re-run Existing Comprehensive Benchmark
- [ ] Run benchmark without changing its methodology
- [ ] Compare Before/After for: recall accuracy, correction accuracy, false memory rate, interrogative noise, token usage, p50/p95 latency, memory-write overhead, isolation, streaming, fail-open
- [ ] Do NOT modify benchmark to inflate scores

### 8.10 Regression Gate
- [ ] All 78+ existing tests pass
- [ ] OpenAI SDK compatibility: `/v1/models`, `/v1/chat/completions` (stream + non-stream)
- [ ] Malformed/oversized request handling
- [ ] Fail-open behavior
- [ ] Conversation isolation
- [ ] Memory-AI compressor remains disabled (deterministic engine independently correct)

### 8.11 Final Report
- [ ] Update `benchmarks/COMPREHENSIVE_RESULTS.md` with new results
- [ ] Clearly report Before (70%) vs After (X%) for all metrics
- [ ] List any remaining failures honestly

---

## Explicit Non-Goals (Do Not Do in MVP)

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
- [ ] Tests + Docker + README complete

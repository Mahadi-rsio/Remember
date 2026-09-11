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

- [ ] API authentication hooks
- [ ] Rate limiting hooks
- [ ] Secret redaction; never log API keys; never store upstream keys in raw logs
- [ ] Retention / cleanup config
- [ ] Safe client error responses
- [ ] Failure isolation: Memory AI / SQLite / retrieval failures → still call main AI
- [ ] Response transparency tests: upstream == gateway (stream + non-stream)
- [ ] README: install, env, OpenCode, Codex, OpenAI clients, providers, budget, streaming, troubleshooting, security
- [ ] End-to-end smoke with `docker compose up`

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

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

- [ ] SQLModel/SQLAlchemy models: conversations, messages, memory items, context versions
- [ ] Raw archive writer (user / assistant / tool / system + metadata)
- [ ] Message ID extraction + deterministic hash fallback
- [ ] Delta detection (duplicates, retries, reorder, missing)
- [ ] Conversation / user isolation keys
- [ ] Tests: new delta, duplicate ignore, retry handling

## Phase 3 — Memory Engine (Deterministic)

- [ ] Canonical memory schema (facts, decisions, constraints, preferences, goals, architecture, important_events, active_tasks)
- [ ] Per-item scores: confidence, importance, stability, freshness, information_gain
- [ ] Deterministic low-info message skip (`ok`, `thanks`, `yes`, `continue`, …)
- [ ] Duplicate / merge detection
- [ ] Contradiction handling with supersede (status transitions)
- [ ] Explicit user decision authority vs speculation
- [ ] Information-gain gate before writes
- [ ] Versioned context state on each update
- [ ] Tests: extract, merge, supersede, confidence preserve, low-info skip

## Phase 4 — Memory AI (Optional)

- [ ] Memory AI config (`MEMORY_AI_ENABLED`, provider, model, key)
- [ ] Memory AI adapter (OpenRouter / OpenAI / compatible)
- [ ] Structured JSON prompt + Pydantic validation
- [ ] Retry-once on parse failure; keep prior memory otherwise
- [ ] Tool-output compression → compact summary; raw preserved
- [ ] Ensure Memory AI never used as main answer generator
- [ ] Tests: mocked AI success/failure; malformed JSON isolation

## Phase 5 — Context Compiler

- [ ] Assembler: system + canonical + recent + tool results + new message
- [ ] Token budget enforcement (`CONTEXT_BUDGET`)
- [ ] Selector scoring (`value / token_cost`)
- [ ] No naive head/tail truncation
- [ ] Persist compiled context version snapshots
- [ ] Tests: within budget, high-value priority, recent context kept

## Phase 6 — Retrieval & Cache

- [ ] SQLite FTS5 indexes for raw history + memory
- [ ] `Retriever` interface + FTS backend
- [ ] Stub/optional embedding path (off hot path)
- [ ] Version-aware caches (request, extraction, compilation, retrieval)
- [ ] Cache key includes conversation + context version + request hash
- [ ] Optional Redis adapter (not required for MVP)
- [ ] Background job hooks: embeddings, consolidation, repair

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

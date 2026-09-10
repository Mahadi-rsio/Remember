# Plan notes (phase exits)

Pull from `plan.md` when verifying a phase is done.

## Phase 0
Empty FastAPI app starts; env loads; Docker builds; `docker compose up` with SQLite only.

## Phase 1
OpenCode/Codex can point at gateway; responses match direct upstream (no memory yet). Streaming + non-streaming identity tests.

## Phase 2
Every request archives raw messages; only new deltas flagged for processing. Isolation keys exist.

## Phase 3
Memory updates from deltas without Memory AI for trivial turns. Contradiction supersede + information-gain gate.

## Phase 4
`MEMORY_AI_ENABLED=true` improves compression; `false` still works. Malformed JSON never corrupts canonical memory.

## Phase 5
Compiled context ≤ budget; coherent prompts to main model; versioned snapshots stored.

## Phase 6
FTS search works; caches version-safe; MVP runs without Redis.

## Phase 7
Auth/rate-limit hooks, redaction, retention, README, full suite green, compose smoke.

## Hard non-goals
Require Redis/vector DB; RAG-as-primary; rewrite responses; replace main model; require MCP/custom SDKs.

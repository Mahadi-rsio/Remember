# Plan notes (phase exits)

Pull from `plan.md` when verifying a phase is done.

## Phase 0
Hono app starts; env bindings load; `wrangler dev` boots with D1 only.

## Phase 1
OpenCode/Codex can point at gateway; responses match direct upstream (no memory yet). Streaming + non-streaming identity tests.

## Phase 2
Every request archives raw messages to D1; only new deltas flagged for processing. Isolation keys exist.

## Phase 3
Memory updates from deltas without Memory AI for trivial turns. Contradiction supersede + information-gain gate.

## Phase 4
`MEMORY_AI_ENABLED=true` improves compression; `false` still works. Malformed JSON never corrupts canonical memory.

## Phase 5
Compiled context ≤ budget; coherent prompts to main model; versioned snapshots stored in D1.

## Phase 6
FTS search works; caches version-safe; MVP runs without Upstash Redis.

## Phase 7
Auth/rate-limit hooks, redaction, retention, README, full suite green, `wrangler dev` smoke.

## Phase 8
Memory correctness ≥ 95%, correction accuracy ≥ 95%, false-memory rate ≈ 0%, interrogative noise = 0%. All existing tests pass.

## Phase 9
Full TypeScript test suite passes with `bun test`. Covers proxy identity, delta, memory engine, correction/revocation, context compiler, isolation, fail-open.

## Hard non-goals
Require Redis/vector DB; RAG-as-primary; rewrite responses; replace main model; require MCP/custom SDKs; Docker; Python.

---
name: memory-gateway
description: >-
  Steer the Remember AI Memory Gateway project: phase order, design invariants,
  progress tracking via todo.md, and next-task selection. Use when building,
  implementing, refactoring, testing, documenting, or checking status of the
  Memory Gateway / context compression proxy; when the user mentions phases,
  todo.md, plan.md, architecture, PROMT.md, OpenAI-compatible proxy, delta
  detection, context compiler, Memory AI, memory analyzer, three-way
  classification, store/context/discard, short-term, long-term, Redis,
  subject/predicate/value, structured memory, retrieval, or context composer.
---

# Memory Gateway — Project Steering

## Stack

**TypeScript · Cloudflare Workers · Hono · Drizzle ORM · Neon (PostgreSQL) · Upstash Redis**

No Python. No Docker.

## First actions (every session)

1. Read `todo.md` — source of truth for progress (checked = done).
2. Skim current phase in `plan.md` if scope is unclear.
3. For design disputes, prefer `architecture.md` then `PROMT.md`.
4. For HTTP surface, use `api.md`.

Do **not** re-read all docs every turn; load only what the task needs.

## Invariants (never violate)

1. Gateway optimizes context **to** the main model; never alters response **from** it.
2. Main upstream AI is mandatory for answers; Memory AI never answers the user.
3. Not conventional RAG-first; loop is `Context[n] + delta → memory → Context[n+1]`.
4. Raw archive is authoritative; compact memory is derived and repairable.
5. Memory failures must not break main AI forwarding (fail-open everywhere: PostgreSQL, Redis, Memory AI, retrieval).
6. **Dual-store memory:** durable facts → PostgreSQL as structured subject/predicate/value triples; transient "what's happening now" state → Redis (short-term) with TTL. Redis is optional only as a dependency — when absent, fall back to the in-memory store (never break the main path).
7. No MCP / custom client SDKs required — clients only change `base_url`.
8. No Docker. No Python. Cloudflare Workers only.
9. No embeddings / vector DB / graph DB yet — retrieval is deterministic (predicate/keyword/scope filters), not semantic.
10. Preserve history: supersede/revoke, never delete; keep `MemoryStatus` lifecycle (`active | superseded | revoked | expired | obsolete`).

## Phase order (do not skip ahead)

| Phase | Focus | Status |
|-------|--------|--------|
| 0 | Skeleton + Hono + health | ✅ Done |
| 1 | Transparent OpenAI proxy + streaming | ✅ Done |
| 2 | Neon archive + delta detection | ✅ Done |
| 3 | Deterministic memory engine | ✅ Done |
| 4 | Optional Memory AI compressor | ✅ Done |
| 5 | Fixed-budget context compiler | ✅ Done |
| 6 | FTS retrieval + versioned cache | ✅ Done |
| 7 | Security, hardening, README | ✅ Done |
| 8 | Memory correctness (FIX.md) — interrogative noise, correction/revocation, false-memory, conflict resolution | ✅ Done |
| 9 | **TypeScript test suite parity** — proxy identity, delta, memory engine, correction/revocation, context compiler, isolation, fail-open, e2e smoke | 🔲 Current |
| 10 | **Short-term + long-term memory architecture** — three-way analyzer (`store`/`context`/`discard`), structured SPV triples in PostgreSQL, short-term Redis context w/ TTL, context composer merges both, deterministic retrieval | ✅ Done |

Work the **lowest incomplete phase**. Only touch a later phase if the user explicitly asks or a blocker requires a thin stub.

## Key commands

```bash
bun run dev              # local dev via wrangler dev (port 8787)
bun test                 # run test suite
bun run typecheck        # tsc --noEmit
bun run deploy           # deploy to Cloudflare Workers
bun run db:migrate         # apply Neon migrations
bun run db:generate        # generate Drizzle migrations
bun run db:studio          # open Drizzle Studio
```

> **Integration tests need live services.** Source the env before running:
> `export $(grep -E '^(DATABASE_URL|UPSTASH_REDIS)' .dev.vars | xargs)` then `bun test`.
> `.dev.vars` is **not** auto-loaded by `bun test`.
>
> **Migrations on an existing Neon DB:** the Drizzle migrator requires a
> `__drizzle_migrations` journal table. If the baseline (`0000`) was applied
> manually, `db:migrate` fails with `42P07` (duplicate table). Apply new
> migrations via `drizzle-kit push` or run the new migration's SQL statements
> directly against the DB instead.

## Progress protocol

After finishing meaningful work in a phase:

1. Mark matching `- [ ]` → `- [x]` in `todo.md` (only items actually done).
2. If you discover new required work, add a checkbox under the right phase — do not invent new phases.
3. When the user asks for status, report:
   - Current phase
   - Done / remaining counts for that phase
   - Recommended next 1–3 tasks from unchecked items
   - Blockers (if any)

## Implementation habits

- Package layout: follow `architecture.md` (`src/...`).
- Prefer modular replaceable adapters (`OpenAICompatibleProvider`, `Retriever`, `ShortTermContextStore`).
- Hot path: delta → extract candidates → **Memory Analyzer** (three-way bucket) → store→PostgreSQL / context→Redis / discard→drop → compile (merge long-term + short-term) → upstream → unchanged response.
- Memory Analyzer modules: `src/memory/analyzer.ts` (classify/derive), `src/memory/context-store.ts` (Redis + in-memory store), `src/memory/retrieve.ts` (deterministic long-term retrieval), `src/context/compiler.ts` (context composer merging both stores).
- Structured long-term triples live on `memory_items` (`subject`, `predicate`, `value`, `scope`, `valid_from`, `valid_until`); persisted across all insert/update/contradiction paths.
- Short-term context keys: `current_error` (TTL 3600s), `active_debugging_context` / `current_task` / `recent_decisions` (TTL 7200s).
- Streaming: proxy SSE immediately; memory after complete / async via `waitUntil`.
- Tests required for: delta, memory merge/supersede, budget, proxy identity (stream + non-stream), analyzer classification, context store (in-memory + live Redis), retrieval, context composition.
- Do not commit unless the user asks.

## Decision shortcuts

| Question | Answer |
|----------|--------|
| Where to put code? | Matching module under `src/` |
| Docker? | No — Cloudflare Workers only |
| Python? | No — TypeScript only |
| Vector DB for MVP? | No |
| Truncate context from ends? | No — score by value/token_cost |
| Memory AI parse fail? | Retry once if configured; keep prior memory |
| Contradiction? | Supersede; don't wipe history; user decisions win |
| Client API docs? | `api.md` |
| Is a message a question? | Yes → skip extraction entirely (interrogative classifier) |
| Correction detected? | Store `{type:correction, target, old_value, new_value}`; set old fact → SUPERSEDED |
| Revocation detected? | Set memory item → REVOKED; keep in archive; exclude from compiled context |
| Conflict in compiled context? | Latest correction > latest ACTIVE > SUPERSEDED; never inject both |
| Memory-AI compressor? | Keep disabled unless user asks; deterministic engine must be independently correct |
| Local base URL? | `http://localhost:8787/v1` (wrangler dev) |
| Config secrets? | `wrangler secret put <KEY>` — never in `wrangler.jsonc` or committed files |
| Database? | Neon via `DATABASE_URL` |
| Where does a candidate go? | Three-way bucket via `src/memory/analyzer.ts`: `store`→PostgreSQL, `context`→Redis, `discard`→drop |
| What's a durable fact? | Stable/identity/preference (e.g. "My name is X", "X uses Y", "I prefer Z") → store |
| What's short-term context? | Transient "right now" state: debugging, current error/issue, current task → Redis w/ TTL |
| What's discarded? | Noise/filler acknowledgements (haha, ok, thanks, yes...) → dropped entirely |
| Short-term vs long-term in prompt? | Composer merges both: long-term SPV triples + a `[Short-Term Context]` block |
| Redis down? | Fail-open → `MemoryContextStore` (in-memory) fallback; never break main forwarding |
| How to test Redis? | Source `.dev.vars` (`UPSTASH_REDIS_REST_URL`/`TOKEN`) then `bun test tests/redis-context.integration.test.ts` |
| Upstash hash numeric values? | Returned as numbers (e.g. `401`), not strings — coerce with `String()` in assertions |

## Extra reference

- Phase exit criteria and risks: [plan.md](../../../plan.md)
- Architecture: [architecture.md](../../../architecture.md)
- HTTP surface: [api.md](../../../api.md)

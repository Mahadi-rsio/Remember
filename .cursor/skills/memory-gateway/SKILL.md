---
name: memory-gateway
description: >-
  Steer the Remember AI Memory Gateway project: phase order, design invariants,
  progress tracking via todo.md, and next-task selection. Use when building,
  implementing, refactoring, testing, documenting, or checking status of the
  Memory Gateway / context compression proxy; when the user mentions phases,
  todo.md, plan.md, architecture, PROMT.md, OpenAI-compatible proxy, delta
  detection, context compiler, or Memory AI.
---

# Memory Gateway — Project Steering

## Stack

**TypeScript · Cloudflare Workers · Hono · Drizzle ORM · Cloudflare D1 · Upstash Redis**

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
5. Memory failures must not break main AI forwarding.
6. MVP: Cloudflare D1 (SQLite-compatible); Upstash Redis optional only.
7. No MCP / custom client SDKs required — clients only change `base_url`.
8. No Docker. No Python. Cloudflare Workers only.

## Phase order (do not skip ahead)

| Phase | Focus | Status |
|-------|--------|--------|
| 0 | Skeleton + Hono + health | ✅ Done |
| 1 | Transparent OpenAI proxy + streaming | ✅ Done |
| 2 | D1 archive + delta detection | ✅ Done |
| 3 | Deterministic memory engine | ✅ Done |
| 4 | Optional Memory AI compressor | ✅ Done |
| 5 | Fixed-budget context compiler | ✅ Done |
| 6 | FTS retrieval + versioned cache | ✅ Done |
| 7 | Security, hardening, README | ✅ Done |
| 8 | Memory correctness (FIX.md) — interrogative noise, correction/revocation, false-memory, conflict resolution | ✅ Done |
| 9 | **TypeScript test suite parity** — proxy identity, delta, memory engine, correction/revocation, context compiler, isolation, fail-open, e2e smoke | 🔲 Current |

Work the **lowest incomplete phase**. Only touch a later phase if the user explicitly asks or a blocker requires a thin stub.

## Key commands

```bash
bun run dev              # local dev via wrangler dev (port 8787)
bun test                 # run test suite
bun run typecheck        # tsc --noEmit
bun run deploy           # deploy to Cloudflare Workers
bun run db:migrate:local # apply D1 migrations locally
bun run db:migrate:remote # apply D1 migrations to production
bun run db:generate      # generate Drizzle migrations
bun run db:studio        # open Drizzle Studio
```

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
- Prefer modular replaceable adapters (`OpenAICompatibleProvider`, `Retriever`).
- Hot path: delta → load memory → deterministic → Memory AI only if needed → compile → upstream → unchanged response.
- Streaming: proxy SSE immediately; memory after complete / async via `waitUntil`.
- Tests required for: delta, memory merge/supersede, budget, proxy identity (stream + non-stream).
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

## Extra reference

- Phase exit criteria and risks: [plan.md](../../../plan.md)
- Architecture: [architecture.md](../../../architecture.md)
- HTTP surface: [api.md](../../../api.md)

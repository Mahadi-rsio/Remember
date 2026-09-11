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
6. MVP: SQLite (+ FTS5); Redis / vectors / embeddings optional only.
7. No MCP / custom client SDKs required — clients only change `base_url`.

## Phase order (do not skip ahead)

| Phase | Focus | Unlock next when |
|-------|--------|------------------|
| 0 | Skeleton + Docker + health | App boots via compose |
| 1 | Transparent OpenAI proxy + streaming | Upstream response identity tests pass |
| 2 | SQLite archive + delta detection | Deltas correct under retry/dup |
| 3 | Deterministic memory engine | Low-info skip + supersede works without Memory AI |
| 4 | Optional Memory AI compressor | Disabled path still works; bad JSON isolated |
| 5 | Fixed-budget context compiler | Context ≤ `CONTEXT_BUDGET` |
| 6 | FTS retrieval + versioned cache | FTS works; stale cache impossible |
| 7 | Security, failure isolation, README | DoD checklist in `todo.md` complete |

Work the **lowest incomplete phase**. Only touch a later phase if the user explicitly asks or a blocker requires a thin stub.

## Progress protocol

After finishing meaningful work in a phase:

1. Mark matching `- [ ]` → `- [x]` in `todo.md` (only items actually done).
2. If you discover new required work, add a checkbox under the right phase — do not invent new phases.
3. When the user asks for status, report:
   - Current phase
   - Done / remaining counts for that phase
   - Recommended next 1–3 tasks from unchecked items
   - Blockers (if any)

Optional: run `python .agents/skills/memory-gateway/scripts/progress.py` for a checkbox summary.

## Implementation habits

- Package layout: follow `architecture.md` / `PROMT.md` §25 (`memory-gateway/app/...`).
- Prefer modular replaceable adapters (`AIProvider`, `Retriever`).
- Hot path: delta → load memory → deterministic → Memory AI only if needed → compile → upstream → unchanged response.
- Streaming: proxy SSE immediately; memory after complete / async.
- Tests required for: delta, memory merge/supersede, budget, proxy identity (stream + non-stream).
- Do not commit unless the user asks.

## Decision shortcuts

| Question | Answer |
|----------|--------|
| Where to put code? | Matching package under `memory-gateway/app/` |
| Vector DB for MVP? | No |
| Truncate context from ends? | No — score by value/token_cost |
| Memory AI parse fail? | Retry once if configured; keep prior memory |
| Contradiction? | Supersede; don't wipe history; user decisions win |
| Client API docs? | `api.md` |

## Extra reference

- Phase exit criteria and risks: [plan-notes.md](plan-notes.md)
- Status reply template: [status-template.md](status-template.md)

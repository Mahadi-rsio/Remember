# Memory Gateway

An OpenAI-compatible proxy that gives any client persistent memory. Clients only change
their `base_url` — no SDKs, no MCP, no custom tools.

```
Client ──▶ Gateway ──▶ Main AI (answers)
              │
              └─▶ Cloudflare D1: raw archive + compact memory + compiled context
```

**How it works:** every request is archived, diffed against known history (delta
detection), distilled into compact memory, and recompiled into a fixed-budget context
before reaching the main AI. The main AI always generates the answer; responses are
returned **unchanged** (streaming and non-streaming). The gateway optimizes what goes
*in*, never what comes *out*.

**Stack:** TypeScript · Cloudflare Workers · Hono · Drizzle ORM · Cloudflare D1 · Upstash Redis (optional)

---

## Install & Run

### Local development

```bash
bun install
cp .dev.vars.example .dev.vars
# Edit .dev.vars — set UPSTREAM_API_KEY at minimum

bun run db:migrate:local   # apply D1 migrations locally
bun run dev                # → wrangler dev → http://localhost:8787
curl http://localhost:8787/health
```

Run the test suite:

```bash
bun test
```

### Deploy to Cloudflare

```bash
# Set secrets (never committed to source)
wrangler secret put UPSTREAM_API_KEY
wrangler secret put GATEWAY_API_KEY       # optional
wrangler secret put UPSTASH_REDIS_REST_URL    # optional
wrangler secret put UPSTASH_REDIS_REST_TOKEN  # optional
wrangler secret put MEMORY_AI_API_KEY         # optional

# Apply migrations to production D1
bun run db:migrate:remote

# Deploy the Worker
bun run deploy
```

---

## Environment

Local secrets live in `.dev.vars` (never committed). Non-secret vars go in `wrangler.jsonc` under `"vars"`.

| Variable | Default | Where | Purpose |
|----------|---------|-------|---------|
| `UPSTREAM_BASE_URL` | `https://api.openai.com/v1` | `wrangler.jsonc` | Main AI provider base URL |
| `UPSTREAM_API_KEY` | — | **secret** | **Required.** Key for the main AI |
| `MEMORY_AI_ENABLED` | `false` | `wrangler.jsonc` | Optional AI compressor for memory |
| `MEMORY_AI_BASE_URL` / `_MODEL` / `_API_KEY` | — | jsonc / secret | Memory AI config |
| `CONTEXT_BUDGET` | `8000` | `wrangler.jsonc` | Token budget for compiled context |
| `GATEWAY_API_KEY` | unset | secret | Optional bearer auth on the gateway |
| `UPSTASH_REDIS_REST_URL` / `_TOKEN` | unset | secret | Optional Redis cache + rate limiting |
| `DB` | — | D1 binding | Raw archive + memory storage (managed by Cloudflare) |

### Providers

The upstream is any OpenAI-compatible endpoint — OpenAI, OpenRouter, vLLM, Ollama
(`http://localhost:11434/v1`), LM Studio, etc. Point `UPSTREAM_BASE_URL` + `UPSTREAM_API_KEY`
at it. The Memory AI compressor (optional) is configured separately and never answers users.

---

## Client configuration

Set `base_url` to the gateway. Nothing else changes.

### OpenAI SDK (TypeScript)

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:8787/v1",
  apiKey: "sk-anything",   // gateway key if GATEWAY_API_KEY is set
  defaultHeaders: {
    "X-Conversation-Id": "my-thread-42",
  },
});

const r = await client.chat.completions.create({
  model: "gpt-4.1",
  messages: [{ role: "user", content: "My codename is Falcon-Nine." }],
});
```

Next session, a bare question — *"What's my codename?"* — already knows. Memory is keyed
per conversation via the `X-Conversation-Id` header.

Without the header, the gateway derives a stable id from the first message of the thread.

### OpenAI SDK (Python)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8787/v1",
    api_key="sk-anything",
    default_headers={"X-Conversation-Id": "my-thread-42"},
)
r = client.chat.completions.create(
    model="gpt-4.1",
    messages=[{"role": "user", "content": "My codename is Falcon-Nine."}],
)
```

### OpenCode / Codex / any OpenAI-compatible tool

```text
base_url = http://localhost:8787/v1
api_key  = <GATEWAY_API_KEY or anything>
model    = <upstream model name>
```

### curl

```bash
curl -X POST http://localhost:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Conversation-Id: my-thread-42" \
  -d '{"model":"gpt-4.1","messages":[{"role":"user","content":"hi"}]}'
```

Full endpoint reference: [api.md](api.md).

---

## Context budget

`CONTEXT_BUDGET` (tokens) caps the compiled context sent upstream. Selection is
**score-based** — items are ranked by `value / token_cost` (importance, recency,
relevance) — never naive head/tail truncation. Each update persists a versioned context
snapshot, so state is auditable and repairable.

Override per-request with the `X-Context-Budget` header.

## Streaming

`"stream": true` works transparently: SSE chunks are proxied to the client as they
arrive (no full buffering); memory extraction runs after the stream completes via
`waitUntil`. Responses are byte-identical to upstream.

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `502` / connection refused on chat | `UPSTREAM_BASE_URL` reachable? `UPSTREAM_API_KEY` set? See Worker logs |
| `model_not_found` | Model name must exist on the *upstream*, not the gateway — check `GET /v1/models` |
| Memory not remembered | Reuse the same `X-Conversation-Id`; verify rows in D1 via `bun run db:studio` |
| `413` on upload | Body exceeds request size limit |
| Health fails on boot | D1 binding configured? Run `bun run db:migrate:local` |
| Want a fresh slate | Delete rows from D1 via Cloudflare dashboard or drop local `.wrangler/` state |

---

## Development

```text
src/
├── index.ts              # Hono app entry
├── env.ts                # Env bindings interface
├── routes/               # v1.ts, health.ts, auth.ts, rate-limit.ts
├── providers/            # OpenAI-compatible adapter, Memory AI adapter
├── memory/               # delta, engine, extractor, facts, correction, revocation,
│                         # interrogative, low-info, scorer, contradiction, state, isolation
├── context/              # compiler, assembler, selector, tokens
├── storage/              # archive.ts (raw message writer)
├── retrieval/            # FTS retriever interface + D1 backend
├── cache/                # version-aware cache (Upstash Redis optional)
├── models/               # Zod schemas + TypeScript types
└── db/                   # Drizzle ORM setup

drizzle/                  # Generated SQL migrations
tests/                    # bun test suite
wrangler.jsonc            # Cloudflare Workers config
```

Design docs: [architecture.md](architecture.md), [PROMT.md](PROMT.md), [api.md](api.md).

## Security

- Upstream API keys are Wrangler secrets only; never logged, never archived, never
  echoed in errors.
- Optional `GATEWAY_API_KEY` enables bearer auth for clients.
- Conversation data is isolated per conversation/user key; raw history and compact
  memory live in Cloudflare D1.
- Rate limiting via Upstash Ratelimit guards against abuse; memory/D1/retrieval failures
  degrade gracefully (the main AI is still called).

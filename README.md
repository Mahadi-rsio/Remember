# Memory Gateway

An OpenAI-compatible proxy that gives any client persistent memory. Clients only change
their `base_url` — no SDKs, no MCP, no custom tools.

```
Client ──▶ Gateway ──▶ Main AI (answers)
              │
              └─▶ SQLite: raw archive + compact memory + compiled context
```

**How it works:** every request is archived, diffed against known history (delta
detection), distilled into compact memory, and recompiled into a fixed-budget context
before reaching the main AI. The main AI always generates the answer; responses are
returned **unchanged** (streaming and non-streaming). The gateway optimizes what goes
*in*, never what comes *out*.

---

## Install

### Docker (recommended)

```bash
cd memory-gateway
cp .env.example .env          # then edit UPSTREAM_API_KEY
docker compose up --build -d
curl http://localhost:8000/health
```

### Local (Python 3.12+)

```bash
cd memory-gateway
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit UPSTREAM_API_KEY
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run the test suite:

```bash
pytest -q                     # 78 tests, no network needed
```

---

## Environment

All variables live in `memory-gateway/.env` (see `.env.example`).

| Variable | Default | Purpose |
|----------|---------|---------|
| `UPSTREAM_BASE_URL` | `https://api.openai.com/v1` | Main AI provider base URL |
| `UPSTREAM_API_KEY` | — | **Required.** Key for the main AI |
| `MEMORY_AI_ENABLED` | `false` | Optional AI compressor for memory |
| `MEMORY_AI_BASE_URL` / `_MODEL` / `_API_KEY` | OpenRouter / `cheap-model` | Memory AI config |
| `CONTEXT_BUDGET` | `8000` | Token budget for compiled context |
| `SQLITE_PATH` | `./data/memory.db` | Raw archive + memory storage |
| `GATEWAY_API_KEY` | unset | Optional bearer auth on the gateway (Phase 7 hook) |
| `MAX_REQUEST_BYTES` | `2000000` | Request body size limit |

### Providers

The upstream is any OpenAI-compatible endpoint — OpenAI, OpenRouter, vLLM, Ollama
(`http://localhost:11434/v1`), LM Studio, etc. Point `UPSTREAM_BASE_URL` + `UPSTREAM_API_KEY`
at it. The Memory AI compressor (optional) is configured separately and never answers users.

---

## Client configuration

Set `base_url` to the gateway. Nothing else changes.

### OpenAI client (Python)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="sk-anything",  # gateway key if GATEWAY_API_KEY is set
)
r = client.chat.completions.create(
    model="gpt-4.1",
    messages=[{"role": "user", "content": "My codename is Falcon-Nine."}],
)
```

Next session, a bare question — *"What's my codename?"* — already knows. Memory is keyed
per conversation: pass a stable header to keep turns in one thread:

```http
X-Conversation-Id: my-thread-42
```

Without it, the gateway derives a stable id from the first message of the thread.

### OpenCode / Codex / any OpenAI-compatible tool

Provider settings:

```text
base_url = http://localhost:8000/v1
api_key  = <GATEWAY_API_KEY or anything>
model    = <upstream model name>
```

### curl

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
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

## Streaming

`"stream": true` works transparently: SSE chunks are proxied to the client as they
arrive (no full buffering); memory extraction runs after the stream completes.
Responses are byte-identical to upstream.

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `502` / connection refused on chat | `UPSTREAM_BASE_URL` reachable? `UPSTREAM_API_KEY` set? See gateway logs |
| `model_not_found` | Model name must exist on the *upstream*, not the gateway — check `GET /v1/models` |
| Memory not remembered | Reuse the same `X-Conversation-Id`; verify rows in `memory_items` (SQLite) |
| `413` on upload | Body exceeds `MAX_REQUEST_BYTES` |
| Health fails on boot | `SQLITE_PATH` writable? (Docker mounts the `gateway-data` volume) |
| Want a fresh slate | Stop gateway, delete `data/memory.db`, restart |

---

## Benchmark

A live benchmark compares the gateway against the upstream directly (proxy overhead,
streaming latency, memory-write cost, and context compaction):

```bash
# gateway running on :8000, .env holds UPSTREAM_API_KEY
cd memory-gateway
python benchmarks/bench.py --runs 8
```

Measured live against a real upstream (Progga, `deepseek-v4-flash-0731`, 2026-09-11) —
full report in [memory-gateway/benchmarks/RESULTS.md](memory-gateway/benchmarks/RESULTS.md):

| Metric | Gateway | Direct | Delta |
|---|---:|---:|---:|
| Non-stream p50 latency | 625 ms | 635 ms | **−10 ms** |
| Non-stream p95 latency | 804 ms | 1392 ms | −588 ms |
| Stream time-to-first-token | 539 ms | 508 ms | +31 ms |
| Memory-write turn (extract+persist) | 691 ms | 647 ms | +44 ms |
| **Prompt tokens, 30-turn history** | **57** | 547 | **−90%** |

Takeaways: the proxy adds ~zero overhead (p50 within noise), the full memory pipeline
costs ~44 ms per turn, and the context compiler cut prompt tokens by **90%** on a long
conversation — the core value proposition.

## Security

- Upstream API keys are server-side config only; never logged, never archived, never
  echoed in errors.
- Optional `GATEWAY_API_KEY` enables bearer auth for clients.
- Conversation data is isolated per conversation/user key; raw history and compact
  memory live in local SQLite under `data/`.
- Request size limits guard against abuse; memory/SQLite/retrieval failures degrade
  gracefully (the main AI is still called).

## Development

```text
memory-gateway/
├── app/
│   ├── api/          # FastAPI routes (proxy, health)
│   ├── providers/    # AIProvider adapters (OpenAI-compatible)
│   ├── memory/       # delta detection, extraction, merge/supersede
│   ├── context/      # fixed-budget compiler
│   ├── storage/      # SQLModel + SQLite (+ FTS5)
│   ├── retrieval/    # FTS retriever
│   ├── cache/        # version-aware caches
│   └── models/       # canonical schemas
├── benchmarks/         # live benchmark: python benchmarks/bench.py
├── tests/              # 78 offline tests
└── Dockerfile / docker-compose.yml
```

Design docs: [architecture.md](architecture.md), [PROMT.md](PROMT.md), [api.md](api.md).

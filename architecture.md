# Architecture — AI Memory Gateway

## Role

The Memory Gateway is a **stateful context transformation layer**, not a chatbot and not a conventional RAG system. It receives OpenAI-compatible requests, maintains persistent conversation memory, compiles a fixed-budget context, forwards to the **main** AI provider, and returns the upstream response **unchanged**.

## High-Level Data Flow

```
OpenCode / Codex / AI Client
            │
            ▼
      Memory Gateway (FastAPI)
            │
     ┌──────┴─────────┐
     │                │
 Memory Engine    Context Compiler
     │                │
     ▼                ▼
Cheap AI Model   Optimized Context
 (optional)            │
     │                │
     └───────┬────────┘
             ▼
      MAIN AI PROVIDER
 OpenAI / Anthropic / Gemini /
 OpenRouter / OpenAI-compatible
             │
             ▼
     Original Response (unchanged)
             │
             ▼
           Client
```

### Central operation

```
PersistentContext[n] + NewMessages
        ↓
  Delta Detection
        ↓
  Memory Update
        ↓
PersistentContext[n+1]
        ↓
Fixed-Budget Context
        ↓
   MAIN AI MODEL
        ↓
 UNCHANGED RESPONSE
```

## Request Path (Hot Path)

Preferred critical path — keep it lightweight:

1. Receive OpenAI-compatible request
2. Authenticate / isolate conversation
3. Identify **delta** vs already-processed messages
4. Persist raw messages to archive
5. Load current versioned canonical memory
6. Deterministic memory processing
7. Call Memory AI **only when necessary**
8. Compile optimized context under token budget
9. Forward to main upstream API
10. Proxy response (stream or non-stream) **unchanged**
11. Optionally record assistant output for memory (post-complete / async)

Expensive work (embeddings, deep consolidation, archival indexing, memory repair, long-term summarization) runs **asynchronously** and must not block token delivery.

## Component Map

```
memory-gateway/
├── app/
│   ├── api/           # OpenAI-compatible HTTP routes
│   ├── providers/     # Upstream + Memory AI adapters
│   ├── memory/        # Delta, extract, compress, score, contradict, state
│   ├── context/       # Compiler, budget, selector
│   ├── storage/       # SQLite / SQLModel models & repos
│   ├── retrieval/     # FTS5 (+ future vector backends)
│   ├── cache/         # Version-aware caches
│   ├── models/        # Pydantic schemas
│   └── main.py
├── tests/
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

### API layer

- Exposes OpenAI-compatible surface so clients only change `base_url`.
- Does not require MCP, custom memory tools, or client SDK changes.
- Routes orchestrate memory + compile + provider; never rewrite assistant payloads.

### Provider layer

```python
class AIProvider:
    async def chat(...)
    async def responses(...)
    async def stream(...)
```

- **Main provider** (mandatory): generates the user-facing answer.
- **Memory AI provider** (optional): compresses/extracts structured memory only.
- First implementation: OpenAI-compatible HTTP adapter with configurable base URL.
- Native Anthropic/Gemini adapters can be added later without touching the memory engine.

### Memory engine

| Module | Responsibility |
|--------|----------------|
| `delta.py` | Detect new vs processed messages (IDs or hashes) |
| `extractor.py` | Candidate memory extraction (rules + AI) |
| `compressor.py` | Summaries, tool-output compaction |
| `scorer.py` | confidence, importance, stability, freshness, information_gain |
| `contradiction.py` | Versioned supersede; protect confirmed decisions |
| `state.py` | Canonical memory CRUD + versioning |

Pipeline per delta:

```
New Messages
  → Deterministic Rules
  → Candidate Extraction
  → Duplicate Detection
  → Contradiction Detection
  → Cheap AI Compression (if needed)
  → Canonical Memory Update
  → Versioned Context State
```

### Context compiler

Combines, under `CONTEXT_BUDGET`:

- System instructions
- Canonical memory (selected items)
- Relevant recent context
- Important current tool results
- New user message

Selection score ≈ `value / token_cost`, where value includes relevance, confidence, importance, freshness, stability, and information gain. Avoid naive truncation.

### Storage

**SQLite + FTS5** for MVP.

Three memory layers:

1. **Raw Archive** — original messages, tool I/O, metadata; never destroyed.
2. **Canonical Memory** — compact structured items (facts, decisions, constraints, preferences, goals, architecture, important_events, active_tasks).
3. **Recent Context** — short window of active conversation to avoid over-compression.

Every canonical update creates a new **context version** (`conversation_id`, `version`, `state`, `created_at`, `source_message_ids`). Never destructively mutate the only copy.

### Retrieval

```python
class Retriever:
    async def search(...): ...
```

- MVP backend: SQLite FTS5.
- Future: pgvector, Qdrant, Weaviate, Milvus.
- Embeddings optional; use only when semantic retrieval is needed.

### Cache

Optional Redis; SQLite sufficient for v1.

Layers: request, memory extraction, context compilation, retrieval, embedding.

Keys must include versions/hashes, e.g. `conversation_id + context_version + request_hash`. Never let an old cache entry override a newer context version.

## Memory Item Model

```json
{
  "content": "...",
  "type": "decision",
  "confidence": 0.96,
  "importance": 0.91,
  "stability": 0.88,
  "freshness": 0.70,
  "information_gain": 0.40,
  "source_message_ids": [],
  "created_at": "...",
  "updated_at": "...",
  "status": "active",
  "version": 12
}
```

Separate scores — do not collapse into one metric. Explicit user decisions outrank speculative model text. Corrections override prior memory. Low information gain skips duplicate writes.

## Memory AI Contract

When enabled, Memory AI returns **strict JSON** (schema-validated), e.g.:

```json
{
  "summary": "...",
  "facts": [],
  "decisions": [],
  "constraints": [],
  "preferences": [],
  "goals": [],
  "obsolete_items": [],
  "contradictions": [],
  "confidence": 0.92
}
```

On parse failure: retry once if configured; otherwise keep previous memory; never corrupt canonical state.

Memory AI must **not** generate the user's final answer.

## Failure Isolation

| Failure | Fallback |
|---------|----------|
| Memory AI down / bad JSON | Previous canonical memory + recent messages |
| SQLite / retrieval error | Best-effort recent messages → still call main AI |
| Embedding / cache miss | Skip optional path; continue |

Main upstream should remain usable whenever possible.

## Streaming

For `"stream": true`, proxy upstream SSE chunks directly. Do not buffer the full stream unless required. Memory extraction runs after completion or async. Never delay tokens for background memory work.

## Security Boundaries

- API authentication hooks
- Per-user / conversation isolation
- Request size limits
- Rate limiting hooks
- Secret redaction; no API-key logging
- Configurable retention
- Never store upstream API keys in raw conversation logs

## Configuration Surface (conceptual)

| Variable | Role |
|----------|------|
| `UPSTREAM_PROVIDER` / `UPSTREAM_BASE_URL` / `UPSTREAM_API_KEY` | Main AI |
| `MEMORY_AI_ENABLED` / `MEMORY_AI_*` | Optional compressor |
| `CONTEXT_BUDGET` | Token budget for compiled context |
| SQLite path / retention / auth secrets | Persistence & security |

## What This Is Not

- Not a RAG-first embedding → top-k → LLM loop for every turn
- Not a replacement for the main reasoning model
- Not a client-visible memory chatbot API (transparency is the product)

## Design Invariant

> The gateway optimizes what is sent **TO** the main model, but must not alter what comes **BACK FROM** the main model.

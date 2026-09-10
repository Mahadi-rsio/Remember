# API — AI Memory Gateway

OpenAI-compatible HTTP API. Clients point `base_url` at the gateway; no MCP, custom tools, or SDK changes required.

## Base URL

```
https://gateway.example.com/v1
```

Local MVP example:

```
http://localhost:8000/v1
```

Client → Gateway → Upstream:

```
Client
  ↓
https://gateway.example.com/v1
  ↓
https://api.openai.com/v1   # or OpenRouter / local / other compatible
```

## Authentication

Gateway authentication (client → gateway) is configurable via auth hooks (API key / bearer). Upstream credentials are configured on the gateway and must never appear in conversation logs.

Typical client header (when gateway auth enabled):

```http
Authorization: Bearer <GATEWAY_API_KEY>
```

Upstream uses server-side config:

```env
UPSTREAM_PROVIDER=openai
UPSTREAM_BASE_URL=https://api.openai.com/v1
UPSTREAM_API_KEY=...
```

## Endpoints (MVP)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/chat/completions` | Chat Completions (primary) |
| `POST` | `/v1/responses` | Responses API |
| `GET` | `/v1/models` | List models (proxied / filtered) |
| `GET` | `/health` | Liveness (gateway-local) |

### POST `/v1/chat/completions`

Accepts standard OpenAI Chat Completions request bodies.

Gateway behavior:

1. Archive raw messages; compute delta
2. Update persistent memory when needed
3. Compile fixed-budget context
4. Forward optimized request to main upstream
5. Return upstream response **unchanged**

Streaming:

```json
{
  "model": "gpt-4.1",
  "stream": true,
  "messages": [
    {"role": "user", "content": "Continue the Neon migration plan."}
  ]
}
```

When `stream: true`, the gateway proxies upstream SSE chunks to the client without buffering the full stream. Memory extraction runs after completion or asynchronously.

Non-streaming: JSON body is returned exactly as received from upstream (assistant text, tool calls, finish_reason, usage, ids, metadata preserved).

### POST `/v1/responses`

OpenAI-compatible Responses API passthrough with the same memory → compile → upstream → unchanged response pipeline.

### GET `/v1/models`

Proxies or presents available models from the configured upstream so clients can discover models through the gateway base URL.

### GET `/health`

Gateway-local health check (does not require upstream). Used by Docker / orchestration.

## Conversation Identity

The gateway keys persistent state by conversation / user isolation identifiers derived from:

- Explicit conversation IDs when the client/provider supplies them
- Stable request/session metadata when available
- Otherwise deterministic derivation from message history fingerprints

Clients should reuse the same conversation identity across turns for correct delta detection and memory continuity.

## What the Gateway Changes vs Does Not Change

| Direction | Behavior |
|-----------|----------|
| **Request → Upstream** | May replace/expand `messages` (or equivalent) with a compiled fixed-budget context derived from persistent memory + recent context + new user message |
| **Response → Client** | Must be identical to upstream (stream and non-stream). No rewriting of assistant text, tool calls, arguments, finish reasons, usage, response IDs, or metadata |

## Memory AI (Not a Client API)

Memory compression uses an optional internal adapter. It is **not** exposed as a separate public chat endpoint for end-user answers.

```env
MEMORY_AI_ENABLED=true
MEMORY_AI_PROVIDER=openrouter
MEMORY_AI_MODEL=cheap-model
MEMORY_AI_API_KEY=...
```

Memory AI returns validated structured JSON for internal state updates only.

## Context Budget

```env
CONTEXT_BUDGET=8000
```

Compiled context sent upstream should be approximately ≤ this token budget. Selection is score-based (`value / token_cost`), not naive truncation.

## Error Behavior

- Upstream errors: mapped/proxied to the client with safe handling; prefer preserving upstream status/body where appropriate.
- Memory / SQLite / retrieval / Memory AI failures: **fallback** to previous canonical memory + recent messages and still call the main AI whenever possible.
- Malformed Memory AI output: retry once if configured; otherwise leave memory unchanged.

Memory failures must not normally break the main completion path.

## Provider Extensibility

Server-side provider interface:

```python
class AIProvider:
    async def chat(...)
    async def responses(...)
    async def stream(...)
```

MVP ships an OpenAI-compatible adapter covering OpenAI, OpenRouter, local servers, and other compatible bases. Additional native adapters (Anthropic, Gemini, etc.) can be added without changing the memory engine.

## Security Notes for API Consumers

- Do not send upstream provider secrets in message content.
- Respect request size limits.
- Expect rate-limit hooks on the gateway.
- Conversation data is isolated per user/conversation; retention is configurable.

## Client Configuration Examples

### Generic OpenAI-compatible client

```text
base_url = http://localhost:8000/v1
api_key  = <GATEWAY_API_KEY>
model    = <upstream model name>
```

### OpenCode / Codex

Set the provider base URL to the gateway `/v1` endpoint and use the gateway API key. No custom memory tools or MCP required — the gateway is transparent.

## Invariant

The public API looks like OpenAI. Internally the gateway rewrites **outgoing context** only. **Incoming model responses are never altered.**

Build a production-oriented AI Memory Gateway / Context Compression Proxy in TypeScript on Cloudflare Workers.

The gateway sits transparently between AI clients such as OpenCode, Codex, or other OpenAI-compatible agents and the real upstream AI API.

Core Goal

The gateway must:

1. Receive the AI client's normal API request.
2. Detect only the new/delta messages since the previous request.
3. Maintain persistent conversation memory/state.
4. Use a cheap AI model optionally to convert important information into compact, structured memory and summaries.
5. Build a fixed-size, optimized context from the persistent state + relevant recent messages.
6. Forward that optimized request to the actual/main AI API.
7. Return the actual model's response to the client unchanged.

The gateway itself is NOT the main reasoning model.

Architecture:

OpenCode / Codex / AI Client
            │
            ▼
      Memory Gateway
            │
     ┌──────┴─────────┐
     │                │
 Memory Engine    Context Compiler
     │                │
     ▼                ▼
Cheap AI Model   Optimized Context
     │                │
     └───────┬────────┘
             ▼
      MAIN AI PROVIDER
 OpenAI / Anthropic / Gemini /
 OpenRouter / etc.
             │
             ▼
     Original Response
             │
             ▼
       Client unchanged

---

1. Transparent API Proxy

Implement an OpenAI-compatible API.

At minimum support:

POST /v1/chat/completions
POST /v1/responses
GET  /v1/models

Design the provider layer so additional providers can be added easily.

Example:

UPSTREAM_PROVIDER=openai
UPSTREAM_BASE_URL=https://api.openai.com/v1
UPSTREAM_API_KEY=...

The client should only need to change its API base URL to the gateway.

Example:

Client
  ↓
https://gateway.example.com/v1
  ↓
https://api.openai.com/v1

Do not require MCP, custom memory tools, special SDKs, or modifications to OpenCode/Codex.

---

2. Main AI API Is Mandatory

The gateway MUST forward the final optimized request to a real upstream AI API.

The main AI provider is responsible for generating the actual answer.

Examples:

- OpenAI
- Anthropic
- Gemini
- OpenRouter
- other OpenAI-compatible providers

The gateway must NOT replace the main model with its own memory model.

---

3. Cheap AI Model for Memory Compression

Implement an optional Memory AI adapter.

Its purpose is ONLY to process memory.

It should:

- summarize old/repeated information
- extract facts
- extract decisions
- extract constraints
- extract preferences
- extract goals
- compress tool results
- identify obsolete information
- detect contradictions
- update compact memory state
- generate compact summaries

It must NOT generate the user's final answer.

Example configuration:

MEMORY_AI_ENABLED=true
MEMORY_AI_PROVIDER=openrouter
MEMORY_AI_MODEL=cheap-model
MEMORY_AI_API_KEY=...

The implementation must allow providers such as:

OpenRouter
OpenAI
Gemini
Anthropic
local OpenAI-compatible model

The memory AI should be replaceable without changing the core memory engine.

---

4. Important: Do Not Use Conventional RAG as the Main Architecture

Do NOT implement this as:

every message
    ↓
embedding
    ↓
vector DB
    ↓
top-k retrieval
    ↓
LLM

That is conventional RAG.

The primary memory mechanism must instead be:

Context[n] + NewMessages
          ↓
     Delta Detection
          ↓
     Memory Processing
          ↓
      Context[n+1]

The active context should remain approximately fixed-size while its information is continuously updated.

Raw messages must still be preserved separately.

---

5. Persistent Memory Model

Maintain three layers.

A. Raw Archive

Store the original:

- user messages
- assistant messages
- tool calls
- tool outputs
- system messages when appropriate
- request metadata

Never destroy the original conversation.

B. Canonical Memory

Maintain compact structured information such as:

{
  "facts": [],
  "decisions": [],
  "constraints": [],
  "preferences": [],
  "goals": [],
  "architecture": [],
  "important_events": [],
  "active_tasks": []
}

Each memory item should contain metadata:

{
  "content": "...",
  "type": "decision",
  "confidence": 0.96,
  "importance": 0.91,
  "stability": 0.88,
  "source_message_ids": [],
  "created_at": "...",
  "updated_at": "...",
  "status": "active",
  "version": 12
}

C. Recent Context

Keep a small amount of recent conversation directly available.

This prevents the system from over-compressing information that is still actively relevant.

---

6. Delta Detection

Do not reprocess the entire conversation on every request.

Identify:

already_processed_messages
+
new_messages
=
delta

Use stable message IDs when available.

If IDs are unavailable, use deterministic hashes of message content + role + ordering metadata.

Handle:

- duplicate messages
- reordered messages
- missing messages
- retries
- repeated API requests

Only newly observed information should normally enter the memory processing pipeline.

---

7. Cheap AI Memory Compression Pipeline

For each delta:

New Messages
     ↓
Deterministic Rules
     ↓
Candidate Memory Extraction
     ↓
Duplicate Detection
     ↓
Contradiction Detection
     ↓
Cheap AI Compression/Summary
     ↓
Canonical Memory Update
     ↓
Versioned Context State

Do NOT call the cheap AI model for every trivial message.

Use deterministic rules first.

Examples of messages that may require little/no AI processing:

"ok"
"thanks"
"yes"
"continue"
"run it"
"do that"

The system should detect low information gain and avoid unnecessary memory-AI calls.

---

8. Memory AI Output Must Be Structured

The cheap model should return strict JSON.

Example:

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

Use JSON schema / structured output when the provider supports it.

Never directly trust arbitrary free-form output from the memory model.

Validate it before updating memory.

If parsing fails:

1. retry once if configured
2. otherwise keep the previous memory state unchanged
3. never corrupt canonical memory because of malformed cheap-AI output

---

9. Confidence, Importance and Stability

Do NOT use one score for everything.

Maintain separate values:

confidence
importance
stability
freshness
information_gain

Example:

"We might use Neon"
confidence = 0.60

"We decided to use Neon for production"
confidence = 0.95

Explicit user decisions should have higher authority than model speculation.

Repeated confirmation can increase stability.

Explicit user correction must be able to override previous memory.

---

10. Contradiction Handling

Never blindly overwrite old memory.

Example:

Old:
Database = Supabase

New:
Database = Neon

Create a versioned transition:

Supabase → superseded
Neon → active

Keep historical information in the raw archive.

The latest explicit decision should normally win.

Do not allow speculative AI-generated information to silently overwrite confirmed user decisions.

---

11. Information Gain

Use information gain to determine whether new messages actually change the memory state.

Example:

Current memory:
Database = Neon

New message:
"Yes, we're still using Neon."

Information gain = low

No need to create another duplicate memory item.

But:

Current memory:
Database = Neon

New message:
"We switched production to PostgreSQL on AWS."

Information gain = high.

Update the relevant memory.

Information gain is preferred over using raw entropy as the primary importance metric.

Entropy can be used as an uncertainty signal when useful.

---

12. Context Compiler

The context compiler creates the optimized context sent to the main AI model.

It should combine:

System instructions
+
Canonical Memory
+
Relevant Recent Context
+
Important Current Tool Results
+
New User Message

The output must respect a configurable token budget.

Example:

CONTEXT_BUDGET=8000

If the budget is 8000 tokens, the compiler must produce approximately an 8000-token-or-less context.

Do not simply truncate from the beginning or end.

Treat context selection as a constrained optimization problem.

Conceptually:

selection_score =
    value / token_cost

where value incorporates:

relevance
confidence
importance
freshness
stability
information_gain

---

13. Tool Output Compression

Treat tool outputs specially.

Large outputs such as:

git diff
compiler logs
npm logs
test output
file contents
directory listings
API responses
database results

should not remain permanently in the active context if they are no longer useful.

The cheap memory model may convert them into compact information such as:

Test result:
42 tests passed
2 failed

Relevant failure:
src/auth.ts line 81
JWT expiration bug

But preserve the original tool output in the raw archive.

The system must be able to retrieve the original data when required.

---

14. Raw Data vs Compact Memory

Never confuse:

memory

with:

raw history

The raw history is authoritative.

Compact memory is an optimized representation.

If compact memory becomes incorrect, the system should be able to reconstruct or repair it from the raw archive.

---

15. Retrieval

Start with SQLite.

Use:

SQLite
SQLite FTS5

for searchable raw history and memory.

Do NOT require an external vector database for the MVP.

Design a clean interface so embeddings/vector search can later be added:

class Retriever:
    async def search(...):
        ...

Possible future backends:

SQLite FTS5
pgvector
Qdrant
Weaviate
Milvus

Embeddings are optional.

They should be used only when semantic retrieval is actually necessary.

---

16. Context Versioning

Every canonical memory update should create a new version.

Example:

Context v180
Context v181
Context v182
Context v183

Store:

conversation_id
version
state
created_at
source_message_ids

Never destructively mutate the only copy of the context.

This also prevents stale cache entries from replacing newer context.

---

17. Caching

Implement version-aware caching.

Possible cache layers:

request cache
memory extraction cache
context compilation cache
retrieval cache
embedding cache

Cache keys must include relevant versions/hashes.

Example:

conversation_id + context_version + request_hash

Never allow an old context cache to override a newer context version.

Redis should be optional.

SQLite should be sufficient for the first version.

---

18. Latency Design

The request path should be lightweight.

Preferred flow:

Receive request
      ↓
Identify delta
      ↓
Load current memory
      ↓
Run deterministic processing
      ↓
Run cheap AI only when necessary
      ↓
Compile optimized context
      ↓
Call main AI API
      ↓
Return response

Expensive background work may happen asynchronously.

Examples:

- embeddings
- deep consolidation
- archival indexing
- memory repair
- long-term summarization

Do not make the critical request path unnecessarily dependent on expensive operations.

---

19. CRITICAL RESPONSE TRANSPARENCY REQUIREMENT

The gateway must return the actual upstream model response unchanged.

For successful upstream requests:

Upstream response
        ↓
Gateway
        ↓
Client

Do not rewrite:

- assistant text
- tool calls
- tool arguments
- finish reasons
- usage information
- response IDs
- metadata

Preserve the upstream response structure.

For streaming responses, proxy the stream transparently.

For example:

Client
  ↓
Gateway
  ↓
Main Model
  ↓
SSE stream
  ↓
Gateway
  ↓
Client

Do not buffer the entire stream unless absolutely required.

The gateway may internally record the response for memory processing, but the client-facing response must remain unchanged.

Memory processing must NEVER modify the actual model response.

---

20. Streaming

Support streaming where the upstream provider supports it.

For:

{
  "stream": true
}

the gateway should stream upstream chunks directly to the client.

Memory extraction can happen after the response is complete or asynchronously.

Do not delay token delivery just because the memory system is processing something in the background.

---

21. Failure Isolation

Memory failures must not normally break the main AI request.

If:

Memory AI fails
SQLite fails
Embedding service fails
Retrieval fails

the gateway should have a safe fallback.

For example:

Memory AI unavailable
      ↓
Use previous canonical context
      ↓
Include recent messages
      ↓
Forward request to main AI

The main AI provider should remain independently usable whenever possible.

---

22. API Provider Abstraction

Create provider adapters:

class AIProvider:
    async def chat(...)
    async def responses(...)
    async def stream(...)

Implement at least:

OpenAI-compatible provider

with configurable base URL.

This should allow:

OpenAI
OpenRouter
local models
other compatible APIs

without changing the memory engine.

Create separate adapters later for providers whose API format differs significantly.

---

23. Security

Implement:

- API authentication
- per-user/conversation isolation
- request size limits
- rate limiting hooks
- secret redaction
- safe error handling
- no API-key logging
- configurable retention
- encrypted secrets where appropriate

Never store upstream API keys in raw conversation logs.

---

24. Suggested Stack

Use:

TypeScript
Cloudflare Workers
Hono
Drizzle ORM
Cloudflare D1 (SQLite-compatible)
Bun (package manager + test runner)

Optional:

Upstash Redis (caching + rate limiting)
Embeddings
Vector database
Cheap LLM API

Do not make optional components mandatory for the MVP.

---

25. Project Structure

Create a clean modular project such as:

src/
├── index.ts
├── env.ts
├── routes/
│   ├── v1.ts
│   ├── health.ts
│   ├── auth.ts
│   └── rate-limit.ts
├── providers/
│   ├── openai-compatible.ts
│   └── memory-ai.ts
├── memory/
│   ├── extractor.ts
│   ├── compressor.ts
│   ├── scorer.ts
│   ├── contradiction.ts
│   ├── correction.ts
│   ├── revocation.ts
│   ├── interrogative.ts
│   ├── low-info.ts
│   ├── facts.ts
│   ├── delta.ts
│   ├── engine.ts
│   ├── state.ts
│   ├── ids.ts
│   └── isolation.ts
├── context/
│   ├── compiler.ts
│   ├── assembler.ts
│   ├── selector.ts
│   └── tokens.ts
├── storage/
│   └── archive.ts
├── retrieval/
├── cache/
├── models/
└── db/

drizzle/
tests/
wrangler.jsonc
.dev.vars.example
package.json

Keep the architecture modular and easy to replace.

---

26. Testing

Write tests for:

Delta detection

new messages detected
duplicate messages ignored
retries handled

Memory

facts extracted
duplicates merged
contradictions detected
old values superseded
confidence preserved

Compression

large conversation → compact memory
low-information messages → no unnecessary memory update
tool output → compact summary

Context compiler

context remains within token budget
high-value information prioritized
recent task context preserved

Proxy

request forwarded correctly
headers preserved where appropriate
streaming works
upstream errors handled

Response transparency

Create tests proving that:

upstream response == gateway client response

for both:

non-streaming
streaming

The memory system must not modify the response.

---

27. Deployment

The MVP runs on Cloudflare Workers. Provide:

wrangler.jsonc
.dev.vars.example

Local development:

bun run dev

without requiring Redis, vector DB, or another external service.

Cloudflare D1 (SQLite-compatible) works immediately via the local wrangler D1 emulation.

---

28. README

Document:

1. installation
2. environment variables
3. starting the gateway
4. configuring OpenCode
5. configuring Codex
6. configuring an OpenAI-compatible client
7. configuring the main AI provider
8. configuring the cheap memory AI
9. context budget
10. SQLite storage
11. streaming
12. memory architecture
13. troubleshooting
14. security considerations

Include concrete examples.

---

29. Important Design Principle

The gateway is fundamentally a stateful context transformation layer, not a chatbot and not a normal RAG system.

The central operation is:

PersistentContext[n]
        +
NewMessages
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

The cheap AI exists only to make the persistent representation more compact and useful.

The actual/main AI remains responsible for reasoning and answering.

Raw history remains recoverable.

The client should feel like it is communicating directly with the upstream model, except the gateway intelligently manages the context behind the scenes.

---

Final Implementation Requirement

Do not build a toy summarization proxy.

Build the actual working MVP with:

- Hono + Cloudflare Workers
- OpenAI-compatible proxy
- mandatory upstream/main AI forwarding
- optional cheap memory AI
- persistent Cloudflare D1 memory
- raw message archive
- delta detection
- structured compact memory
- confidence/importance/stability
- contradiction handling
- information-gain detection
- fixed-token context compiler
- D1 FTS retrieval
- optional embedding/vector interface
- versioned context state
- caching (Upstash Redis optional)
- streaming proxy
- failure isolation
- authentication hooks
- tests (`bun test`)
- documentation

Most importantly:

The gateway optimizes what is sent TO the main model, but must not alter what comes BACK FROM the main model.

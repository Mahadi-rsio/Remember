---
name: live-api-tests
description: >-
  Write REAL integration tests for the Remember Memory Gateway that hit live
  services with the real API keys from .dev.vars — the actual Progga upstream
  AI (deepseek/glm models), the Neon PostgreSQL test DB, and the real Upstash
  Redis. Use when creating or running true end-to-end tests against the live
  API key / live upstream, when mocking globalThis.fetch or the in-memory
  context store is NOT enough, or when the user asks for "real real" tests,
  live E2E, or tests that consume the production provider. Covers app.request
  with env bindings, sourcing .dev.vars, live model names, and avoiding secret
  leaks.
---

# Live API Integration Tests

This skill is for **real** tests that consume live credentials from
`.dev.vars` — the real upstream AI provider, real Neon PostgreSQL, and real
Upstash Redis. Use it when mocked `fetch` / in-memory stores are not enough.

## When to use THIS skill vs the unit/other tests

| Test tier | Hits real services? | Example file |
|-----------|--------------------|--------------|
| Unit (`*.test.ts`) | No — pure logic, no network/DB | `tests/analyzer.test.ts` |
| Integration (`*.integration.test.ts`) | Real Neon + real Redis, but upstream `fetch` is **mocked** | `tests/short-term-long-term.integration.test.ts` |
| **Live API (this skill)** | Real Neon + real Redis **and real upstream AI** (no fetch mock) | `tests/live-api.e2e.test.ts` (create if needed) |

The user's phrase "real real test with the live api key" = the third tier:
a true end-to-end round trip through the gateway to the actual provider.

## Ground truth (from the codebase — do not guess these)

- **Gateway auth key:** `Bearer 1234` — hardcoded in `src/auth/identity.ts`
  (`GATEWAY_API_KEY = "1234"`, resolves to `TEST_USER_ID = "test-user"`).
  This is the key the *client* sends to the gateway, NOT the upstream key.
- **Upstream key:** `UPSTREAM_API_KEY` in `.dev.vars` (Progga provider).
  Sent by the gateway to the real upstream. Never hardcode it in a test —
  always read from env.
- **Available live models** (Progga / api.progga.app — OpenAI gpt models are
  NOT available here): `deepseek-v4-flash-0731`, `deepseek-v4-pro-0813`,
  `glm-5.2`, `glm-5.3`, ... Discover the exact list at runtime via
  `GET /v1/models` (below). Use `deepseek-v4-flash-0731` as the default live
  model for tests.
- **Calling the Hono app in-process with real env:** pass the env as the
  **third argument** to `app.request(path, init, env)`:

  ```ts
  const res = await app.request("/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer 1234" },
    body: JSON.stringify({ model, messages, max_tokens }),
  }, liveEnv());
  ```

- **Redis quirks:** Upstash returns numeric-looking hash values as **numbers**
  (e.g. `401`), not strings — coerce with `String(x)` in assertions.

## Setting up the live env in a test

`.dev.vars` is **not** auto-loaded by `bun test`, and it is **gitignored** (so
secrets never reach the repo). Build the env object from `process.env` after
sourcing it on the command line.

```ts
function liveEnv() {
  return {
    UPSTREAM_PROVIDER: process.env.UPSTREAM_PROVIDER,
    UPSTREAM_BASE_URL: process.env.UPSTREAM_BASE_URL,
    UPSTREAM_API_KEY: process.env.UPSTREAM_API_KEY,
    DATABASE_URL: process.env.DATABASE_URL,
    UPSTASH_REDIS_REST_URL: process.env.UPSTASH_REDIS_REST_URL,
    UPSTASH_REDIS_REST_TOKEN: process.env.UPSTASH_REDIS_REST_TOKEN,
    CONTEXT_BUDGET: "8000",
    MEMORY_AI_ENABLED: "false",
  };
}
```

`createTestDb()` from `tests/helpers/db.ts` truncates all DB tables for a
clean slate (already used by the other integration tests).

## How to RUN live tests (must source env first)

```bash
export $(grep -E '^(DATABASE_URL|UPSTASH_REDIS|UPSTREAM)' .dev.vars | xargs)
bun test tests/live-api.e2e.test.ts
```

Never print the `UPSTREAM_API_KEY` or `UPSTASH_REDIS_REST_TOKEN` to logs or
assertions. Redact anything that might contain them.

## Example: discover live models (safe, cheap)

```ts
import { describe, expect, it } from "bun:test";
import app from "../src/index";

describe("live /v1/models", () => {
  it("returns the real upstream model list", async () => {
    const res = await app.request("/v1/models", {
      headers: { Authorization: "Bearer 1234" },
    }, liveEnv());
    expect(res.status).toBe(200);
    const data = await res.json() as any;
    const ids = data.data.map((m: any) => m.id);
    expect(ids).toContain("deepseek-v4-flash-0731");
  });
});
```

## Example: true live chat round trip (no fetch mock)

```ts
import { describe, expect, it } from "bun:test";
import app from "../src/index";

describe("live chat completions", () => {
  it("forwards to the real upstream and returns a real answer", async () => {
    const res = await app.request("/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer 1234" },
      body: JSON.stringify({
        model: "deepseek-v4-flash-0731",
        messages: [{ role: "user", content: "Reply with exactly: OK" }],
        max_tokens: 10,
      }),
    }, liveEnv());
    expect(res.status).toBe(200);
    const data = await res.json() as any;
    expect(data.choices[0].message.content.trim().toUpperCase()).toBe("OK");
    expect(data.model).toBe("deepseek-v4-flash-0731");
  });
});
```

## Live memory flow (proves dual-store with real everything)

1. `archiveRequest` a durable fact ("My name is Mahadi") → assert it lands in
   **PostgreSQL** via `listMemoryItems` / `retrieveMemories`.
2. `archiveRequest` a transient fact ("I'm currently debugging auth") → assert
   it lands in **real Redis** (`RedisContextStore`), NOT PostgreSQL.
3. `compileContext` with the live `contextStore` → assert the compiled prompt
   contains both the long-term fact and the `[Short-Term Context]` block.
4. Send the compiled messages through the real upstream → assert a real answer.

Reuse `createTestContextStoreFromRedis(getRedis(liveEnv()))` (i.e.
`createContextStoreFromRedis` + `getRedis`) for the live Redis context store.

## Checklist before committing a live test

- [ ] Reads all secrets from `process.env` (sourced from `.dev.vars`), never hardcoded.
- [ ] Defaults to a real available model (`deepseek-v4-flash-0731`), discovered via `/v1/models` if uncertain.
- [ ] Uses a unique `userId` (e.g. `live-e2e-${Date.now()}`) so parallel/local runs don't collide; clean up after.
- [ ] Asserts against the live upstream (no `globalThis.fetch` mock).
- [ ] No secret ever printed or asserted.
- [ ] Passes with: `export $(grep -E '^(DATABASE_URL|UPSTASH_REDIS|UPSTREAM)' .dev.vars | xargs) && bun test <file>`.

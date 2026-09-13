import { describe, expect, it } from "bun:test";
import app from "../src/index";
import { createTestDb } from "./helpers/db";
import type { Database } from "../src/db";
import { getRedis } from "../src/cache";
import { createContextStoreFromRedis } from "../src/memory/context-store";
import type { ShortTermContextStore } from "../src/memory/context-store";
import { archiveRequest } from "../src/storage/archive";
import { listMemoryItems } from "../src/memory/state";
import { compileContext } from "../src/context/compiler";
import { MemoryStatus } from "../src/models/memory";

const LIVE_MODEL = process.env.LIVE_MODEL || "deepseek-v4-flash-0731";
const uid = `live-e2e-${Date.now()}`;

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

describe("Live API E2E (real upstream, real Neon, real Redis)", () => {
  it("requires live credentials to be sourced", () => {
    expect(process.env.UPSTREAM_API_KEY).toBeTruthy();
    expect(process.env.DATABASE_URL).toBeTruthy();
    expect(process.env.UPSTASH_REDIS_REST_URL).toBeTruthy();
  });

  it("returns the real upstream model list via /v1/models", async () => {
    const res = await app.request(
      "/v1/models",
      { headers: { Authorization: "Bearer 1234" } },
      liveEnv()
    );
    expect(res.status).toBe(200);
    const data = (await res.json()) as any;
    const ids = data.data.map((m: any) => m.id);
    expect(ids).toContain(LIVE_MODEL);
  });

  it("forwards to the real upstream and returns a real answer", async () => {
    const res = await app.request(
      "/v1/chat/completions",
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer 1234" },
        body: JSON.stringify({
          model: LIVE_MODEL,
          messages: [{ role: "user", content: "Reply with exactly: OK" }],
          max_tokens: 10,
        }),
      },
      liveEnv()
    );
    expect(res.status).toBe(200);
    const data = (await res.json()) as any;
    expect(data.choices[0].message.content.trim().toUpperCase()).toBe("OK");
    expect(data.model).toBe(LIVE_MODEL);
  });

  it("stores a durable fact in real PostgreSQL via the live flow", async () => {
    const db = await createTestDb();
    const ctx: ShortTermContextStore = createContextStoreFromRedis(getRedis(liveEnv() as any));
    await archiveRequest(
      db,
      { messages: [{ role: "user", content: "My name is Mahadi" }] },
      { userId: uid, contextStore: ctx }
    );
    const items = await listMemoryItems(db, uid, MemoryStatus.ACTIVE);
    expect(items.length).toBeGreaterThan(0);
    expect(items[0].content.toLowerCase()).toContain("mahadi");
    // durable facts stay OUT of Redis
    expect(await ctx.getAllContext(uid)).toHaveLength(0);
  });

  it("routes transient state to real Redis, not PostgreSQL", async () => {
    const db = await createTestDb();
    const ctx: ShortTermContextStore = createContextStoreFromRedis(getRedis(liveEnv() as any));
    await archiveRequest(
      db,
      { messages: [{ role: "user", content: "I'm currently debugging an auth bug" }] },
      { userId: uid, contextStore: ctx }
    );
    const entries = await ctx.getAllContext(uid);
    expect(entries.length).toBeGreaterThan(0);
    expect((await listMemoryItems(db, uid, null)).length).toBe(0);
    await ctx.clearUser(uid);
  });

  it("composes live long-term + short-term context and answers via real upstream", async () => {
    const db = await createTestDb();
    const ctx: ShortTermContextStore = createContextStoreFromRedis(getRedis(liveEnv() as any));

    await archiveRequest(
      db,
      { messages: [{ role: "user", content: "My name is Mahadi" }] },
      { userId: uid, contextStore: ctx }
    );
    await archiveRequest(
      db,
      { messages: [{ role: "user", content: "I'm currently debugging an auth bug" }] },
      { userId: uid, contextStore: ctx }
    );

    const compiled = await compileContext(
      db,
      [{ role: "user", content: "What is my name and what am I working on? Answer very briefly." }],
      uid,
      { budget: 4000, contextStore: ctx }
    );
    const joined = compiled.messages.map((m) => JSON.stringify(m)).join(" ").toLowerCase();
    expect(joined).toContain("mahadi");
    expect(joined).toContain("debug");
    expect(compiled.shortTermItemsUsed).toBeGreaterThan(0);

    const res = await app.request(
      "/v1/chat/completions",
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer 1234" },
        body: JSON.stringify({
          model: LIVE_MODEL,
          messages: compiled.messages,
          max_tokens: 40,
        }),
      },
      liveEnv()
    );
    expect(res.status).toBe(200);
    const data = (await res.json()) as any;
    const answer = data.choices[0].message.content.toLowerCase();
    expect(answer).toContain("mahadi");
    await ctx.clearUser(uid);
  });
});

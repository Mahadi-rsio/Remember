import { describe, expect, it, beforeEach } from "bun:test";
import { createTestDb, createTestContextStore } from "./helpers/db";
import type { Database } from "../src/db";
import type { MemoryContextStore } from "../src/memory/context-store";
import { archiveRequest } from "../src/storage/archive";
import { listMemoryItems } from "../src/memory/state";
import { retrieveMemories } from "../src/memory/retrieve";
import { compileContext } from "../src/context/compiler";
import { MemoryStatus } from "../src/models/memory";

function userMsg(content: string): Record<string, any> {
  return { role: "user", content };
}

describe("Short-term + Long-term memory architecture", () => {
  let db: Database;
  let ctx: MemoryContextStore;

  beforeEach(async () => {
    db = await createTestDb();
    ctx = createTestContextStore();
  });

  async function archive(
    messages: Array<Record<string, any>>,
    userId = "test-user"
  ) {
    return archiveRequest(db, { messages }, { userId, contextStore: ctx });
  }

  async function active(userId: string) {
    return listMemoryItems(db, userId, MemoryStatus.ACTIVE);
  }

  async function all(userId: string) {
    return listMemoryItems(db, userId, null);
  }

  it("stores a single durable memory with structured fields", async () => {
    await archive([userMsg("My name is Mahadi")]);
    const items = await active("test-user");
    expect(items).toHaveLength(1);
    expect(items[0].content.toLowerCase()).toContain("mahadi");
    expect(items[0].subject).toBe("user");
    expect(items[0].predicate).toBe("name");
    expect(items[0].value).toBe("Mahadi");
  });

  it("produces multiple separate long-term memories from one message", async () => {
    await archive([userMsg("Remember uses Neon for its database and Cloudflare for hosting.")]);
    const items = await active("test-user");
    expect(items.length).toBeGreaterThanOrEqual(2);
    const predicates = items.map((i) => i.predicate);
    expect(predicates).toContain("database");
    expect(predicates).toContain("runtime");
  });

  it("routes temporary debugging context to short-term store, not PostgreSQL", async () => {
    await archive([userMsg("I'm currently debugging an authentication bug")]);
    const items = await all("test-user");
    expect(items).toHaveLength(0);
    const context = await ctx.getAllContext("test-user");
    expect(context.length).toBeGreaterThan(0);
    const joined = context.map((c) => c.value.toLowerCase()).join(" ");
    expect(joined).toContain("debug");
  });

  it("discards noise entirely (no store, no context)", async () => {
    await archive([userMsg("haha")]);
    expect(await all("test-user")).toHaveLength(0);
    expect(await ctx.getAllContext("test-user")).toHaveLength(0);
  });

  it("does not create a duplicate on repeat of the same fact", async () => {
    await archive([userMsg("My name is Mahadi")]);
    await archive([userMsg("My name is Mahadi")]);
    const items = await all("test-user");
    expect(items.filter((i) => i.status === MemoryStatus.ACTIVE)).toHaveLength(1);
  });

  it("updates (supersedes) a database from Neon to Turso", async () => {
    await archive([userMsg("Remember uses Neon for its database.")]);
    await archive([userMsg("We switched Remember to Turso for the database.")]);
    const items = await all("test-user");
    const activeOne = items.find((i) => i.status === MemoryStatus.ACTIVE);
    const superseded = items.find((i) => i.status === MemoryStatus.SUPERSEDED);
    expect(activeOne).toBeDefined();
    expect(superseded).toBeDefined();
    expect(activeOne!.content.toLowerCase()).toContain("turso");
    expect(superseded!.content.toLowerCase()).toContain("neon");
  });

  it("handles an explicit contradiction by superseding the old value", async () => {
    await archive([userMsg("Remember uses Neon for its database.")]);
    await archive([userMsg("Actually, we switched Remember to Postgres for the database.")]);
    const items = await all("test-user");
    const activeOne = items.find((i) => i.status === MemoryStatus.ACTIVE);
    const superseded = items.find((i) => i.status === MemoryStatus.SUPERSEDED);
    expect(activeOne?.content.toLowerCase()).toContain("postgres");
    expect(superseded?.content.toLowerCase()).toContain("neon");
  });

  it("preserves historical state rather than deleting it", async () => {
    await archive([userMsg("Remember uses Neon for its database.")]);
    await archive([userMsg("We switched Remember to Turso for the database.")]);
    const items = await all("test-user");
    const neon = items.find((i) => i.content.toLowerCase().includes("neon"));
    const turso = items.find((i) => i.content.toLowerCase().includes("turso"));
    expect(neon).toBeDefined();
    expect(turso).toBeDefined();
    expect(neon!.status).toBe(MemoryStatus.SUPERSEDED);
    expect(turso!.status).toBe(MemoryStatus.ACTIVE);
  });

  it("scopes memories correctly per user and project", async () => {
    await archive([userMsg("My name is Mahadi")], "user-a");
    await archive([userMsg("My name is Dina")], "user-b");
    const a = await active("user-a");
    const b = await active("user-b");
    expect(a[0].value).toBe("Mahadi");
    expect(b[0].value).toBe("Dina");
    expect(a[0].value).not.toBe("Dina");
  });

  it("isolates project-scoped memories", async () => {
    await archive([userMsg("Remember uses Neon for its database.")], "proj-a");
    await archive([userMsg("Cloudisy uses PostgreSQL for storage.")], "proj-b");
    const a = await active("proj-a");
    const b = await active("proj-b");
    expect(a.map((i) => i.content.toLowerCase()).join(" ")).toContain("neon");
    expect(b.map((i) => i.content.toLowerCase()).join(" ")).toContain("postgres");
    expect(a.map((i) => i.content.toLowerCase()).join(" ")).not.toContain("postgres");
  });

  it("stores short-term context with a TTL", async () => {
    await archive([userMsg("The current error is 401")]);
    const ctxEntries = await ctx.getAllContext("test-user");
    expect(ctxEntries.length).toBeGreaterThan(0);
    expect(ctxEntries[0].ttlSeconds).toBeGreaterThan(0);
  });

  it("composes both short-term context and long-term memory into the LLM prompt", async () => {
    await archive([userMsg("My name is Mahadi")]);
    await archive([userMsg("I'm currently debugging an authentication bug")]);

    const result = await compileContext(db, [
      { role: "user", content: "What's my name and what am I working on?" },
    ], "test-user", { budget: 4000, contextStore: ctx });

    const compiled = result.messages
      .map((m) => JSON.stringify(m))
      .join(" ")
      .toLowerCase();

    expect(compiled).toContain("mahadi");
    expect(compiled).toContain("debug");
    expect(result.shortTermItemsUsed).toBeGreaterThan(0);
  });

  it("retrieves active memories deterministically by predicate", async () => {
    await archive([userMsg("Remember uses Neon for its database.")]);
    const results = await retrieveMemories(db, {
      userId: "test-user",
      predicate: "database",
      status: MemoryStatus.ACTIVE,
    });
    expect(results.length).toBeGreaterThan(0);
    expect(results[0].current).toBe(true);
    expect(results[0].item.predicate).toBe("database");
  });

  it("retrieval distinguishes current vs historical state", async () => {
    await archive([userMsg("Remember uses Neon for its database.")]);
    await archive([userMsg("We switched Remember to Turso for the database.")]);

    const current = await retrieveMemories(db, {
      userId: "test-user",
      predicate: "database",
      status: MemoryStatus.ACTIVE,
    });
    const historical = await retrieveMemories(db, {
      userId: "test-user",
      predicate: "database",
      includeHistorical: true,
    });
    expect(current.filter((r) => r.current).length).toBeGreaterThan(0);
    expect(historical.some((r) => !r.current)).toBe(true);
  });

  it("context does not leak between different short-term context keys", async () => {
    await archive([userMsg("I'm currently debugging an authentication bug")]);
    const debug = await ctx.getContext("test-user", "active_debugging_context");
    expect(debug).not.toBeNull();
    expect(await ctx.getContext("test-user", "current_task")).toBeNull();
  });
});

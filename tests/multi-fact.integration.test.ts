import { describe, expect, it } from "bun:test";
import { createTestDb } from "./helpers/db";
import type { Database } from "../src/db";
import { archiveRequest } from "../src/storage/archive";
import { listMemoryItems } from "../src/memory/state";
import { compileContext } from "../src/context/compiler";
import { MemoryStatus } from "../src/models/memory";

function userMsg(content: string): Record<string, any> {
  return { role: "user", content };
}

async function archive(
  db: Database,
  messages: Array<Record<string, any>>,
  conv: string
): Promise<string> {
  const delta = await archiveRequest(db, { messages }, { "x-conversation-id": conv } as Record<string, string>);
  expect(delta).not.toBeNull();
  return (delta as any).conversationId as string;
}

async function active(db: Database, conv: string) {
  return listMemoryItems(db, conv, MemoryStatus.ACTIVE);
}

async function all(db: Database, conv: string) {
  return listMemoryItems(db, conv, null);
}

describe("Multi-fact atomic extraction", () => {
  it("persists a single atomic database fact from a uses statement", async () => {
    const db = await createTestDb();
    const conv = await archive(db, [userMsg("Remember uses Neon for its database.")], "mf-single");

    const items = await active(db, conv);
    expect(items).toHaveLength(1);
    expect(items[0].content.toLowerCase()).toContain("neon");
    expect(items[0].topicKey).toBe("project.database");
  });

  it("persists multiple atomic facts from one message", async () => {
    const db = await createTestDb();
    const conv = await archive(
      db,
      [
        userMsg(
          "I am building an AI memory gateway called Remember. It uses Cloudflare Workers with Hono, Turso as the database."
        ),
      ],
      "mf-multi"
    );

    const items = await active(db, conv);
    expect(items.length).toBeGreaterThanOrEqual(4);
    const byKey = new Map(items.map((i) => [i.topicKey, i.content.toLowerCase()]));
    expect(byKey.get("project.name")).toContain("remember");
    expect(byKey.get("project.database")).toContain("turso");
    expect(byKey.get("project.runtime")).toContain("cloudflare workers");
    expect(byKey.get("project.framework")).toContain("hono");
  });

  it("persists 6+ atomic facts from a long stack message", async () => {
    const db = await createTestDb();
    const conv = await archive(
      db,
      [
        userMsg(
          "I am building an AI memory gateway called Remember. It uses Cloudflare Workers with Hono, Turso as the database, Upstash Redis for caching, and Groq for summarization."
        ),
      ],
      "mf-long"
    );

    const items = await active(db, conv);
    expect(items.length).toBeGreaterThanOrEqual(6);
  });

  it("supersedes the old database when the stack is switched", async () => {
    const db = await createTestDb();
    const conv = await archive(db, [userMsg("Remember uses Neon for its database.")], "mf-switch");

    await archive(db, [userMsg("We switched Remember to Turso for the database.")], conv);

    const items = await all(db, conv);
    const dbFacts = items.filter((i) => i.topicKey === "project.database");
    expect(dbFacts.length).toBe(2);
    const activeDb = dbFacts.find((i) => i.status === MemoryStatus.ACTIVE);
    const superseded = dbFacts.find((i) => i.status === MemoryStatus.SUPERSEDED);
    expect(activeDb?.content.toLowerCase()).toContain("turso");
    expect(superseded?.content.toLowerCase()).toContain("neon");
  });

  it("isolates facts per conversation", async () => {
    const db = await createTestDb();
    await archive(db, [userMsg("Remember uses Neon for its database.")], "mf-proj-a");
    await archive(db, [userMsg("Cloudisy uses PostgreSQL for storage.")], "mf-proj-b");

    const a = await active(db, "mf-proj-a");
    const b = await active(db, "mf-proj-b");
    expect(a.map((i) => i.content.toLowerCase()).join(" ")).toContain("neon");
    expect(a.map((i) => i.content.toLowerCase()).join(" ")).not.toContain("postgresql");
    expect(b.map((i) => i.content.toLowerCase()).join(" ")).toContain("postgresql");
    expect(b.map((i) => i.content.toLowerCase()).join(" ")).not.toContain("neon");
  });

  it("retrieves the database fact for a wording-variant query", async () => {
    const db = await createTestDb();
    const conv = await archive(db, [userMsg("Remember uses Turso for its database.")], "mf-query");

    const result = await compileContext(db, [
      { role: "user", content: "Hey, what database does the project use?" },
    ], conv, { budget: 4000 });

    const compiled = result.messages
      .filter((m) => m.role === "system" || m.role === "user")
      .map((m) => JSON.stringify(m))
      .join(" ");
    expect(compiled.toLowerCase()).toContain("turso");
  });
});

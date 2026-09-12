import { describe, expect, it } from "bun:test";
import { createTestDb } from "./helpers/db";
import type { Database } from "../src/db";
import { archiveRequest } from "../src/storage/archive";
import { listMemoryItems } from "../src/memory/state";
import { compileContext } from "../src/context/compiler";
import { MemoryStatus } from "../src/models/memory";

function userMsg(content: string, id?: string): Record<string, any> {
  return id ? { role: "user", content, id } : { role: "user", content };
}

async function archive(
  db: Database,
  messages: Array<Record<string, any>>,
  userId: string
): Promise<void> {
  const delta = await archiveRequest(db, { messages }, { userId });
  expect(delta).not.toBeNull();
}

async function activeContents(db: Database, userId: string): Promise<string[]> {
  const items = await listMemoryItems(db, userId, MemoryStatus.ACTIVE);
  return items.map((i) => i.content);
}

function compiledText(messages: Array<Record<string, any>>): string {
  return messages.map((m) => String(m.content)).join("\n").toLowerCase();
}

describe("User Isolation Integration (real SQLite DB)", () => {
  it("never leaks memories between users", async () => {
    const db = await createTestDb();

    await archive(
      db,
      [userMsg("I am building an AI Memory Gateway called Fallback", "iso-1")],
      "user-a"
    );
    await archive(
      db,
      [userMsg("I am building a game engine called Blastwave", "iso-2")],
      "user-b"
    );

    const contentsA = await activeContents(db, "user-a");
    const contentsB = await activeContents(db, "user-b");

    expect(contentsA.some((c) => c.toLowerCase().includes("fallback"))).toBe(true);
    expect(contentsA.some((c) => c.toLowerCase().includes("blastwave"))).toBe(false);
    expect(contentsB.some((c) => c.toLowerCase().includes("blastwave"))).toBe(true);
    expect(contentsB.some((c) => c.toLowerCase().includes("fallback"))).toBe(false);
  });

  it("compiled context for user B excludes user A memory", async () => {
    const db = await createTestDb();

    await archive(
      db,
      [userMsg("The deployment target is AWS Lambda", "tgt-a")],
      "user-deploy-a"
    );
    await archive(
      db,
      [userMsg("The deployment target is Cloudflare Workers", "tgt-b")],
      "user-deploy-b"
    );

    const compiledB = await compileContext(
      db,
      [userMsg("Where do we deploy?")],
      "user-deploy-b",
      { persistSnapshot: false }
    );
    const textB = compiledText(compiledB.messages);
    expect(textB).toContain("cloudflare workers");
    expect(textB).not.toContain("aws lambda");
  });
});

describe("Memory Merge & Staleness Integration (real SQLite DB)", () => {
  it("merges near-duplicate restatements instead of creating new items", async () => {
    const db = await createTestDb();
    const userId = "user-merge";

    await archive(db, [userMsg("Cloudisy uses PostgreSQL for its database", "d1")], userId);
    await archive(db, [userMsg("Cloudisy uses PostgreSQL for its database", "d2")], userId);
    await archive(db, [userMsg("Cloudisy uses PostgreSQL for its database", "d3")], userId);

    const active = await activeContents(db, userId);
    const matching = active.filter((c) => c.toLowerCase().includes("postgresql"));
    expect(matching.length).toBe(1);

    const all = await listMemoryItems(db, userId, null);
    expect(all.length).toBe(1);
  });

  it("only the latest ACTIVE value survives conflicting updates", async () => {
    const db = await createTestDb();
    const userId = "user-stale";

    await archive(db, [userMsg("I prefer dark theme", "s1")], userId);
    await archive(db, [userMsg("Actually, I prefer light theme now", "s2")], userId);

    const active = await activeContents(db, userId);
    const text = active.join(" ").toLowerCase();
    expect(text).toContain("light");
    expect(text).not.toContain("dark");
  });

  it("keeps unrelated memories alongside corrections", async () => {
    const db = await createTestDb();
    const userId = "user-unrelated";

    await archive(db, [userMsg("The project name is Cloudisy", "u1")], userId);
    await archive(db, [userMsg("I prefer TypeScript for implementation", "u2")], userId);
    await archive(db, [userMsg("Actually, I prefer Rust now", "u3")], userId);

    const active = await activeContents(db, userId);
    const text = active.join(" ").toLowerCase();
    expect(text).toContain("cloudisy");
    expect(text).toContain("rust");
    expect(text).not.toContain("typescript");
  });
});

describe("Context Compiler Budget Integration (real SQLite DB)", () => {
  it("respects budget while preserving system and latest message with real memories", async () => {
    const db = await createTestDb();
    const userId = "user-budget";

    await archive(db, [userMsg("Cloudisy uses PostgreSQL for its database", "b1")], userId);
    await archive(db, [userMsg("I prefer TypeScript for implementation", "b2")], userId);

    const messages = [
      { role: "system", content: "You are a helpful coding assistant." },
      userMsg("What database does Cloudisy use?"),
    ];

    const compiled = await compileContext(db, messages, userId, {
      budget: 300,
      persistSnapshot: false,
    });

    expect(compiled.totalTokens).toBeLessThanOrEqual(300);
    expect(compiled.messages[compiled.messages.length - 1].content).toBe(
      "What database does Cloudisy use?"
    );
    expect(compiled.canonicalItemsUsed).toBeGreaterThan(0);
  });
});

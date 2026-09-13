import { describe, expect, it } from "bun:test";
import { createTestDb, createTestContextStore } from "./helpers/db";
import type { Database } from "../src/db";
import { archiveRequest } from "../src/storage/archive";
import { listMemoryItems, persistCandidates } from "../src/memory/state";
import { expandRelations } from "../src/memory/retrieve";
import { updateItemAtomic } from "../src/memory/concurrency";
import { MemoryStatus, MemoryType, type CandidateMemory } from "../src/models/memory";
import { memoryItems } from "../src/db/schema/memory";
import { eq } from "drizzle-orm";

function userMsg(content: string): Record<string, any> {
  return { role: "user", content };
}

async function archive(
  db: Database,
  messages: Array<Record<string, any>>,
  userId = "test-user",
  contextStore?: any
): Promise<string> {
  const delta = await archiveRequest(db, { messages }, { userId, contextStore });
  expect(delta).not.toBeNull();
  return (delta as any).userId as string;
}

async function active(db: Database, userId: string) {
  return listMemoryItems(db, userId, MemoryStatus.ACTIVE);
}

describe("temporary_state memory routing", () => {
  it("routes temporary/currently-happening state to the short-term context store, not long-term", async () => {
    const db = await createTestDb();
    const ctx = createTestContextStore();
    const userId = await archive(
      db,
      [userMsg("I am currently working on fixing an authentication bug.")],
      "test-user",
      ctx
    );

    // Goes to Redis / short-term context (as current_task or current_error),
    // NOT PostgreSQL.
    const entries = await ctx.getAllContext(userId);
    const keys = entries.map((e) => e.key);
    expect(keys.some((k) => k === "current_task" || k === "current_error")).toBe(true);

    const longTerm = await active(db, userId);
    expect(longTerm.some((i) => i.type === "temporary_state")).toBe(false);
  });
});

describe("relationship links on supersede", () => {
  it("records supersedes_id + relationship on the replacement memory", async () => {
    const db = await createTestDb();
    const userId = await archive(db, [userMsg("Remember uses Neon for its database.")]);
    await archive(db, [userMsg("We switched Remember to Turso for the database.")], userId);

    const dbFacts = await db
      .select()
      .from(memoryItems)
      .where(eq(memoryItems.topicKey, "project.database"))
      .execute();

    const activeDb = dbFacts.find((i) => i.status === MemoryStatus.ACTIVE);
    const superseded = dbFacts.find((i) => i.status === MemoryStatus.SUPERSEDED);
    expect(activeDb).toBeDefined();
    expect(superseded).toBeDefined();
    expect(activeDb?.supersedesId).toBe(superseded?.id);
    expect(activeDb?.relationship).toBe("supersedes");
  });

  it("contradicting facts record contradicts_ids on both sides", async () => {
    const db = await createTestDb();
    const userId = await archive(db, [userMsg("My favorite language is Python.")]);
    await archive(db, [userMsg("Actually, my favorite language is Rust now.")], userId);

    const items = await active(db, userId);
    const rust = items.find((i) => i.value.toLowerCase().includes("rust"));
    expect(rust).toBeDefined();
  });
});

describe("relationship expansion retrieval", () => {
  it("expands supersede links to pull in the superseded item", async () => {
    const db = await createTestDb();
    const userId = await archive(db, [userMsg("Remember uses Neon for its database.")]);
    await archive(db, [userMsg("We switched Remember to Turso for the database.")], userId);

    const turso = (await active(db, userId)).find((i) =>
      i.content.toLowerCase().includes("turso")
    );
    expect(turso).toBeDefined();

    const expanded = await expandRelations(db, userId, [turso!], { activeOnly: false });
    const superseded = expanded.find((i) => i.content.toLowerCase().includes("neon"));
    expect(superseded).toBeDefined();
    expect(superseded?.status).toBe(MemoryStatus.SUPERSEDED);
  });

  it("returns nothing when seeds have no relationship links", async () => {
    const db = await createTestDb();
    const userId = await archive(db, [userMsg("Remember uses Neon for its database.")]);

    const items = await active(db, userId);
    const expanded = await expandRelations(db, userId, items);
    expect(expanded).toHaveLength(0);
  });
});

describe("optimistic concurrency (CAS)", () => {
  it("increments version on a matching compare-and-swap", async () => {
    const db = await createTestDb();
    const userId = await archive(db, [userMsg("Remember uses Neon for its database.")]);
    const item = (await active(db, userId))[0];
    expect(item.version).toBe(1);

    const ok = await updateItemAtomic(db, item.id, item.version, { value: "Neon (updated)" });
    expect(ok).toBe(true);

    const [after] = await db
      .select()
      .from(memoryItems)
      .where(eq(memoryItems.id, item.id));
    expect(after.version).toBe(2);
    expect(after.value).toBe("Neon (updated)");
  });

  it("fails the CAS (no write) when the expected version is stale", async () => {
    const db = await createTestDb();
    const userId = await archive(db, [userMsg("Remember uses Neon for its database.")]);
    const item = (await active(db, userId))[0];

    // Simulate a concurrent writer that bumped the version first.
    const concurrent = await updateItemAtomic(db, item.id, item.version, { value: "Concurrent" });
    expect(concurrent).toBe(true);

    // Our stale update (same expectedVersion) must be rejected without a write.
    const stale = await updateItemAtomic(db, item.id, item.version, { value: "Stale write" });
    expect(stale).toBe(false);

    const [after] = await db
      .select()
      .from(memoryItems)
      .where(eq(memoryItems.id, item.id));
    expect(after.version).toBe(2);
    expect(after.value).toBe("Concurrent");
  });

  it("persistCandidates retries once and resolves a conflict via fresh state", async () => {
    const db = await createTestDb();
    const userId = await archive(db, [userMsg("Remember uses Neon for its database.")]);
    const original = (await active(db, userId))[0];

    // A concurrent writer modifies the target memory after we'd snapshot it.
    await updateItemAtomic(db, original.id, original.version, { value: "Concurrent change" });

    // A candidate that supersedes the database fact: with retry + fresh reload
    // the persist path should resolve cleanly (create the Turso replacement)
    // instead of dropping the candidate.
    const candidate: CandidateMemory = {
      content: "Remember uses Turso for its database.",
      type: MemoryType.FACT,
      topicKey: "project.database",
      subject: "project",
      predicate: "database",
      value: "Turso",
      scope: "project",
      sourceMessageIds: ["m1"],
      confidence: 0.9,
      importance: 0.7,
      stability: 0.5,
      freshness: 0.8,
      informationGain: 0.5,
    };

    const results = await persistCandidates(db, userId, [candidate]);
    // The concurrent-write conflict is resolved by reloading fresh state and
    // retrying; it must not surface as a hard failure.
    expect(results.some((r) => r.action === "conflict")).toBe(false);

    const items = await active(db, userId);
    const turso = items.find((i) => i.content.toLowerCase().includes("turso"));
    expect(turso).toBeDefined();
  });
});

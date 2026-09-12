import { describe, expect, it } from "bun:test";
import { createTestDb } from "./helpers/db";
import type { Database } from "../src/db";
import { archiveRequest, persistNewMessages } from "../src/storage/archive";
import { detectDelta } from "../src/memory/delta";
import { listMemoryItems } from "../src/memory/state";
import { MemoryStatus } from "../src/models/memory";
import { normalizeMessages } from "../src/memory/ids";
import { users as usersTable } from "../src/db/schema/users";

function userMsg(content: string, id?: string): Record<string, any> {
  return id ? { role: "user", content, id } : { role: "user", content };
}

async function archive(
  db: Database,
  messages: Array<Record<string, any>>,
  userId = "test-user"
): Promise<string> {
  const body = { messages };
  const delta = await archiveRequest(db, body, { userId });
  expect(delta).not.toBeNull();
  return (delta as any).userId as string;
}

async function activeContents(db: Database, userId: string): Promise<string[]> {
  const items = await listMemoryItems(db, userId, MemoryStatus.ACTIVE);
  return items.map((i) => i.content);
}

describe("Archive + Delta Integration (real SQLite DB)", () => {
  it("persists new messages and re-identifies them as duplicates on retry", async () => {
    const db = await createTestDb();
    const userId = "test-user";
    const messages = [userMsg("Cloudisy uses PostgreSQL for storage", "m1")];

    await db
      .insert(usersTable)
      .values({ userId, apiKey: "1234", createdAt: new Date().toISOString() })
      .onConflictDoNothing()
      .returning();

    const delta1 = await detectDelta(db, userId, null, messages);
    expect(delta1.newMessages).toHaveLength(1);

    await persistNewMessages(db, userId, delta1.newMessages);

    const delta2 = await detectDelta(db, userId, null, messages);
    expect(delta2.newMessages).toHaveLength(0);
    expect(delta2.duplicateMessages).toHaveLength(1);
  });

  it("stores only meaningful facts and skips low-info affirmations", async () => {
    const db = await createTestDb();
    const userId = await archive(
      db,
      [
        userMsg("ok"),
        userMsg("thanks a lot"),
        userMsg("I am building an AI Memory Gateway called Remember"),
      ]
    );

    const contents = await activeContents(db, userId);
    expect(contents).toHaveLength(1);
    expect(contents[0].toLowerCase()).toContain("remember");
  });

  it("does not create memory from pure questions", async () => {
    const db = await createTestDb();
    const userId = await archive(
      db,
      [
        userMsg("What is my name?"),
        userMsg("Why did we choose PostgreSQL?"),
        userMsg("Where is the project deployed?"),
      ]
    );

    const contents = await activeContents(db, userId);
    expect(contents).toHaveLength(0);
  });

  it("persists messages into the raw archive even when memory engine runs", async () => {
    const db = await createTestDb();
    const userId = await archive(db, [userMsg("We decided to use Drizzle ORM", "m-raw")]);

    const delta = await detectDelta(db, userId, null, [userMsg("We decided to use Drizzle ORM", "m-raw")]);
    expect(delta.duplicateMessages).toHaveLength(1);
  });
});

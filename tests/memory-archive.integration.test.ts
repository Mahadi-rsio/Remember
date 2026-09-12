import { describe, expect, it } from "bun:test";
import { createTestDb } from "./helpers/db";
import type { Database } from "../src/db";
import { archiveRequest, persistNewMessages } from "../src/storage/archive";
import { detectDelta } from "../src/memory/delta";
import { listMemoryItems } from "../src/memory/state";
import { MemoryStatus } from "../src/models/memory";
import { normalizeMessages } from "../src/memory/ids";
import { conversations as conversationsTable } from "../src/db/schema/conversations";

function userMsg(content: string, id?: string): Record<string, any> {
  return id ? { role: "user", content, id } : { role: "user", content };
}

async function archive(
  db: Database,
  messages: Array<Record<string, any>>,
  conv?: string
): Promise<string> {
  const body = { messages };
  const delta = await archiveRequest(db, body, { "x-conversation-id": conv } as Record<string, string>);
  expect(delta).not.toBeNull();
  return (delta as any).conversationId as string;
}

async function activeContents(db: Database, conv: string): Promise<string[]> {
  const items = await listMemoryItems(db, conv, MemoryStatus.ACTIVE);
  return items.map((i) => i.content);
}

describe("Archive + Delta Integration (real SQLite DB)", () => {
  it("persists new messages and re-identifies them as duplicates on retry", async () => {
    const db = await createTestDb();
    const conv = "conv-delta-1";
    const messages = [userMsg("Cloudisy uses PostgreSQL for storage", "m1")];

    await db
      .insert(conversationsTable)
      .values({ id: conv, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() })
      .run();

    const delta1 = await detectDelta(db, conv, null, messages);
    expect(delta1.newMessages).toHaveLength(1);

    await persistNewMessages(db, conv, delta1.newMessages);

    const delta2 = await detectDelta(db, conv, null, messages);
    expect(delta2.newMessages).toHaveLength(0);
    expect(delta2.duplicateMessages).toHaveLength(1);
  });

  it("stores only meaningful facts and skips low-info affirmations", async () => {
    const db = await createTestDb();
    const conv = await archive(
      db,
      [
        userMsg("ok"),
        userMsg("thanks a lot"),
        userMsg("I am building an AI Memory Gateway called Remember"),
      ],
      "conv-lowinfo"
    );

    const contents = await activeContents(db, conv);
    expect(contents).toHaveLength(1);
    expect(contents[0].toLowerCase()).toContain("remember");
  });

  it("does not create memory from pure questions", async () => {
    const db = await createTestDb();
    const conv = await archive(
      db,
      [
        userMsg("What is my name?"),
        userMsg("Why did we choose PostgreSQL?"),
        userMsg("Where is the project deployed?"),
      ],
      "conv-questions"
    );

    const contents = await activeContents(db, conv);
    expect(contents).toHaveLength(0);
  });

  it("persists messages into the raw archive even when memory engine runs", async () => {
    const db = await createTestDb();
    const conv = await archive(db, [userMsg("We decided to use Drizzle ORM", "m-raw")], "conv-raw");

    const delta = await detectDelta(db, conv, null, [userMsg("We decided to use Drizzle ORM", "m-raw")]);
    expect(delta.duplicateMessages).toHaveLength(1);
  });
});

import { describe, expect, it } from "bun:test";
import { createTestDb } from "./helpers/db";
import type { Database } from "../src/db";
import { archiveRequest } from "../src/storage/archive";
import { listMemoryItems, latestContextVersion } from "../src/memory/state";
import { compileContext } from "../src/context/compiler";
import { MemoryStatus } from "../src/models/memory";
import { corrections as correctionsTable } from "../src/db/schema/corrections";
import { contextVersions } from "../src/db/schema/context";
import { eq } from "drizzle-orm";

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

async function itemsByStatus(db: Database, userId: string, status: string) {
  return await listMemoryItems(db, userId, status as MemoryStatus);
}

async function contentsByStatus(db: Database, userId: string, status: string): Promise<string[]> {
  const items = await itemsByStatus(db, userId, status);
  return items.map((i) => i.content);
}

async function activeContents(db: Database, userId: string): Promise<string[]> {
  return await contentsByStatus(db, userId, MemoryStatus.ACTIVE);
}

function compiledText(messages: Array<Record<string, any>>): string {
  return messages.map((m) => String(m.content)).join("\n").toLowerCase();
}

describe("Correction Semantics Integration (real SQLite DB)", () => {
  it("supersedes old fact when user corrects the database choice", async () => {
    const db = await createTestDb();
    const userId = "user-corr-db";

    await archive(db, [userMsg("Cloudisy uses Neon for database", "c1")], userId);
    expect(
      (await activeContents(db, userId)).some((c) => c.toLowerCase().includes("neon"))
    ).toBe(true);

    await archive(db, [userMsg("Actually, Cloudisy uses self-hosted PostgreSQL", "c2")], userId);

    const active = await activeContents(db, userId);
    const superseded = await contentsByStatus(db, userId, MemoryStatus.SUPERSEDED);

    expect(active.some((c) => c.toLowerCase().includes("postgresql"))).toBe(true);
    expect(active.some((c) => c.toLowerCase().includes("neon"))).toBe(false);
    expect(superseded.some((c) => c.toLowerCase().includes("neon"))).toBe(true);

    const corrRows = await db
      .select()
      .from(correctionsTable)
      .where(eq(correctionsTable.userId, userId));
    expect(corrRows.length).toBeGreaterThan(0);
    expect(corrRows[0].oldValue.toLowerCase()).toContain("neon");
    expect(corrRows[0].newValue.toLowerCase()).toContain("postgresql");
  });

  it("supersedes preference contradiction (React -> Vue)", async () => {
    const db = await createTestDb();
    const userId = "user-corr-pref";

    await archive(db, [userMsg("I prefer React for frontend work", "p1")], userId);
    await archive(db, [userMsg("Actually, I prefer Vue now", "p2")], userId);

    const active = await activeContents(db, userId);
    const superseded = await contentsByStatus(db, userId, MemoryStatus.SUPERSEDED);

    expect(active.filter((c) => c.toLowerCase().includes("vue")).length).toBeGreaterThan(0);
    expect(active.filter((c) => c.toLowerCase() === "react").length).toBe(0);
    expect(superseded.length).toBeGreaterThan(0);
  });

  it("compiled context surfaces only the corrected value and bumps context version", async () => {
    const db = await createTestDb();
    const userId = "user-corr-compile";

    await archive(db, [userMsg("Cloudisy uses Neon for database", "k1")], userId);
    const versionBefore = await latestContextVersion(db, userId);

    await archive(db, [userMsg("Actually, Cloudisy uses self-hosted PostgreSQL", "k2")], userId);
    const versionAfter = await latestContextVersion(db, userId);
    expect(versionAfter).toBeGreaterThan(versionBefore);

    const compiled = await compileContext(
      db,
      [userMsg("What database does Cloudisy use?")],
      userId,
      { persistSnapshot: false }
    );
    const text = compiledText(compiled.messages);
    expect(text).toContain("postgresql");
    expect(text).not.toContain("neon");

    const snapshots = await db
      .select()
      .from(contextVersions)
      .where(eq(contextVersions.userId, userId));
    expect(snapshots.length).toBeGreaterThanOrEqual(2);
  });

  it("correction without matching old fact still stores the corrected value", async () => {
    const db = await createTestDb();
    const userId = "user-corr-orphan";

    await archive(db, [userMsg("Actually, the deployment was changed to AWS Lambda", "o1")], userId);

    const active = await activeContents(db, userId);
    expect(active.some((c) => c.toLowerCase().includes("aws lambda"))).toBe(true);
  });
});

describe("Revocation Semantics Integration (real SQLite DB)", () => {
  it("revokes stored secret after reset and excludes it from compiled context", async () => {
    const db = await createTestDb();
    const userId = "user-revoke-1";

    await archive(db, [userMsg("The temporary password is temp1234", "r1")], userId);
    expect(
      (await activeContents(db, userId)).some((c) => c.includes("temp1234"))
    ).toBe(true);

    await archive(db, [userMsg("The password was reset; ignore temp1234", "r2")], userId);

    const active = await activeContents(db, userId);
    const revoked = await contentsByStatus(db, userId, MemoryStatus.REVOKED);

    expect(active.some((c) => c.includes("temp1234"))).toBe(false);
    expect(revoked.some((c) => c.includes("temp1234"))).toBe(true);

    const compiled = await compileContext(
      db,
      [userMsg("What is the temporary password?")],
      userId,
      { persistSnapshot: false }
    );
    expect(compiledText(compiled.messages)).not.toContain("temp1234");
  });

  it("revoked items remain in the raw archive for auditability", async () => {
    const db = await createTestDb();
    const userId = "user-revoke-2";

    await archive(db, [userMsg("The temporary password is temp1234", "r1")], userId);
    await archive(db, [userMsg("The password was reset; ignore temp1234", "r2")], userId);

    const all = await listMemoryItems(db, userId, null);
    expect(all.some((i) => i.content.includes("temp1234"))).toBe(true);
  });
});

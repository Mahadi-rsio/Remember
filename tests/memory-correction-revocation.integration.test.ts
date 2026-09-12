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
  conv: string
): Promise<void> {
  const delta = await archiveRequest(db, { messages }, {
    "x-conversation-id": conv,
  } as Record<string, string>);
  expect(delta).not.toBeNull();
}

async function itemsByStatus(db: Database, conv: string, status: string) {
  return await listMemoryItems(db, conv, status as MemoryStatus);
}

async function contentsByStatus(db: Database, conv: string, status: string): Promise<string[]> {
  const items = await itemsByStatus(db, conv, status);
  return items.map((i) => i.content);
}

async function activeContents(db: Database, conv: string): Promise<string[]> {
  return await contentsByStatus(db, conv, MemoryStatus.ACTIVE);
}

function compiledText(messages: Array<Record<string, any>>): string {
  return messages.map((m) => String(m.content)).join("\n").toLowerCase();
}

describe("Correction Semantics Integration (real SQLite DB)", () => {
  it("supersedes old fact when user corrects the database choice", async () => {
    const db = await createTestDb();
    const conv = "conv-corr-db";

    await archive(db, [userMsg("Cloudisy uses Neon for database", "c1")], conv);
    expect(
      (await activeContents(db, conv)).some((c) => c.toLowerCase().includes("neon"))
    ).toBe(true);

    await archive(db, [userMsg("Actually, Cloudisy uses self-hosted PostgreSQL", "c2")], conv);

    const active = await activeContents(db, conv);
    const superseded = await contentsByStatus(db, conv, MemoryStatus.SUPERSEDED);

    expect(active.some((c) => c.toLowerCase().includes("postgresql"))).toBe(true);
    expect(active.some((c) => c.toLowerCase().includes("neon"))).toBe(false);
    expect(superseded.some((c) => c.toLowerCase().includes("neon"))).toBe(true);

    const corrRows = await db
      .select()
      .from(correctionsTable)
      .where(eq(correctionsTable.conversationId, conv));
    expect(corrRows.length).toBeGreaterThan(0);
    expect(corrRows[0].oldValue.toLowerCase()).toContain("neon");
    expect(corrRows[0].newValue.toLowerCase()).toContain("postgresql");
  });

  it("supersedes preference contradiction (React -> Vue)", async () => {
    const db = await createTestDb();
    const conv = "conv-corr-pref";

    await archive(db, [userMsg("I prefer React for frontend work", "p1")], conv);
    await archive(db, [userMsg("Actually, I prefer Vue now", "p2")], conv);

    const active = await activeContents(db, conv);
    const superseded = await contentsByStatus(db, conv, MemoryStatus.SUPERSEDED);

    expect(active.filter((c) => c.toLowerCase().includes("vue")).length).toBeGreaterThan(0);
    expect(active.filter((c) => c.toLowerCase() === "react").length).toBe(0);
    expect(superseded.length).toBeGreaterThan(0);
  });

  it("compiled context surfaces only the corrected value and bumps context version", async () => {
    const db = await createTestDb();
    const conv = "conv-corr-compile";

    await archive(db, [userMsg("Cloudisy uses Neon for database", "k1")], conv);
    const versionBefore = await latestContextVersion(db, conv);

    await archive(db, [userMsg("Actually, Cloudisy uses self-hosted PostgreSQL", "k2")], conv);
    const versionAfter = await latestContextVersion(db, conv);
    expect(versionAfter).toBeGreaterThan(versionBefore);

    const compiled = await compileContext(
      db,
      [userMsg("What database does Cloudisy use?")],
      conv,
      { persistSnapshot: false }
    );
    const text = compiledText(compiled.messages);
    expect(text).toContain("postgresql");
    expect(text).not.toContain("neon");

    const snapshots = await db
      .select()
      .from(contextVersions)
      .where(eq(contextVersions.conversationId, conv));
    expect(snapshots.length).toBeGreaterThanOrEqual(2);
  });

  it("correction without matching old fact still stores the corrected value", async () => {
    const db = await createTestDb();
    const conv = "conv-corr-orphan";

    await archive(db, [userMsg("Actually, the deployment was changed to AWS Lambda", "o1")], conv);

    const active = await activeContents(db, conv);
    expect(active.some((c) => c.toLowerCase().includes("aws lambda"))).toBe(true);
  });
});

describe("Revocation Semantics Integration (real SQLite DB)", () => {
  it("revokes stored secret after reset and excludes it from compiled context", async () => {
    const db = await createTestDb();
    const conv = "conv-revoke-1";

    await archive(db, [userMsg("The temporary password is temp1234", "r1")], conv);
    expect(
      (await activeContents(db, conv)).some((c) => c.includes("temp1234"))
    ).toBe(true);

    await archive(db, [userMsg("The password was reset; ignore temp1234", "r2")], conv);

    const active = await activeContents(db, conv);
    const revoked = await contentsByStatus(db, conv, MemoryStatus.REVOKED);

    expect(active.some((c) => c.includes("temp1234"))).toBe(false);
    expect(revoked.some((c) => c.includes("temp1234"))).toBe(true);

    const compiled = await compileContext(
      db,
      [userMsg("What is the temporary password?")],
      conv,
      { persistSnapshot: false }
    );
    expect(compiledText(compiled.messages)).not.toContain("temp1234");
  });

  it("revoked items remain in the raw archive for auditability", async () => {
    const db = await createTestDb();
    const conv = "conv-revoke-2";

    await archive(db, [userMsg("The temporary password is temp1234", "r1")], conv);
    await archive(db, [userMsg("The password was reset; ignore temp1234", "r2")], conv);

    const all = await listMemoryItems(db, conv, null);
    expect(all.some((i) => i.content.includes("temp1234"))).toBe(true);
  });
});

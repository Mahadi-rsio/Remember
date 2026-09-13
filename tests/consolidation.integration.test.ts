import { describe, expect, it, beforeEach } from "bun:test";
import { createTestDb, createTestContextStore } from "./helpers/db";
import type { Database } from "../src/db";
import type { MemoryContextStore } from "../src/memory/context-store";
import { archiveRequest } from "../src/storage/archive";
import { listMemoryItems } from "../src/memory/state";
import { compileContext } from "../src/context/compiler";
import { MemoryStatus } from "../src/models/memory";
import { runConsolidationPass } from "../src/memory/consolidator";

function userMsg(content: string): Record<string, any> {
  return { role: "user", content };
}

describe("Memory consolidation persistence", () => {
  let db: Database;
  let ctx: MemoryContextStore;

  beforeEach(async () => {
    db = await createTestDb();
    ctx = createTestContextStore();
  });

  async function archive(content: string, userId = "test-user") {
    return archiveRequest(db, { messages: [userMsg(content)] }, { userId, contextStore: ctx });
  }

  it("consolidates multiple stack preferences into one architecture memory", async () => {
    await archive("I prefer TypeScript");
    await archive("I prefer Neon over PlanetScale");
    await archive("I prefer Cloudflare Workers");
    await archive("I prefer Hono");

    // Explicit pass in case per-message clustering ran early with <3 items.
    await runConsolidationPass(db, "test-user");

    const active = await listMemoryItems(db, "test-user", MemoryStatus.ACTIVE);
    const stack = active.filter((i) => i.topicKey === "user.tech_stack");
    expect(stack.length).toBeGreaterThanOrEqual(1);
    expect(stack[0].type).toBe("architecture");
    expect(stack[0].predicate).toBe("tech_stack");

    const value = JSON.parse(stack[0].value);
    expect(value.language?.toLowerCase()).toContain("typescript");
    expect(String(value.database || "").toLowerCase()).toContain("neon");

    const superseded = await listMemoryItems(db, "test-user", MemoryStatus.SUPERSEDED);
    expect(superseded.length).toBeGreaterThanOrEqual(3);

    const compiled = await compileContext(
      db,
      [{ role: "user", content: "What is my tech stack?" }],
      "test-user",
      { persistSnapshot: false, contextStore: ctx }
    );
    const text = compiled.messages.map((m) => String(m.content)).join("\n").toLowerCase();
    expect(text).toContain("typescript");
    expect(text).toContain("neon");
  });
});

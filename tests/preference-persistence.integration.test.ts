import { describe, expect, it, beforeEach } from "bun:test";
import { createTestDb, createTestContextStore } from "./helpers/db";
import type { Database } from "../src/db";
import type { MemoryContextStore } from "../src/memory/context-store";
import { archiveRequest } from "../src/storage/archive";
import { listMemoryItems } from "../src/memory/state";
import { compileContext } from "../src/context/compiler";
import { MemoryStatus } from "../src/models/memory";
import { extractKeywords } from "../src/context/selector";

function userMsg(content: string): Record<string, any> {
  return { role: "user", content };
}

describe("Preference promotion to long-term memory", () => {
  let db: Database;
  let ctx: MemoryContextStore;

  beforeEach(async () => {
    db = await createTestDb();
    ctx = createTestContextStore();
  });

  async function archive(messages: Array<Record<string, any>>, userId = "test-user") {
    return archiveRequest(db, { messages }, { userId, contextStore: ctx });
  }

  async function active(userId = "test-user") {
    return listMemoryItems(db, userId, MemoryStatus.ACTIVE);
  }

  async function all(userId = "test-user") {
    return listMemoryItems(db, userId, null);
  }

  it('persists "I love red" as user.favorite_color', async () => {
    await archive([userMsg("I love red")]);
    const items = await active();
    expect(items).toHaveLength(1);
    expect(items[0].subject).toBe("user");
    expect(items[0].predicate).toBe("favorite_color");
    expect(items[0].value).toBe("red");
    expect(items[0].status).toBe(MemoryStatus.ACTIVE);
    expect(items[0].type).toBe("preference");
  });

  it("recalls favourite colour spelling via compiled context", async () => {
    await archive([userMsg("I love red")]);
    const compiled = await compileContext(
      db,
      [{ role: "user", content: "What is my favourite color?" }],
      "test-user",
      { persistSnapshot: false, contextStore: ctx }
    );
    const text = compiled.messages.map((m) => String(m.content)).join("\n").toLowerCase();
    expect(text).toContain("red");
    expect(compiled.canonicalItemsUsed).toBeGreaterThan(0);
  });

  it('does not store "I love this response"', async () => {
    await archive([userMsg("I love this response")]);
    expect(await all()).toHaveLength(0);
    expect(await ctx.getAllContext("test-user")).toHaveLength(0);
  });

  it('supersedes red with "I love blue now"', async () => {
    await archive([userMsg("I love red")]);
    await archive([userMsg("I love blue now")]);

    const items = await all();
    const activeItems = items.filter((i) => i.status === MemoryStatus.ACTIVE);
    const superseded = items.filter((i) => i.status === MemoryStatus.SUPERSEDED);

    expect(activeItems).toHaveLength(1);
    expect(activeItems[0].value).toBe("blue");
    expect(activeItems[0].predicate).toBe("favorite_color");
    expect(superseded.length).toBeGreaterThanOrEqual(1);
    expect(superseded.some((i) => i.value === "red")).toBe(true);
    expect(activeItems[0].supersedesId).toBeTruthy();

    const compiled = await compileContext(
      db,
      [{ role: "user", content: "What is my favourite colour?" }],
      "test-user",
      { persistSnapshot: false, contextStore: ctx }
    );
    const text = compiled.messages.map((m) => String(m.content)).join("\n").toLowerCase();
    expect(text).toContain("blue");
    expect(text).not.toContain("red");
  });

  it("normalizes favourite/colour keywords for retrieval overlap", () => {
    const keys = extractKeywords("What is my favourite colour?");
    expect(keys.has("favorite")).toBe(true);
    expect(keys.has("color")).toBe(true);
    expect(keys.has("favourite")).toBe(false);
    expect(keys.has("colour")).toBe(false);
  });
});

import { describe, expect, it } from "bun:test";
import {
  MemoryContextStore,
  RedisContextStore,
  createContextStore,
} from "../src/memory/context-store";

describe("MemoryContextStore (in-memory)", () => {
  it("sets and reads a context value", async () => {
    const store = new MemoryContextStore();
    await store.setContext("u1", "current_task", "fixing auth", 3600);
    expect(await store.getContext("u1", "current_task")).toBe("fixing auth");
  });

  it("returns null for a missing key", async () => {
    const store = new MemoryContextStore();
    expect(await store.getContext("u1", "missing")).toBeNull();
  });

  it("expires entries after their TTL", async () => {
    const store = new MemoryContextStore();
    await store.setContext("u1", "current_error", "401", 0.01); // 10ms
    expect(await store.getContext("u1", "current_error")).toBe("401");
    await new Promise((r) => setTimeout(r, 30));
    expect(await store.getContext("u1", "current_error")).toBeNull();
  });

  it("lists all live context entries", async () => {
    const store = new MemoryContextStore();
    await store.setContext("u1", "current_task", "build x", 3600);
    await store.setContext("u1", "current_error", "401", 3600);
    const all = await store.getAllContext("u1");
    expect(all.map((e) => e.key).sort()).toEqual([
      "current_error",
      "current_task",
    ]);
  });

  it("isolates context per user", async () => {
    const store = new MemoryContextStore();
    await store.setContext("u1", "current_task", "a", 3600);
    await store.setContext("u2", "current_task", "b", 3600);
    expect(await store.getContext("u1", "current_task")).toBe("a");
    expect(await store.getContext("u2", "current_task")).toBe("b");
  });

  it("deletes a single key", async () => {
    const store = new MemoryContextStore();
    await store.setContext("u1", "k", "v", 3600);
    await store.deleteContext("u1", "k");
    expect(await store.getContext("u1", "k")).toBeNull();
  });

  it("clears a user", async () => {
    const store = new MemoryContextStore();
    await store.setContext("u1", "k", "v", 3600);
    await store.clearUser("u1");
    expect(await store.getContext("u1", "k")).toBeNull();
  });
});

describe("RedisContextStore", () => {
  function fakeRedis() {
    const hash = new Map<string, Record<string, string>>();
    return {
      redis: {
        async get(_k: string) {
          return null;
        },
        async set(_k: string, _v: string) {
          return null;
        },
        async hgetall(key: string) {
          return hash.get(key) ?? null;
        },
        async hset(key: string, data: Record<string, string>) {
          hash.set(key, { ...(hash.get(key) || {}), ...data });
        },
        async hdel(key: string, ...fields: string[]) {
          const m = hash.get(key);
          if (m) {
            for (const f of fields) delete m[f];
          }
        },
        async del(key: string) {
          hash.delete(key);
        },
      },
    };
  }

  it("stores and reads a context value via Redis", async () => {
    const { redis } = fakeRedis();
    const store = new RedisContextStore(redis as any);
    await store.setContext("u1", "current_task", "auth", 3600);
    expect(await store.getContext("u1", "current_task")).toBe("auth");
  });

  it("returns null for missing Redis value", async () => {
    const { redis } = fakeRedis();
    const store = new RedisContextStore(redis as any);
    expect(await store.getContext("u1", "nope")).toBeNull();
  });

  it("createContextStore returns memory store when redis is null", () => {
    const store = createContextStore(null);
    expect(store).toBeInstanceOf(MemoryContextStore);
  });
});

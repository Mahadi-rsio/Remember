import { describe, expect, it } from "bun:test";
import { createTestDb } from "./helpers/db";
import type { Database } from "../src/db";
import { archiveRequest } from "../src/storage/archive";
import { compileContext } from "../src/context/compiler";
import { userIdForApiKey } from "../src/auth/identity";

const USER_ID = "test-user";

describe("User Memory Persistence Across Independent Requests (Neon PostgreSQL)", () => {
  it("persists memory under the API-key-derived user and recalls it in a separate request with no conversation/session ID", async () => {
    const db = await createTestDb();

    // Resolve user from the hardcoded API key (the real auth seam).
    expect(userIdForApiKey("1234")).toBe(USER_ID);

    // Request 1: archive a fact. No conversation_id, session_id, or thread_id.
    const archiveDelta = await archiveRequest(
      db,
      {
        messages: [
          { role: "user", content: "Remember uses Neon PostgreSQL for its database" },
        ],
      },
      { userId: USER_ID }
    );
    expect(archiveDelta).not.toBeNull();

    // Request 2: a completely independent request (fresh context compile).
    // Same user, but no conversational identifier is passed anywhere.
    const compiled = await compileContext(
      db,
      [{ role: "user", content: "What database does Remember use?" }],
      USER_ID,
      { persistSnapshot: false }
    );

    const text = compiled.messages.map((m) => String(m.content)).join("\n").toLowerCase();
    expect(text).toContain("neon postgresql");
    expect(compiled.canonicalItemsUsed).toBeGreaterThan(0);
  });

  it("scopes persistence to the user: other users never see the remembered fact", async () => {
    const db = await createTestDb();

    await archiveRequest(
      db,
      {
        messages: [
          { role: "user", content: "Remember uses Neon PostgreSQL for its database" },
        ],
      },
      { userId: USER_ID }
    );

    const otherCompiled = await compileContext(
      db,
      [{ role: "user", content: "What database does Remember use?" }],
      "some-other-user",
      { persistSnapshot: false }
    );

    const text = otherCompiled.messages.map((m) => String(m.content)).join("\n").toLowerCase();
    expect(text).not.toContain("neon postgresql");
  });
});

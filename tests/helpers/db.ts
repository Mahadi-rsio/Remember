import { neon } from "@neondatabase/serverless";
import { drizzle } from "drizzle-orm/neon-http";
import * as schema from "../../src/db/schema";
import type { Database as AppDatabase } from "../../src/db";
import { users } from "../../src/db/schema/users";
import { messages } from "../../src/db/schema/messages";
import { memoryItems } from "../../src/db/schema/memory";
import { contextVersions } from "../../src/db/schema/context";
import { corrections } from "../../src/db/schema/corrections";

const TABLES = [users, messages, memoryItems, contextVersions, corrections];

const TABLE_NAME = Symbol.for("drizzle:Name");

function tableName(table: typeof users): string {
  return (table as any)[TABLE_NAME];
}

/**
 * Creates a connection to the Neon test database (DATABASE_URL), wrapped in a
 * Drizzle instance compatible with the memory engine. Each call truncates all
 * tables first so every test starts isolated. Requires a live Neon test DB
 * with the production schema already applied (see scripts/migrate.ts).
 */
export async function createTestDb(): Promise<AppDatabase> {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is required to run integration tests. Point it at a Neon test database."
    );
  }

  const sql = neon(url);
  const db = drizzle(sql, { schema }) as unknown as AppDatabase;

  for (const table of TABLES) {
    await db.execute(
      `TRUNCATE TABLE "${tableName(table)}" RESTART IDENTITY CASCADE`
    );
  }

  return db;
}

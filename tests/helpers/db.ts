import { Database } from "bun:sqlite";
import { drizzle as drizzleBun } from "drizzle-orm/bun-sqlite";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import * as schema from "../../src/db/schema";
import type { Database as AppDatabase } from "../../src/db";

const MIGRATION_PATH = resolve(__dirname, "../../drizzle/0000_powerful_nemesis.sql");

function applyMigration(sqlite: Database): void {
  const sql = readFileSync(MIGRATION_PATH, "utf-8");
  const statements = sql
    .split("--> statement-breakpoint")
    .map((s) => s.trim())
    .filter(Boolean);

  for (const stmt of statements) {
    sqlite.exec(stmt);
  }
}

/**
 * Creates a real in-memory SQLite database with the production D1 schema
 * applied, wrapped in a Drizzle instance compatible with the memory engine.
 * Each call returns an isolated, fully-writable database.
 */
export function createTestDb(): AppDatabase {
  const sqlite = new Database(":memory:");
  applyMigration(sqlite);
  sqlite.exec("PRAGMA foreign_keys = ON");
  return drizzleBun(sqlite, { schema }) as unknown as AppDatabase;
}

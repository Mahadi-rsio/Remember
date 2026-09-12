#!/usr/bin/env bun
/**
 * Apply Drizzle SQL migrations to Turso / libSQL.
 * Loads credentials from .dev.vars (local) or process.env.
 */
import { config } from "dotenv";
import { createClient } from "@libsql/client";
import { drizzle } from "drizzle-orm/libsql";
import { migrate } from "drizzle-orm/libsql/migrator";

config({ path: ".dev.vars" });

const url = process.env.TURSO_DATABASE_URL;
if (!url) {
  console.error("TURSO_DATABASE_URL is required (set in .dev.vars or env)");
  process.exit(1);
}

const client = createClient({
  url,
  authToken: process.env.TURSO_AUTH_TOKEN,
});

const db = drizzle(client);

console.log(`Migrating ${url} ...`);
await migrate(db, { migrationsFolder: "./drizzle" });
console.log("Migrations applied.");

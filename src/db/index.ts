import { neon } from "@neondatabase/serverless";
import { drizzle } from "drizzle-orm/neon-http";
import * as schema from "./schema";
import type { Env } from "../env";

export * from "./schema";

type AppDatabase = ReturnType<typeof drizzle<typeof schema>>;

let cached:
  | {
      url: string;
      db: AppDatabase;
    }
  | null = null;

export function getDb(env: Env) {
  if (!env.DATABASE_URL) {
    throw new Error("DATABASE_URL is not configured");
  }

  if (cached && cached.url === env.DATABASE_URL) {
    return cached.db;
  }

  const sql = neon(env.DATABASE_URL);
  const db = drizzle(sql, { schema });
  cached = { url: env.DATABASE_URL, db };
  return db;
}

export type Database = ReturnType<typeof getDb>;

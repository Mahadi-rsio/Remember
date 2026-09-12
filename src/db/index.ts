import { createClient } from "@libsql/client/web";
import { drizzle } from "drizzle-orm/libsql";
import * as schema from "./schema";
import type { Env } from "../env";

export * from "./schema";

type AppDatabase = ReturnType<typeof drizzle<typeof schema>>;

let cached:
  | {
      url: string;
      token: string | undefined;
      db: AppDatabase;
    }
  | null = null;

export function getDb(env: Env) {
  if (!env.TURSO_DATABASE_URL) {
    throw new Error("TURSO_DATABASE_URL is not configured");
  }

  if (
    cached &&
    cached.url === env.TURSO_DATABASE_URL &&
    cached.token === env.TURSO_AUTH_TOKEN
  ) {
    return cached.db;
  }

  const client = createClient({
    url: env.TURSO_DATABASE_URL,
    authToken: env.TURSO_AUTH_TOKEN,
  });

  const db = drizzle(client, { schema });
  cached = {
    url: env.TURSO_DATABASE_URL,
    token: env.TURSO_AUTH_TOKEN,
    db,
  };
  return db;
}

export type Database = ReturnType<typeof getDb>;

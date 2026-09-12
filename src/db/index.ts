import { createClient } from "@libsql/client/web";
import { drizzle } from "drizzle-orm/libsql";
import * as schema from "./schema";
import type { Env } from "../env";

export * from "./schema";

export function getDb(env: Env) {
  if (!env.TURSO_DATABASE_URL) {
    throw new Error("TURSO_DATABASE_URL environment variable is not defined");
  }

  const client = createClient({
    url: env.TURSO_DATABASE_URL,
    authToken: env.TURSO_AUTH_TOKEN,
  });

  return drizzle(client, { schema });
}

export type Database = ReturnType<typeof getDb>;

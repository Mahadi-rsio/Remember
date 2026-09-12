import { drizzle } from "drizzle-orm/d1";
import * as schema from "./schema";
import type { Env } from "../env";

export * from "./schema";

export function getDb(env: Env) {
  if (!env.DB) {
    throw new Error("DB (Cloudflare D1) binding is not configured");
  }

  return drizzle(env.DB, { schema });
}

export type Database = ReturnType<typeof getDb>;

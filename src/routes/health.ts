import { Hono } from "hono";
import type { HonoContext } from "../env";
import { getDb } from "../db";
import { sql } from "drizzle-orm";

export const healthRouter = new Hono<HonoContext>();

healthRouter.get("/health", async (c) => {
  const env = c.env;
  let tursoReady = false;

  if (env.TURSO_DATABASE_URL) {
    try {
      const db = getDb(env);
      await db.run(sql`SELECT 1`);
      tursoReady = true;
    } catch {
      tursoReady = false;
    }
  }

  const isMemoryAiEnabled =
    String(env.MEMORY_AI_ENABLED).toLowerCase() === "true";

  return c.json({
    status: tursoReady || !env.TURSO_DATABASE_URL ? "ok" : "degraded",
    service: "remember-memory-gateway",
    runtime: "cloudflare-worker",
    database: {
      provider: "turso",
      ready: tursoReady,
    },
    memory_ai_enabled: isMemoryAiEnabled,
    context_budget: Number(env.CONTEXT_BUDGET ?? 8000),
  });
});

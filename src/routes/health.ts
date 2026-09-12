import { Hono } from "hono";
import type { HonoContext } from "../env";
import { getDb } from "../db";
import { getRedis } from "../cache";
import { sql } from "drizzle-orm";

export const healthRouter = new Hono<HonoContext>();

healthRouter.get("/health", async (c) => {
  const env = c.env;
  let dbReady = false;
  let redisReady = false;

  if (env.DATABASE_URL) {
    try {
      const db = getDb(env);
      await db.execute(sql`SELECT 1`);
      dbReady = true;
    } catch {
      dbReady = false;
    }
  }

  // Upstash Redis check (optional)
  const redis = getRedis(env);
  if (redis) {
    try {
      const pong = await redis.ping();
      redisReady = pong === "PONG";
    } catch {
      redisReady = false;
    }
  }

  const isMemoryAiEnabled =
    String(env.MEMORY_AI_ENABLED).toLowerCase() === "true";

  // Fail-open when Neon is not configured (proxy still works without memory)
  const ready = dbReady || !env.DATABASE_URL;

  return c.json({
    status: ready ? "ok" : "degraded",
    service: "remember-memory-gateway",
    runtime: "cloudflare-worker",
    database: {
      provider: "neon",
      ready: dbReady,
    },
    cache: {
      provider: "upstash-redis",
      configured: Boolean(redis),
      ready: redisReady,
    },
    memory_ai_enabled: isMemoryAiEnabled,
    context_budget: Number(env.CONTEXT_BUDGET ?? 8000),
  });
});

import { Hono } from "hono";
import type { HonoContext } from "../env";
import { getDb } from "../db";
import { getRedis } from "../cache";
import { sql } from "drizzle-orm";

export const healthRouter = new Hono<HonoContext>();

healthRouter.get("/health", async (c) => {
  const env = c.env;
  let d1Ready = false;
  let redisReady = false;

  // Cloudflare D1 check
  if (env.DB) {
    try {
      const db = getDb(env);
      await db.run(sql`SELECT 1`);
      d1Ready = true;
    } catch {
      d1Ready = false;
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

  const ready = d1Ready || !env.DB;

  return c.json({
    status: ready ? "ok" : "degraded",
    service: "remember-memory-gateway",
    runtime: "cloudflare-worker",
    database: {
      provider: "cloudflare-d1",
      ready: d1Ready,
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

import type { Context } from "hono";
import type { HonoContext } from "../env";
import { getRateLimiter } from "../cache";

export async function checkRateLimit(c: Context<HonoContext>): Promise<Response | null> {
  const limiter = getRateLimiter(c.env);
  if (!limiter) {
    return null; // Rate limiting not active without Redis
  }

  const ip =
    c.req.header("cf-connecting-ip") ||
    c.req.header("x-forwarded-for")?.split(",")[0].trim() ||
    "unknown";

  try {
    const { success, reset } = await limiter.limit(ip);
    if (!success) {
      const retryAfterSeconds = Math.max(1, Math.ceil((reset - Date.now()) / 1000));
      return c.json(
        {
          error: {
            message: "Rate limit exceeded; please retry later",
            type: "requests",
            code: "rate_limit_exceeded",
          },
        },
        429,
        {
          "Retry-After": String(retryAfterSeconds),
        }
      );
    }
  } catch {
    // Fail open on rate limiter error
    return null;
  }

  return null;
}

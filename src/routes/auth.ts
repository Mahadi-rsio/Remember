import type { Context } from "hono";
import type { HonoContext } from "../env";

export function checkAuth(c: Context<HonoContext>): Response | null {
  const expected = c.env.GATEWAY_API_KEY;
  if (!expected) {
    return null; // Open mode
  }

  const authHeader = c.req.header("authorization") || "";
  if (authHeader.toLowerCase().startsWith("bearer ")) {
    const token = authHeader.slice(7).trim();
    if (token === expected) {
      return null;
    }
  }

  const apiKeyHeader = c.req.header("x-api-key") || "";
  if (apiKeyHeader === expected) {
    return null;
  }

  return c.json(
    {
      error: {
        message: "Unauthorized: valid API key required",
        type: "invalid_request_error",
        code: "invalid_api_key",
      },
    },
    401
  );
}

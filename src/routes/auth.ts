import type { Context } from "hono";
import type { HonoContext } from "../env";
import { userIdForApiKey } from "../auth/identity";

export interface AuthUser {
  userId: string;
  apiKey: string;
}

function unauthorized(c: Context<HonoContext>): Response {
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

/**
 * Authenticate a request via the `Authorization: Bearer <key>` header.
 *
 * Returns the resolved user identity, or a 401 Response when the header is
 * missing, the token is not a Bearer token, or the key is not a valid one.
 */
export function checkAuth(c: Context<HonoContext>): AuthUser | Response {
  const authHeader = c.req.header("authorization") || "";
  if (!authHeader.toLowerCase().startsWith("bearer ")) {
    return unauthorized(c);
  }

  const token = authHeader.slice(7).trim();
  if (!token) {
    return unauthorized(c);
  }

  const userId = userIdForApiKey(token);
  if (!userId) {
    return unauthorized(c);
  }

  return { userId, apiKey: token };
}

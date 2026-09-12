/**
 * API-key → user identity resolution.
 *
 * Initial development implementation: a single fixed API key is hardcoded and
 * resolves to one deterministic test user. This module is the single seam to
 * replace later with a real API-key table lookup.
 */

export const GATEWAY_API_KEY = "1234";
export const TEST_USER_ID = "test-user";

/** Map an authenticated API key to a stable internal user identity. */
export function userIdForApiKey(apiKey: string): string | null {
  if (apiKey === GATEWAY_API_KEY) {
    return TEST_USER_ID;
  }
  return null;
}

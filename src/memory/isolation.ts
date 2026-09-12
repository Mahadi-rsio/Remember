import { createHash } from "node:crypto";

function asStr(value: any): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") {
    const t = value.trim();
    return t || null;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

function headerValue(headers: Headers | Record<string, string> | undefined, ...names: string[]): string | null {
  if (!headers) return null;
  if (headers instanceof Headers) {
    for (const name of names) {
      const v = headers.get(name);
      if (v) return asStr(v);
    }
    return null;
  }
  const lower: Record<string, string> = {};
  for (const [k, v] of Object.entries(headers)) {
    lower[k.toLowerCase()] = v;
  }
  for (const name of names) {
    const v = lower[name.toLowerCase()];
    if (v) return asStr(v);
  }
  return null;
}

export function extractUserKey(
  body: Record<string, any>,
  headers?: Headers | Record<string, string>
): string | null {
  for (const candidate of [
    headerValue(headers, "x-user-id", "x-user"),
    asStr(body.user),
    typeof body.metadata === "object" && body.metadata !== null ? asStr(body.metadata.user_id) : null,
    typeof body.metadata === "object" && body.metadata !== null ? asStr(body.metadata.user) : null,
  ]) {
    if (candidate) return candidate;
  }
  return null;
}

export function extractExplicitConversationId(
  body: Record<string, any>,
  headers?: Headers | Record<string, string>
): string | null {
  const meta = typeof body.metadata === "object" && body.metadata !== null ? body.metadata : {};
  for (const candidate of [
    headerValue(headers, "x-conversation-id", "x-session-id"),
    asStr(body.conversation_id),
    asStr(body.conversation),
    asStr(body.session_id),
    asStr(meta.conversation_id),
    asStr(meta.session_id),
  ]) {
    if (candidate) return candidate;
  }
  return null;
}

function fingerprintMessages(messages: any[]): string {
  const seed = messages.slice(0, 1);
  const canonical = JSON.stringify(seed);
  return createHash("sha256").update(canonical).digest("hex").slice(0, 32);
}

export function deriveIsolationKeys(
  body: Record<string, any>,
  headers?: Headers | Record<string, string>
): [string, string | null] {
  const userKey = extractUserKey(body, headers);
  const explicit = extractExplicitConversationId(body, headers);
  if (explicit) {
    return [explicit, userKey];
  }

  let messages = body.messages;
  if (!Array.isArray(messages)) {
    const rawInput = body.input;
    if (Array.isArray(rawInput)) {
      messages = rawInput;
    } else if (typeof rawInput === "string") {
      messages = [{ role: "user", content: rawInput }];
    } else {
      messages = [];
    }
  }

  const fingerprint = fingerprintMessages(messages);
  if (userKey) {
    return [`u:${userKey}:${fingerprint}`, userKey];
  }
  return [`anon:${fingerprint}`, null];
}

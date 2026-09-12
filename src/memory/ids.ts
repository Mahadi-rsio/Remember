import { createHash } from "node:crypto";

export function canonicalizeContent(content: any): string {
  if (content === null || content === undefined) {
    return "";
  }
  if (typeof content === "string") {
    return content;
  }
  try {
    return JSON.stringify(content);
  } catch {
    return String(content);
  }
}

export function contentHash(role: string, content: any, ordinal?: number | null): string {
  const payload: Record<string, any> = {
    role,
    content: canonicalizeContent(content),
  };
  if (ordinal !== undefined && ordinal !== null) {
    payload.ordinal = ordinal;
  }
  const raw = JSON.stringify(payload);
  return createHash("sha256").update(raw).digest("hex");
}

export function extractClientMessageId(message: Record<string, any>): string | null {
  for (const key of ["id", "message_id"]) {
    const value = message[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  const toolCallId = message.tool_call_id;
  if (typeof toolCallId === "string" && toolCallId.trim()) {
    return `tool:${toolCallId.trim()}`;
  }
  return null;
}

export interface NormalizedMessage {
  role: string;
  content: string;
  contentHash: string;
  messageKey: string;
  clientMessageId: string | null;
  ordinal: number;
  raw: Record<string, any>;
}

export function normalizeMessage(message: Record<string, any>, ordinal: number): NormalizedMessage {
  const role = String(message.role || "user");
  const content = canonicalizeContent(message.content);
  const clientId = extractClientMessageId(message);

  const digest = contentHash(role, message.content, clientId ? null : ordinal);
  const messageKey = clientId ? `id:${clientId}` : `hash:${digest}`;

  return {
    role,
    content,
    contentHash: digest,
    messageKey,
    clientMessageId: clientId,
    ordinal,
    raw: { ...message },
  };
}

export function normalizeMessages(messages: Array<Record<string, any>>): NormalizedMessage[] {
  return messages.map((msg, i) => normalizeMessage(msg, i));
}

import { eq } from "drizzle-orm";
import type { Database } from "../db";
import { messages as messagesTable } from "../db/schema/messages";
import { type NormalizedMessage, normalizeMessages } from "./ids";

export interface DeltaResult {
  conversationId: string;
  userKey: string | null;
  allMessages: NormalizedMessage[];
  newMessages: NormalizedMessage[];
  duplicateMessages: NormalizedMessage[];
  alreadyProcessedKeys: Set<string>;
}

export async function loadProcessedKeys(
  db: Database,
  conversationId: string
): Promise<Set<string>> {
  const rows = await db
    .select({ messageKey: messagesTable.messageKey })
    .from(messagesTable)
    .where(eq(messagesTable.conversationId, conversationId));

  return new Set(rows.map((r) => r.messageKey));
}

export async function detectDelta(
  db: Database,
  conversationId: string,
  userKey: string | null,
  messages: Array<Record<string, any>>
): Promise<DeltaResult> {
  const normalized = normalizeMessages(messages);
  const processed = await loadProcessedKeys(db, conversationId);

  const newMessages: NormalizedMessage[] = [];
  const duplicates: NormalizedMessage[] = [];
  const seenInRequest = new Set<string>();

  for (const msg of normalized) {
    if (seenInRequest.has(msg.messageKey)) {
      duplicates.push(msg);
      continue;
    }
    seenInRequest.add(msg.messageKey);

    if (processed.has(msg.messageKey)) {
      duplicates.push(msg);
    } else {
      newMessages.push(msg);
    }
  }

  return {
    conversationId,
    userKey,
    allMessages: normalized,
    newMessages,
    duplicateMessages: duplicates,
    alreadyProcessedKeys: processed,
  };
}

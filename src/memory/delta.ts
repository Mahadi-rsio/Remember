import { eq } from "drizzle-orm";
import type { Database } from "../db";
import { messages as messagesTable } from "../db/schema/messages";
import { type NormalizedMessage, normalizeMessages } from "./ids";

export interface DeltaResult {
  userId: string;
  userKey: string | null;
  allMessages: NormalizedMessage[];
  newMessages: NormalizedMessage[];
  duplicateMessages: NormalizedMessage[];
  alreadyProcessedKeys: Set<string>;
}

export async function loadProcessedKeys(
  db: Database,
  userId: string
): Promise<Set<string>> {
  const rows = await db
    .select({ messageKey: messagesTable.messageKey })
    .from(messagesTable)
    .where(eq(messagesTable.userId, userId));

  return new Set(rows.map((r) => r.messageKey));
}

export async function detectDelta(
  db: Database,
  userId: string,
  userKey: string | null,
  messages: Array<Record<string, any>>
): Promise<DeltaResult> {
  const normalized = normalizeMessages(messages);
  const processed = await loadProcessedKeys(db, userId);

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
    userId,
    userKey,
    allMessages: normalized,
    newMessages,
    duplicateMessages: duplicates,
    alreadyProcessedKeys: processed,
  };
}

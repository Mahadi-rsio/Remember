import { eq, and } from "drizzle-orm";
import type { Database } from "../db";
import { conversations as conversationsTable } from "../db/schema/conversations";
import { messages as messagesTable, type Message } from "../db/schema/messages";
import { detectDelta, type DeltaResult } from "../memory/delta";
import { processMemoryDelta, processMemoryDeltaAsync } from "../memory/engine";
import type { NormalizedMessage } from "../memory/ids";
import { deriveIsolationKeys } from "../memory/isolation";
import type { MemoryAIAdapter } from "../providers/memory-ai";

export function extractMessageList(body: Record<string, any>): Array<Record<string, any>> {
  const msgs = body.messages;
  if (Array.isArray(msgs)) {
    return msgs.filter((m) => typeof m === "object" && m !== null);
  }

  const rawInput = body.input;
  if (Array.isArray(rawInput)) {
    const out: Array<Record<string, any>> = [];
    for (const item of rawInput) {
      if (typeof item === "object" && item !== null) {
        out.push(item);
      } else if (typeof item === "string") {
        out.push({ role: "user", content: item });
      }
    }
    return out;
  }
  if (typeof rawInput === "string") {
    return [{ role: "user", content: rawInput }];
  }
  return [];
}

export async function ensureConversation(
  db: Database,
  conversationId: string,
  userKey: string | null,
  extraMeta?: Record<string, any> | null
): Promise<void> {
  const existing = await db
    .select()
    .from(conversationsTable)
    .where(eq(conversationsTable.id, conversationId))
    .limit(1);

  const nowIso = new Date().toISOString();
  if (existing.length === 0) {
    await db.insert(conversationsTable).values({
      id: conversationId,
      userKey,
      createdAt: nowIso,
      updatedAt: nowIso,
      metadataJson: extraMeta ? JSON.stringify(extraMeta) : null,
    });
  } else {
    const row = existing[0];
    const updateData: { updatedAt: string; userKey?: string | null } = { updatedAt: nowIso };
    if (userKey && !row.userKey) {
      updateData.userKey = userKey;
    }
    await db
      .update(conversationsTable)
      .set(updateData)
      .where(eq(conversationsTable.id, conversationId));
  }
}

export async function persistNewMessages(
  db: Database,
  conversationId: string,
  newMessages: NormalizedMessage[]
): Promise<Message[]> {
  const written: Message[] = [];
  const nowIso = new Date().toISOString();

  for (const msg of newMessages) {
    const existing = await db
      .select({ id: messagesTable.id })
      .from(messagesTable)
      .where(
        and(
          eq(messagesTable.conversationId, conversationId),
          eq(messagesTable.messageKey, msg.messageKey)
        )
      )
      .limit(1);

    if (existing.length > 0) {
      continue;
    }

    const [row] = await db
      .insert(messagesTable)
      .values({
        conversationId,
        messageKey: msg.messageKey,
        role: msg.role,
        content: msg.content,
        contentHash: msg.contentHash,
        ordinal: msg.ordinal,
        clientMessageId: msg.clientMessageId,
        metadataJson: JSON.stringify(msg.raw),
        createdAt: nowIso,
      })
      .returning();

    written.push(row);
  }

  return written;
}

export async function archiveRequest(
  db: Database,
  body: Record<string, any>,
  headers?: Headers | Record<string, string>
): Promise<DeltaResult | null> {
  try {
    const [conversationId, userKey] = deriveIsolationKeys(body, headers);
    const messages = extractMessageList(body);
    await ensureConversation(db, conversationId, userKey);

    const delta = await detectDelta(db, conversationId, userKey, messages);
    if (delta.newMessages.length > 0) {
      await persistNewMessages(db, conversationId, delta.newMessages);
    }

    if (delta.newMessages.length > 0) {
      try {
        await processMemoryDelta(db, delta);
      } catch {}
    }

    return delta;
  } catch {
    return null;
  }
}

export async function archiveRequestAsync(
  db: Database,
  body: Record<string, any>,
  headers?: Headers | Record<string, string>,
  memoryAi?: MemoryAIAdapter | null
): Promise<DeltaResult | null> {
  try {
    const [conversationId, userKey] = deriveIsolationKeys(body, headers);
    const messages = extractMessageList(body);
    await ensureConversation(db, conversationId, userKey);

    const delta = await detectDelta(db, conversationId, userKey, messages);
    if (delta.newMessages.length > 0) {
      await persistNewMessages(db, conversationId, delta.newMessages);
    }

    if (delta.newMessages.length > 0) {
      try {
        await processMemoryDeltaAsync(db, delta, { memoryAi });
      } catch {}
    }

    return delta;
  } catch {
    return null;
  }
}

export async function listArchivedKeys(
  db: Database,
  conversationId: string
): Promise<Set<string>> {
  const rows = await db
    .select({ messageKey: messagesTable.messageKey })
    .from(messagesTable)
    .where(eq(messagesTable.conversationId, conversationId));

  return new Set(rows.map((r) => r.messageKey));
}

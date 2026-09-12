import { eq, and, like } from "drizzle-orm";
import type { Database } from "../db";
import { messages } from "../db/schema/messages";
import { memoryItems } from "../db/schema/memory";
import { MemoryStatus } from "../models/memory";
import type { Retriever, RetrievalResult } from "./interface";

export class D1Retriever implements Retriever {
  constructor(private db: Database) {}

  async searchMessages(
    query: string,
    conversationId: string,
    limit = 10
  ): Promise<RetrievalResult[]> {
    if (!query.trim()) return [];
    try {
      const pattern = `%${query.trim()}%`;
      const rows = await this.db
        .select()
        .from(messages)
        .where(
          and(
            eq(messages.conversationId, conversationId),
            like(messages.content, pattern)
          )
        )
        .limit(limit);

      return rows.map((r) => ({
        source: "messages" as const,
        rowId: r.id,
        content: r.content,
        role: r.role,
        conversationId: r.conversationId,
        score: 1.0,
      }));
    } catch {
      return [];
    }
  }

  async searchMemory(
    query: string,
    conversationId: string,
    limit = 10
  ): Promise<RetrievalResult[]> {
    if (!query.trim()) return [];
    try {
      const pattern = `%${query.trim()}%`;
      const rows = await this.db
        .select()
        .from(memoryItems)
        .where(
          and(
            eq(memoryItems.conversationId, conversationId),
            eq(memoryItems.status, MemoryStatus.ACTIVE),
            like(memoryItems.content, pattern)
          )
        )
        .limit(limit);

      return rows.map((r) => ({
        source: "memory_items" as const,
        rowId: r.id,
        content: r.content,
        itemType: r.type,
        topicKey: r.topicKey,
        conversationId: r.conversationId,
        score: 1.0,
      }));
    } catch {
      return [];
    }
  }
}

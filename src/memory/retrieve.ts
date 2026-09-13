/**
 * Deterministic retrieval for long-term memories.
 *
 * No embeddings. Retrieval uses exact/structured filters: subject, predicate,
 * scope, status, confidence/importance/stability thresholds, recency, and
 * current-vs-historical state. When embeddings are added later they become an
 * ADDITIONAL retrieval strategy layered on top — not a rewrite of this engine.
 */
import { and, eq, gte, lte, desc, or, like } from "drizzle-orm";
import type { Database } from "../db";
import { memoryItems, type MemoryItem } from "../db/schema/memory";
import { MemoryStatus } from "../models/memory";

export interface MemoryRetrievalQuery {
  userId: string;
  /** Filter by the entity (subject) e.g. "user", "project", a project name. */
  subject?: string;
  /** Filter by attribute (predicate) e.g. "database", "runtime". */
  predicate?: string;
  /** Filter by scope: "user" | "project" | "session". */
  scope?: string;
  /** Filter by lifecycle status. Defaults to ACTIVE for current-state queries. */
  status?: string | string[];
  /** Include superseded/historical items (current vs historical). */
  includeHistorical?: boolean;
  /** Keyword substring match against content / value. */
  keyword?: string;
  minConfidence?: number;
  minImportance?: number;
  minStability?: number;
  /** Only items updated/created within this many seconds (recency). */
  recencySeconds?: number;
  limit?: number;
  order?: "recency" | "importance" | "confidence";
}

export interface RetrievedMemory {
  item: MemoryItem;
  current: boolean;
}

/**
 * Retrieve long-term memories deterministically. `current` distinguishes
 * currently-active facts from superseded/revoked historical ones.
 */
export async function retrieveMemories(
  db: Database,
  query: MemoryRetrievalQuery
): Promise<RetrievedMemory[]> {
  const conditions = [eq(memoryItems.userId, query.userId)];

  if (query.subject) {
    conditions.push(eq(memoryItems.subject, query.subject));
  }
  if (query.predicate) {
    conditions.push(eq(memoryItems.predicate, query.predicate));
  }
  if (query.scope) {
    conditions.push(eq(memoryItems.scope, query.scope));
  }
  if (query.minConfidence !== undefined) {
    conditions.push(gte(memoryItems.confidence, query.minConfidence));
  }
  if (query.minImportance !== undefined) {
    conditions.push(gte(memoryItems.importance, query.minImportance));
  }
  if (query.minStability !== undefined) {
    conditions.push(gte(memoryItems.stability, query.minStability));
  }

  if (query.includeHistorical) {
    // All statuses.
  } else {
    const statuses =
      query.status === undefined
        ? [MemoryStatus.ACTIVE]
        : Array.isArray(query.status)
          ? query.status
          : [query.status];
    if (statuses.length === 1) {
      conditions.push(eq(memoryItems.status, statuses[0]));
    } else {
      conditions.push(
        or(...statuses.map((s) => eq(memoryItems.status, s))) as any
      );
    }
  }

  if (query.keyword) {
    const pattern = `%${query.keyword.trim()}%`;
    conditions.push(
      or(
        like(memoryItems.content, pattern),
        like(memoryItems.value, pattern),
        like(memoryItems.predicate, pattern)
      ) as any
    );
  }

  if (query.recencySeconds !== undefined && query.recencySeconds > 0) {
    const cutoff = new Date(Date.now() - query.recencySeconds * 1000).toISOString();
    conditions.push(gte(memoryItems.updatedAt, cutoff));
  }

  const orderBy =
    query.order === "importance"
      ? desc(memoryItems.importance)
      : query.order === "confidence"
        ? desc(memoryItems.confidence)
        : desc(memoryItems.updatedAt);

  const rows = await db
    .select()
    .from(memoryItems)
    .where(and(...conditions))
    .orderBy(orderBy)
    .limit(query.limit ?? 20);

  return rows.map((item) => ({
    item,
    current: item.status === MemoryStatus.ACTIVE,
  }));
}

/**
 * Convenience: retrieve only currently-active memories, optionally filtered by
 * predicate/scope — used by the context composer to answer
 * "What should we remember long-term?".
 */
export async function retrieveActiveMemories(
  db: Database,
  userId: string,
  options?: {
    subject?: string;
    predicate?: string;
    scope?: string;
    keyword?: string;
    minImportance?: number;
    limit?: number;
  }
): Promise<MemoryItem[]> {
  const result = await retrieveMemories(db, {
    userId,
    subject: options?.subject,
    predicate: options?.predicate,
    scope: options?.scope,
    keyword: options?.keyword,
    minImportance: options?.minImportance,
    limit: options?.limit,
    status: MemoryStatus.ACTIVE,
  });
  return result.map((r) => r.item);
}

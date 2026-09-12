import { eq, and } from "drizzle-orm";
import type { Database } from "../db";
import { memoryItems, type MemoryItem } from "../db/schema/memory";
import {
  type CandidateMemory,
  type Correction,
  MemoryStatus,
  MemoryType,
} from "../models/memory";
import { contentSimilarity, shouldWriteNewItem, scoreCandidate } from "./scorer";
import { topicKeyFromContent } from "./extractor";

export type ActionKind = "skip" | "merge" | "create" | "supersede" | "reject" | "revoke";

export interface ApplyResult {
  action: ActionKind;
  item?: MemoryItem | null;
  superseded?: MemoryItem | null;
  reason: string;
  correction?: Correction | null;
  revoked?: MemoryItem[] | null;
}

export function parseSourceIds(raw: string): string[] {
  try {
    const data = JSON.parse(raw || "[]");
    if (Array.isArray(data)) {
      return data.map((x) => String(x));
    }
  } catch {}
  return [];
}

export function dumpSourceIds(ids: string[]): string {
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const i of ids) {
    if (!seen.has(i)) {
      seen.add(i);
      ordered.push(i);
    }
  }
  return JSON.stringify(ordered);
}

export async function loadActiveItems(db: Database, conversationId: string): Promise<MemoryItem[]> {
  return await db
    .select()
    .from(memoryItems)
    .where(
      and(
        eq(memoryItems.conversationId, conversationId),
        eq(memoryItems.status, MemoryStatus.ACTIVE)
      )
    );
}

function sameTopic(candidate: CandidateMemory, item: MemoryItem): boolean {
  if (item.type !== candidate.type) {
    return false;
  }
  let itemTopic = (item.topicKey || "").trim();
  if (!itemTopic) {
    itemTopic = topicKeyFromContent(item.content, item.type as MemoryType);
  }
  return Boolean(candidate.topicKey) && candidate.topicKey === itemTopic;
}

function isNearDuplicate(candidate: CandidateMemory, item: MemoryItem): boolean {
  if (item.type !== candidate.type) {
    return false;
  }
  return contentSimilarity(candidate.content, item.content) >= 0.9;
}

function isContradiction(candidate: CandidateMemory, item: MemoryItem): boolean {
  if (!sameTopic(candidate, item)) {
    return false;
  }
  return contentSimilarity(candidate.content, item.content) < 0.9;
}

function correctionOldMatch(candidate: CandidateMemory, active: MemoryItem[]): MemoryItem | null {
  if (!candidate.correction) {
    return null;
  }
  const old = (candidate.correction.oldValue || "").toLowerCase().trim();
  if (!old) {
    return null;
  }
  let best: MemoryItem | null = null;
  let bestScore = 0.0;
  for (const item of active) {
    const itemContent = item.content.toLowerCase();
    if (itemContent.includes(old)) {
      return item;
    }
    const sim = contentSimilarity(old, itemContent);
    if (sim > bestScore) {
      bestScore = sim;
      best = item;
    }
  }
  if (bestScore >= 0.75) {
    return best;
  }
  return null;
}

function canSupersede(candidate: CandidateMemory, existing: MemoryItem): boolean {
  if (candidate.authority === "speculation") {
    if (existing.type === MemoryType.DECISION && existing.confidence >= 0.85) {
      return false;
    }
    if (existing.confidence >= candidate.scores.confidence) {
      return false;
    }
  }
  if (
    existing.type === MemoryType.DECISION &&
    candidate.type !== MemoryType.DECISION &&
    !candidate.isCorrection &&
    candidate.authority !== "user"
  ) {
    return false;
  }
  return true;
}

export function mergeIntoExisting(item: MemoryItem, candidate: CandidateMemory): MemoryItem {
  const sources = parseSourceIds(item.sourceMessageIdsJson);
  sources.push(...candidate.sourceMessageIds);
  item.sourceMessageIdsJson = dumpSourceIds(sources);
  item.confidence = Math.max(item.confidence, candidate.scores.confidence);
  item.importance = Math.max(item.importance, candidate.scores.importance);
  item.stability = Math.min(1.0, Math.max(item.stability, candidate.scores.stability) + 0.08);
  item.freshness = Math.max(item.freshness, candidate.scores.freshness);
  item.informationGain = candidate.scores.informationGain;
  item.updatedAt = new Date().toISOString();
  return item;
}

function findRevocationTargets(candidate: CandidateMemory, active: MemoryItem[]): MemoryItem[] {
  if (!candidate.revocation) {
    return [];
  }
  const value = (candidate.revocation.value || "").toLowerCase().trim();
  const target = (candidate.revocation.target || "").toLowerCase().trim();
  const targetTokens = new Set(target.match(/[a-z0-9]+/g) || []);

  const matches: MemoryItem[] = [];
  for (const item of active) {
    const content = item.content.toLowerCase();
    const topic = (item.topicKey || "").toLowerCase();
    if (value && content.includes(value)) {
      matches.push(item);
      continue;
    }
    if (targetTokens.size > 0) {
      const contentTokens = new Set(content.match(/[a-z0-9]+/g) || []);
      const topicTokens = new Set(topic.match(/[a-z0-9]+/g) || []);
      let overlap = false;
      for (const t of targetTokens) {
        if (contentTokens.has(t) || topicTokens.has(t)) {
          overlap = true;
          break;
        }
      }
      if (overlap) {
        matches.push(item);
      }
    }
  }
  return matches;
}

export async function applyCandidate(
  db: Database,
  conversationId: string,
  candidate: CandidateMemory,
  activeItems?: MemoryItem[]
): Promise<ApplyResult> {
  const active = activeItems ?? (await loadActiveItems(db, conversationId));

  const sameTypeContents = active.filter((i) => i.type === candidate.type).map((i) => i.content);
  candidate.scores = scoreCandidate(candidate, sameTypeContents);

  // 1. Explicit revocation
  if (candidate.revocation) {
    const targets = findRevocationTargets(candidate, active);
    if (targets.length > 0) {
      const revoked: MemoryItem[] = [];
      const nowIso = new Date().toISOString();
      for (const item of targets) {
        if (item.status === MemoryStatus.ACTIVE) {
          await db
            .update(memoryItems)
            .set({ status: MemoryStatus.REVOKED, updatedAt: nowIso })
            .where(eq(memoryItems.id, item.id));
          item.status = MemoryStatus.REVOKED;
          item.updatedAt = nowIso;
          revoked.push(item);
        }
      }
      return {
        action: "revoke",
        reason: "revocation",
        revoked,
      };
    }
    return { action: "skip", reason: "no_revocation_target" };
  }

  // 2. Explicit correction
  if (candidate.correction) {
    const target = correctionOldMatch(candidate, active);
    if (target && canSupersede(candidate, target)) {
      const nowIso = new Date().toISOString();
      await db
        .update(memoryItems)
        .set({ status: MemoryStatus.SUPERSEDED, updatedAt: nowIso })
        .where(eq(memoryItems.id, target.id));
      target.status = MemoryStatus.SUPERSEDED;
      target.updatedAt = nowIso;

      const [inserted] = await db
        .insert(memoryItems)
        .values({
          conversationId,
          content: candidate.content,
          type: candidate.type,
          topicKey: candidate.topicKey,
          confidence: candidate.scores.confidence,
          importance: candidate.scores.importance,
          stability: candidate.scores.stability,
          freshness: candidate.scores.freshness,
          informationGain: candidate.scores.informationGain,
          sourceMessageIdsJson: dumpSourceIds(candidate.sourceMessageIds),
          status: MemoryStatus.ACTIVE,
          version: target.version + 1,
          createdAt: nowIso,
          updatedAt: nowIso,
        })
        .returning();

      return {
        action: "supersede",
        item: inserted,
        superseded: target,
        reason: "correction",
        correction: candidate.correction,
      };
    }
  }

  // 3. Exact / near duplicate -> merge
  for (const item of active) {
    if (isNearDuplicate(candidate, item)) {
      mergeIntoExisting(item, candidate);
      await db
        .update(memoryItems)
        .set({
          sourceMessageIdsJson: item.sourceMessageIdsJson,
          confidence: item.confidence,
          importance: item.importance,
          stability: item.stability,
          freshness: item.freshness,
          informationGain: item.informationGain,
          updatedAt: item.updatedAt,
        })
        .where(eq(memoryItems.id, item.id));
      return { action: "merge", item, reason: "near_duplicate" };
    }
  }

  // 4. Same topic contradiction -> supersede
  for (const item of active) {
    if (isContradiction(candidate, item)) {
      if (!canSupersede(candidate, item)) {
        return {
          action: "reject",
          item,
          reason: "speculation_cannot_overwrite_decision",
        };
      }
      const nowIso = new Date().toISOString();
      await db
        .update(memoryItems)
        .set({ status: MemoryStatus.SUPERSEDED, updatedAt: nowIso })
        .where(eq(memoryItems.id, item.id));
      item.status = MemoryStatus.SUPERSEDED;
      item.updatedAt = nowIso;

      const [inserted] = await db
        .insert(memoryItems)
        .values({
          conversationId,
          content: candidate.content,
          type: candidate.type,
          topicKey: candidate.topicKey,
          confidence: candidate.scores.confidence,
          importance: candidate.scores.importance,
          stability: candidate.scores.stability,
          freshness: candidate.scores.freshness,
          informationGain: candidate.scores.informationGain,
          sourceMessageIdsJson: dumpSourceIds(candidate.sourceMessageIds),
          status: MemoryStatus.ACTIVE,
          version: item.version + 1,
          createdAt: nowIso,
          updatedAt: nowIso,
        })
        .returning();

      let corr = candidate.correction;
      if (!corr && candidate.isCorrection) {
        corr = {
          target: candidate.topicKey,
          oldValue: item.content,
          newValue: candidate.content,
        };
      }

      return {
        action: "supersede",
        item: inserted,
        superseded: item,
        reason: "topic_contradiction",
        correction: corr,
      };
    }
  }

  // 5. Low information gain check
  if (!shouldWriteNewItem(candidate.scores)) {
    return { action: "skip", reason: "low_information_gain" };
  }

  // 6. Create new memory item
  const nowIso = new Date().toISOString();
  const [created] = await db
    .insert(memoryItems)
    .values({
      conversationId,
      content: candidate.content,
      type: candidate.type,
      topicKey: candidate.topicKey,
      confidence: candidate.scores.confidence,
      importance: candidate.scores.importance,
      stability: candidate.scores.stability,
      freshness: candidate.scores.freshness,
      informationGain: candidate.scores.informationGain,
      sourceMessageIdsJson: dumpSourceIds(candidate.sourceMessageIds),
      status: MemoryStatus.ACTIVE,
      version: 1,
      createdAt: nowIso,
      updatedAt: nowIso,
    })
    .returning();

  return { action: "create", item: created, reason: "new_topic" };
}

import type { Database } from "../db";
import type { DeltaResult } from "./delta";
import type { ApplyResult } from "./contradiction";
import type { CandidateMemory, MemoryAIOutput } from "../models/memory";
import type { ShortTermContextStore } from "./context-store";
import { extractCandidates } from "./extractor";
import { isLowInfoMessage } from "./low-info";
import { analyzeCandidates } from "./analyzer";
import { memoryAiOutputToCandidates } from "./compressor";
import {
  listMemoryItems,
  markItemsObsolete,
  memoryChanged,
  persistCandidates,
  writeContextVersion,
} from "./state";
import { MemoryStatus, snapshotFromItems } from "../models/memory";
import type { MemoryAIAdapter } from "../providers/memory-ai";

export interface MemoryUpdateResult {
  userId: string;
  skippedLowInfo?: boolean;
  candidates: number;
  stored: number;
  contextCount: number;
  discarded: number;
  applied: ApplyResult[];
  obsoleteMarked: number;
  contextVersion?: number | null;
  error?: string | null;
}

export async function processMemoryDelta(
  db: Database,
  delta: DeltaResult,
  options?: {
    memoryAiOutput?: MemoryAIOutput | null;
    contextStore?: ShortTermContextStore | null;
  }
): Promise<MemoryUpdateResult | null> {
  const base = {
    userId: delta.userId,
    candidates: 0,
    stored: 0,
    contextCount: 0,
    discarded: 0,
    applied: [],
    obsoleteMarked: 0,
  };

  if (!delta.newMessages || delta.newMessages.length === 0) {
    return { ...base };
  }

  const meaningful = delta.newMessages.filter(
    (m) => ["user", "assistant"].includes(m.role) && !isLowInfoMessage(m.content, m.role)
  );

  if (meaningful.length === 0) {
    return {
      ...base,
      skippedLowInfo: true,
    };
  }

  try {
    const candidates: CandidateMemory[] = extractCandidates(delta.newMessages);
    const sourceIds = delta.newMessages.map((m) => m.messageKey);

    const memoryAiOutput = options?.memoryAiOutput;
    if (memoryAiOutput) {
      const aiCandidates = memoryAiOutputToCandidates(memoryAiOutput, sourceIds);
      const existingContents = new Set(candidates.map((c) => c.content.toLowerCase()));
      for (const aiC of aiCandidates) {
        if (!existingContents.has(aiC.content.toLowerCase())) {
          candidates.push(aiC);
          existingContents.add(aiC.content.toLowerCase());
        }
      }
    }

    // Memory Analyzer: route each candidate to store / context / discard.
    const { store, discard, contextEntries } = analyzeCandidates(candidates);

    let results: ApplyResult[] = [];
    if (store.length > 0) {
      results = await persistCandidates(db, delta.userId, store);
    }

    // Persist short-term context (Redis / in-memory store).
    let contextCount = 0;
    const contextStore = options?.contextStore;
    if (contextStore && contextEntries.length > 0) {
      for (const entry of contextEntries) {
        try {
          await contextStore.setContext(
            delta.userId,
            entry.key,
            entry.value,
            entry.ttlSeconds
          );
          contextCount++;
        } catch {
          // fail-open: context persistence must never break the main path
        }
      }
    }

    let obsoleteCount = 0;
    if (memoryAiOutput && memoryAiOutput.obsolete_items.length > 0) {
      const marked = await markItemsObsolete(
        db,
        delta.userId,
        memoryAiOutput.obsolete_items
      );
      obsoleteCount = marked.length;
    }

    let versionNum: number | null = null;
    if (memoryChanged(results, obsoleteCount)) {
      versionNum = await writeContextVersion(db, delta.userId, sourceIds);
    }

    return {
      userId: delta.userId,
      candidates: candidates.length,
      stored: store.length,
      contextCount,
      discarded: discard.length,
      applied: results,
      obsoleteMarked: obsoleteCount,
      contextVersion: versionNum,
    };
  } catch (err: any) {
    return {
      userId: delta.userId,
      candidates: 0,
      stored: 0,
      contextCount: 0,
      discarded: 0,
      applied: [],
      obsoleteMarked: 0,
      error: err?.message || String(err),
    };
  }
}

export async function processMemoryDeltaAsync(
  db: Database,
  delta: DeltaResult,
  options?: {
    memoryAi?: MemoryAIAdapter | null;
    contextStore?: ShortTermContextStore | null;
  }
): Promise<MemoryUpdateResult | null> {
  const base = {
    userId: delta.userId,
    candidates: 0,
    stored: 0,
    contextCount: 0,
    discarded: 0,
    applied: [],
    obsoleteMarked: 0,
  };

  if (!delta.newMessages || delta.newMessages.length === 0) {
    return { ...base };
  }

  const meaningful = delta.newMessages.filter(
    (m) => ["user", "assistant"].includes(m.role) && !isLowInfoMessage(m.content, m.role)
  );

  if (meaningful.length === 0) {
    return {
      ...base,
      skippedLowInfo: true,
    };
  }

  let aiOutput: MemoryAIOutput | null = null;
  const memoryAi = options?.memoryAi;

  if (memoryAi) {
    try {
      const messagesText = delta.newMessages
        .filter((m) => m.content)
        .map((m) => `${m.role}: ${m.content}`)
        .join("\n");

      let priorSummary: string | null = null;
      try {
        const active = await listMemoryItems(db, delta.userId, MemoryStatus.ACTIVE);
        if (active.length > 0) {
          priorSummary = JSON.stringify(snapshotFromItems(active));
        }
      } catch {}

      aiOutput = await memoryAi.extractMemory(messagesText, priorSummary);
    } catch {
      aiOutput = null;
    }
  }

  return await processMemoryDelta(db, delta, {
    memoryAiOutput: aiOutput,
    contextStore: options?.contextStore,
  });
}

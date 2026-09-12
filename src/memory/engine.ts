import type { Database } from "../db";
import type { DeltaResult } from "./delta";
import type { ApplyResult } from "./contradiction";
import type { CandidateMemory, MemoryAIOutput } from "../models/memory";
import { extractCandidates } from "./extractor";
import { isLowInfoMessage } from "./low-info";
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
  conversationId: string;
  skippedLowInfo?: boolean;
  candidates: number;
  applied: ApplyResult[];
  obsoleteMarked: number;
  contextVersion?: number | null;
  error?: string | null;
}

export async function processMemoryDelta(
  db: Database,
  delta: DeltaResult,
  options?: { memoryAiOutput?: MemoryAIOutput | null }
): Promise<MemoryUpdateResult | null> {
  if (!delta.newMessages || delta.newMessages.length === 0) {
    return {
      conversationId: delta.conversationId,
      candidates: 0,
      applied: [],
      obsoleteMarked: 0,
    };
  }

  const meaningful = delta.newMessages.filter(
    (m) => ["user", "assistant"].includes(m.role) && !isLowInfoMessage(m.content, m.role)
  );

  if (meaningful.length === 0) {
    return {
      conversationId: delta.conversationId,
      skippedLowInfo: true,
      candidates: 0,
      applied: [],
      obsoleteMarked: 0,
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

    let results: ApplyResult[] = [];
    if (candidates.length > 0) {
      results = await persistCandidates(db, delta.conversationId, candidates);
    }

    let obsoleteCount = 0;
    if (memoryAiOutput && memoryAiOutput.obsolete_items.length > 0) {
      const marked = await markItemsObsolete(
        db,
        delta.conversationId,
        memoryAiOutput.obsolete_items
      );
      obsoleteCount = marked.length;
    }

    let versionNum: number | null = null;
    if (memoryChanged(results, obsoleteCount)) {
      versionNum = await writeContextVersion(db, delta.conversationId, sourceIds);
    }

    return {
      conversationId: delta.conversationId,
      candidates: candidates.length,
      applied: results,
      obsoleteMarked: obsoleteCount,
      contextVersion: versionNum,
    };
  } catch (err: any) {
    return {
      conversationId: delta.conversationId,
      candidates: 0,
      applied: [],
      obsoleteMarked: 0,
      error: err?.message || String(err),
    };
  }
}

export async function processMemoryDeltaAsync(
  db: Database,
  delta: DeltaResult,
  options?: { memoryAi?: MemoryAIAdapter | null }
): Promise<MemoryUpdateResult | null> {
  if (!delta.newMessages || delta.newMessages.length === 0) {
    return {
      conversationId: delta.conversationId,
      candidates: 0,
      applied: [],
      obsoleteMarked: 0,
    };
  }

  const meaningful = delta.newMessages.filter(
    (m) => ["user", "assistant"].includes(m.role) && !isLowInfoMessage(m.content, m.role)
  );

  if (meaningful.length === 0) {
    return {
      conversationId: delta.conversationId,
      skippedLowInfo: true,
      candidates: 0,
      applied: [],
      obsoleteMarked: 0,
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
        const active = await listMemoryItems(db, delta.conversationId, MemoryStatus.ACTIVE);
        if (active.length > 0) {
          priorSummary = JSON.stringify(snapshotFromItems(active));
        }
      } catch {}

      aiOutput = await memoryAi.extractMemory(messagesText, priorSummary);
    } catch {
      aiOutput = null;
    }
  }

  return await processMemoryDelta(db, delta, { memoryAiOutput: aiOutput });
}

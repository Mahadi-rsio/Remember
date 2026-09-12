import type { Database } from "../db";
import { assembleContextMessages } from "./assembler";
import {
  extractKeywords,
  scoreCanonicalItem,
  scoreMessageItem,
  selectItemsForBudget,
  type SelectableItem,
} from "./selector";
import { estimateMessagesTokens } from "./tokens";
import { compressToolMessage } from "../memory/compressor";
import { normalizeMessage } from "../memory/ids";
import {
  latestContextVersion,
  listMemoryItems,
  resolveActiveConflicts,
} from "../memory/state";
import { MemoryStatus } from "../models/memory";
import type { MemoryAIAdapter } from "../providers/memory-ai";
import { contextVersions } from "../db/schema/context";

export interface CompileResult {
  messages: Array<Record<string, any>>;
  totalTokens: number;
  contextVersion?: number | null;
  canonicalItemsUsed: number;
  selectedCount: number;
  budget: number;
}

async function persistContextSnapshot(
  db: Database,
  conversationId: string,
  compiledMessages: Array<Record<string, any>>,
  options: {
    budget: number;
    totalTokens: number;
    canonicalCount: number;
    sourceMessageIds: string[];
  }
): Promise<number | null> {
  try {
    const nextVer = (await latestContextVersion(db, conversationId)) + 1;
    const stateData = {
      budget: options.budget,
      total_tokens: options.totalTokens,
      message_count: compiledMessages.length,
      canonical_items_count: options.canonicalCount,
    };
    await db.insert(contextVersions).values({
      conversationId,
      version: nextVer,
      stateJson: JSON.stringify(stateData),
      sourceMessageIdsJson: JSON.stringify(options.sourceMessageIds),
      createdAt: new Date().toISOString(),
    });
    return nextVer;
  } catch {
    return null;
  }
}

export async function compileContext(
  db: Database | null,
  messages: Array<Record<string, any>>,
  conversationId?: string | null,
  options?: {
    budget?: number;
    memoryAi?: MemoryAIAdapter | null;
    persistSnapshot?: boolean;
  }
): Promise<CompileResult> {
  const targetBudget = options?.budget || 8000;

  if (!messages || messages.length === 0) {
    return {
      messages: [],
      totalTokens: 0,
      budget: targetBudget,
      canonicalItemsUsed: 0,
      selectedCount: 0,
    };
  }

  try {
    let latestUserText = "";
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        latestUserText = String(messages[i].content || "");
        break;
      }
    }
    const queryKeywords = extractKeywords(latestUserText);

    let canonicalItems: any[] = [];
    if (db && conversationId) {
      try {
        const rawItems = await listMemoryItems(db, conversationId, MemoryStatus.ACTIVE);
        canonicalItems = resolveActiveConflicts(rawItems);
      } catch {}
    }

    const processedMessages: Array<Record<string, any>> = [];
    for (let idx = 0; idx < messages.length; idx++) {
      const m = messages[idx];
      const contentStr = String(m.content || "");
      if (m.role === "tool" && contentStr.length > 400) {
        let compressed = contentStr;
        if (options?.memoryAi) {
          try {
            const norm = normalizeMessage(m, idx);
            compressed = await compressToolMessage(norm, options.memoryAi);
          } catch {
            compressed = contentStr;
          }
        } else if (contentStr.length > 1000) {
          const lines = contentStr.split("\n");
          const head = lines.slice(0, 10).join("\n");
          compressed = `${head}\n... [tool output truncated for context budget: ${lines.length} lines total]`;
        }
        processedMessages.push({ ...m, content: compressed });
      } else {
        processedMessages.push(m);
      }
    }

    const candidates: SelectableItem[] = [];
    const totalMsgs = processedMessages.length;

    for (let idx = 0; idx < totalMsgs; idx++) {
      const isLatest = idx === totalMsgs - 1;
      const item = scoreMessageItem(processedMessages[idx], {
        index: idx,
        totalMessages: totalMsgs,
        queryKeywords,
        isLatest,
      });
      candidates.push(item);
    }

    for (let cIdx = 0; cIdx < canonicalItems.length; cIdx++) {
      const item = scoreCanonicalItem(canonicalItems[cIdx], {
        ordinal: 100000 + cIdx,
        queryKeywords,
      });
      candidates.push(item);
    }

    const currentTokens = estimateMessagesTokens(messages);
    if (canonicalItems.length === 0 && currentTokens <= targetBudget) {
      let versionNum: number | null = null;
      if (db && conversationId && options?.persistSnapshot !== false) {
        versionNum = await persistContextSnapshot(db, conversationId, messages, {
          budget: targetBudget,
          totalTokens: currentTokens,
          canonicalCount: 0,
          sourceMessageIds: messages.map((m, idx) => String(m.id || idx)),
        });
      }
      return {
        messages,
        totalTokens: currentTokens,
        contextVersion: versionNum,
        canonicalItemsUsed: 0,
        selectedCount: messages.length,
        budget: targetBudget,
      };
    }

    const selected = selectItemsForBudget(candidates, targetBudget);
    const compiledMessages = assembleContextMessages(selected, {
      hasCanonicalMemory: canonicalItems.length > 0,
    });

    const finalTokens = estimateMessagesTokens(compiledMessages);
    const canonicalUsed = selected.filter((s) => s.kind === "canonical_memory").length;

    let versionNum: number | null = null;
    if (db && conversationId && options?.persistSnapshot !== false) {
      const sourceIds = selected.map((s) => s.itemId);
      versionNum = await persistContextSnapshot(db, conversationId, compiledMessages, {
        budget: targetBudget,
        totalTokens: finalTokens,
        canonicalCount: canonicalUsed,
        sourceMessageIds: sourceIds,
      });
    }

    return {
      messages: compiledMessages,
      totalTokens: finalTokens,
      contextVersion: versionNum,
      canonicalItemsUsed: canonicalUsed,
      selectedCount: selected.length,
      budget: targetBudget,
    };
  } catch {
    return {
      messages,
      totalTokens: estimateMessagesTokens(messages),
      budget: targetBudget,
      canonicalItemsUsed: 0,
      selectedCount: messages.length,
    };
  }
}

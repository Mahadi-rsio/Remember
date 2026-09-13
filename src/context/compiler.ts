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
  resolveActiveConflicts,
} from "../memory/state";
import { retrieveActiveMemories, expandRelations } from "../memory/retrieve";
import type { ShortTermContextStore } from "../memory/context-store";
import type { MemoryAIAdapter } from "../providers/memory-ai";
import { contextVersions } from "../db/schema/context";

export interface CompileResult {
  messages: Array<Record<string, any>>;
  totalTokens: number;
  contextVersion?: number | null;
  canonicalItemsUsed: number;
  shortTermItemsUsed: number;
  selectedCount: number;
  budget: number;
}

async function persistContextSnapshot(
  db: Database,
  userId: string,
  compiledMessages: Array<Record<string, any>>,
  options: {
    budget: number;
    totalTokens: number;
    canonicalCount: number;
    sourceMessageIds: string[];
  }
): Promise<number | null> {
  try {
    const nextVer = (await latestContextVersion(db, userId)) + 1;
    const stateData = {
      budget: options.budget,
      total_tokens: options.totalTokens,
      message_count: compiledMessages.length,
      canonical_items_count: options.canonicalCount,
    };
    await db.insert(contextVersions).values({
      userId,
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
  userId?: string | null,
  options?: {
    budget?: number;
    memoryAi?: MemoryAIAdapter | null;
    persistSnapshot?: boolean;
    contextStore?: ShortTermContextStore | null;
  }
): Promise<CompileResult> {
  const targetBudget = options?.budget || 8000;

  if (!messages || messages.length === 0) {
    return {
      messages: [],
      totalTokens: 0,
      budget: targetBudget,
      canonicalItemsUsed: 0,
      shortTermItemsUsed: 0,
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
    let retrievedActive: any[] = [];
    if (db && userId) {
      try {
        // Lexical retrieval: pull the active long-term set narrowed by the
        // query keywords (OR match against content/value/predicate/subject),
        // then expand first-class relationships (supersedes/contradicts/
        // related) so we surface connected history without loading the whole
        // dataset. We deliberately do NOT hard-filter by scope: AI-extracted
        // scopes are unreliable, so a hard scope filter causes false negatives.
        retrievedActive = await retrieveActiveMemories(db, userId, {
          keywords: queryKeywords.size > 0 ? [...queryKeywords].slice(0, 6) : undefined,
          limit: 40,
        });

        const expanded = await expandRelations(db, userId, retrievedActive, {
          depth: 1,
          activeOnly: true,
          limit: 20,
        });
        const merged = new Map<number, any>();
        for (const item of [...retrievedActive, ...expanded]) {
          merged.set(item.id, item);
        }
        canonicalItems = resolveActiveConflicts(Array.from(merged.values()));
      } catch {}
    }

    // Short-term context from Redis (or in-memory store) — "what's happening right now?"
    let shortTermText = "";
    let shortTermItemsUsed = 0;
    const contextStore = options?.contextStore;
    if (contextStore && userId) {
      try {
        const ctx = await contextStore.getAllContext(userId);
        if (ctx && ctx.length > 0) {
          const lines = ctx.map((e) => `• ${e.key}: ${e.value}`);
          shortTermText = `[Short-Term Context (current state)]\n${lines.join("\n")}`;
          shortTermItemsUsed = ctx.length;
        }
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

    // Deterministic retrieval happened above (scope-first + relationship
    // expansion); `retrievedActive` holds the active long-term set.

    const currentTokens = estimateMessagesTokens(messages);
    if (retrievedActive.length === 0 && shortTermItemsUsed === 0 && currentTokens <= targetBudget) {
      let versionNum: number | null = null;
      if (db && userId && options?.persistSnapshot !== false) {
        versionNum = await persistContextSnapshot(db, userId, messages, {
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
        shortTermItemsUsed: 0,
        selectedCount: messages.length,
        budget: targetBudget,
      };
    }

    const selected = selectItemsForBudget(candidates, targetBudget);

    // Prepend the short-term context block to the assembled system prompt.
    let compiledMessages = assembleContextMessages(selected, {
      hasCanonicalMemory: retrievedActive.length > 0,
    });
    if (shortTermText) {
      const sysIdx = compiledMessages.findIndex((m) => m.role === "system");
      if (sysIdx !== -1) {
        const existing = String(compiledMessages[sysIdx].content || "");
        compiledMessages[sysIdx].content = `${existing}\n\n${shortTermText}`.trim();
      } else {
        compiledMessages.unshift({ role: "system", content: shortTermText });
      }
    }

    const finalTokens = estimateMessagesTokens(compiledMessages);
    const canonicalUsed = selected.filter((s) => s.kind === "canonical_memory").length;

    let versionNum: number | null = null;
    if (db && userId && options?.persistSnapshot !== false) {
      const sourceIds = selected.map((s) => s.itemId);
      versionNum = await persistContextSnapshot(db, userId, compiledMessages, {
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
      shortTermItemsUsed,
      selectedCount: selected.length,
      budget: targetBudget,
    };
  } catch {
    return {
      messages,
      totalTokens: estimateMessagesTokens(messages),
      budget: targetBudget,
      canonicalItemsUsed: 0,
      shortTermItemsUsed: 0,
      selectedCount: messages.length,
    };
  }
}

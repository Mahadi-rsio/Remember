import {
  type CandidateMemory,
  type MemoryAIOutput,
  MemoryType,
} from "../models/memory";
import type { NormalizedMessage } from "./ids";
import { topicKeyFromContent } from "./extractor";
import { scoreCandidate } from "./scorer";
import type { MemoryAIAdapter } from "../providers/memory-ai";

export function memoryAiOutputToCandidates(
  output: MemoryAIOutput,
  sourceMessageIds: string[]
): CandidateMemory[] {
  const candidates: CandidateMemory[] = [];
  const typeMapping: Array<[string[], MemoryType]> = [
    [output.facts, MemoryType.FACT],
    [output.decisions, MemoryType.DECISION],
    [output.constraints, MemoryType.CONSTRAINT],
    [output.preferences, MemoryType.PREFERENCE],
    [output.goals, MemoryType.GOAL],
    [output.architecture, MemoryType.ARCHITECTURE],
    [output.important_events, MemoryType.IMPORTANT_EVENT],
    [output.active_tasks, MemoryType.ACTIVE_TASK],
  ];

  for (const [items, mtype] of typeMapping) {
    for (const text of items) {
      const cleaned = text.trim();
      if (!cleaned) continue;
      const topic = topicKeyFromContent(cleaned, mtype);
      const candidate: CandidateMemory = {
        content: cleaned,
        type: mtype,
        scores: {
          confidence: 0,
          importance: 0,
          stability: 0,
          freshness: 1,
          informationGain: 0,
        },
        sourceMessageIds: [...sourceMessageIds],
        topicKey: topic,
        authority: "user",
        isCorrection: false,
      };
      const scores = scoreCandidate(candidate);
      scores.confidence = Math.min(1.0, Math.max(0.0, output.confidence * Math.max(0.85, scores.confidence)));
      scores.informationGain = Math.max(0.5, scores.informationGain);
      candidate.scores = scores;
      candidates.push(candidate);
    }
  }

  return candidates;
}

export async function compressToolMessage(
  message: NormalizedMessage,
  adapter?: MemoryAIAdapter | null
): Promise<string> {
  if (message.role !== "tool") {
    return message.content;
  }

  const toolName =
    message.raw.name || message.raw.tool_name || message.raw.tool_call_id || "tool";

  if (!adapter) {
    return message.content;
  }

  try {
    return await adapter.compressToolOutput(String(toolName), message.content);
  } catch {
    return message.content;
  }
}

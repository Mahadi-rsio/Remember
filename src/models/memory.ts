/**
 * Canonical memory schema: types, statuses, scores, and candidates.
 */

export enum MemoryType {
  FACT = "fact",
  DECISION = "decision",
  CONSTRAINT = "constraint",
  PREFERENCE = "preference",
  GOAL = "goal",
  ARCHITECTURE = "architecture",
  IMPORTANT_EVENT = "important_event",
  ACTIVE_TASK = "active_task",
}

export const CANONICAL_TYPES: MemoryType[] = Object.values(MemoryType);

export enum MemoryStatus {
  ACTIVE = "active",
  SUPERSEDED = "superseded",
  REVOKED = "revoked",
  EXPIRED = "expired",
  OBSOLETE = "obsolete",
}

export interface MemoryScores {
  confidence: number;
  importance: number;
  stability: number;
  freshness: number;
  informationGain: number;
}

export function defaultMemoryScores(): MemoryScores {
  return {
    confidence: 0.0,
    importance: 0.0,
    stability: 0.0,
    freshness: 1.0,
    informationGain: 0.0,
  };
}

export interface StructuredFact {
  entity: string;
  attribute: string;
  value: string;
  memoryType: MemoryType;
  rawText: string;
}

export interface Correction {
  target: string;
  oldValue: string;
  newValue: string;
}

export interface Revocation {
  target: string;
  value: string;
}

export interface CandidateMemory {
  content: string;
  type: MemoryType;
  scores: MemoryScores;
  sourceMessageIds: string[];
  topicKey: string;
  authority: "user" | "assistant" | "speculation";
  isCorrection: boolean;
  structuredFact?: StructuredFact | null;
  correction?: Correction | null;
  revocation?: Revocation | null;
}

export interface CanonicalMemorySnapshot {
  facts: string[];
  decisions: string[];
  constraints: string[];
  preferences: string[];
  goals: string[];
  architecture: string[];
  importantEvents: string[];
  activeTasks: string[];
}

export function createEmptySnapshot(): CanonicalMemorySnapshot {
  return {
    facts: [],
    decisions: [],
    constraints: [],
    preferences: [],
    goals: [],
    architecture: [],
    importantEvents: [],
    activeTasks: [],
  };
}

export function snapshotFromItems(items: Array<{ type: string; content: string }>): CanonicalMemorySnapshot {
  const snapshot = createEmptySnapshot();
  for (const item of items) {
    if (!item.content) continue;
    switch (item.type) {
      case MemoryType.FACT:
        snapshot.facts.push(item.content);
        break;
      case MemoryType.DECISION:
        snapshot.decisions.push(item.content);
        break;
      case MemoryType.CONSTRAINT:
        snapshot.constraints.push(item.content);
        break;
      case MemoryType.PREFERENCE:
        snapshot.preferences.push(item.content);
        break;
      case MemoryType.GOAL:
        snapshot.goals.push(item.content);
        break;
      case MemoryType.ARCHITECTURE:
        snapshot.architecture.push(item.content);
        break;
      case MemoryType.IMPORTANT_EVENT:
        snapshot.importantEvents.push(item.content);
        break;
      case MemoryType.ACTIVE_TASK:
        snapshot.activeTasks.push(item.content);
        break;
    }
  }
  return snapshot;
}

export interface MemoryAIOutput {
  summary: string;
  facts: string[];
  decisions: string[];
  constraints: string[];
  preferences: string[];
  goals: string[];
  architecture: string[];
  important_events: string[];
  active_tasks: string[];
  obsolete_items: string[];
  contradictions: string[];
  confidence: number;
}

export interface ToolSummaryOutput {
  summary: string;
  key_points: string[];
  status: "success" | "error" | "warning";
}

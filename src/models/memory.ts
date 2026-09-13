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
  TEMPORARY_STATE = "temporary_state",
}

export const CANONICAL_TYPES: MemoryType[] = Object.values(MemoryType);

export enum MemoryStatus {
  ACTIVE = "active",
  SUPERSEDED = "superseded",
  REVOKED = "revoked",
  EXPIRED = "expired",
  OBSOLETE = "obsolete",
}

/**
 * First-class relationship kinds between memory items. Recorded on the
 * `relationship` column (the relation this item holds toward `supersedesId`)
 * and in the JSON id-list columns (`contradictsIdsJson`,
 * `relatedMemoryIdsJson`).
 */
export enum MemoryRelationship {
  SUPPORTS = "supports",
  CONTRADICTS = "contradicts",
  SUPERSEDES = "supersedes",
  DERIVED_FROM = "derived_from",
  RELATED_TO = "related_to",
  REVOKES = "revokes",
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

export type FactScope = "user" | "project" | "session";

/** Three-way classification from the Memory Analyzer. */
export enum MemoryBucket {
  STORE = "store",
  CONTEXT = "context",
  DISCARD = "discard",
}

/** Short-term context entry stored in Redis / ephemeral store. */
export interface ContextEntry {
  key: string;
  value: string;
  /** Seconds from write time before the entry expires. 0 = no expiry. */
  ttlSeconds?: number;
  createdAt?: string;
}

export interface StructuredFact {
  entity: string;
  attribute: string;
  value: string;
  memoryType: MemoryType;
  rawText: string;
  /** Stable structured key such as "user.name" or "project.database". */
  key?: string;
  /** USER / PROJECT / SESSION. Derived from the key prefix when not set. */
  scope?: FactScope;
  /** True when this fact is an explicit update of a previous value. */
  isUpdate?: boolean;
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
  /** Classification decided by the Memory Analyzer. */
  bucket?: MemoryBucket;
  subject?: string;
  predicate?: string;
  value?: string;
  scope?: FactScope;
  /** ISO timestamp of when this candidate becomes/claims to be valid. */
  validFrom?: string | null;
  /** ISO timestamp after which this candidate should no longer be treated as current. */
  validUntil?: string | null;
  structuredFact?: StructuredFact | null;
  correction?: Correction | null;
  revocation?: Revocation | null;
  /** Relationship this candidate holds toward an existing memory item. */
  relationship?: MemoryRelationship | null;
  /** Id of the memory item this candidate is derived from / related to. */
  relatedToId?: number | null;
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
      case MemoryType.TEMPORARY_STATE:
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

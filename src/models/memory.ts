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

/**
 * Temporal / modality state of a fact. "usage/current" when omitted for
 * backwards compatibility with facts that have no explicit state.
 */
export type FactState =
  | "current"
  | "past"
  | "planned"
  | "possible"
  | "conditional"
  | "stopped"
  | "superseded";

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
  /** Temporal / modality state (current, past, planned, possible, …). */
  state?: FactState;
  /** Local extraction confidence 0..1 (undefined → treat as implicit). */
  confidence?: number;
  /** Optional metadata: comparison target ("over"), causal reason, etc. */
  metadata?: Record<string, string>;
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

export interface MemoryAICandidate {
  action: "NEW" | "REINFORCE" | "SUPERSEDES" | "CONTRADICTS" | "UPDATE" | "DISCARD";
  destination: "STORE" | "CONTEXT" | "DISCARD";
  type: string;
  scope: "USER" | "PROJECT" | "SESSION";
  subject: string;
  predicate: string;
  value: string;
  topicKey: string;
  confidence: number;
  importance: number;
  stability: "permanent" | "long-term" | "short-term" | "session";
  ttl_hours: number | null;
  supersedes_id: string | null;
  reinforces_id: string | null;
  informationGain: number;
  rawText: string;
}

/** Validated Memory AI extraction result (array of structured candidates). */
export interface MemoryAIOutput {
  candidates: MemoryAICandidate[];
  /** Derived from SUPERSEDES / CONTRADICTS for engine obsolete marking. */
  obsolete_items: string[];
}

/** One consolidated memory produced by the consolidation engine. */
export interface ConsolidatedMemory {
  type: string;
  scope: "USER" | "PROJECT" | "SESSION";
  subject: string;
  predicate: string;
  value: string | Record<string, unknown>;
  topicKey: string;
  confidence: number;
  importance: number;
  stability: "permanent" | "long-term" | "short-term" | "session";
  sourceMemoryIds: string[];
  consolidationNote?: string;
}

export interface ConsolidationConflict {
  memory_ids: string[];
  description: string;
  resolution: string;
}

/** Result of consolidating one related memory cluster. */
export interface ConsolidationResult {
  consolidated: ConsolidatedMemory[];
  superseded_ids: string[];
  conflicts_detected: ConsolidationConflict[];
}

export interface ToolSummaryOutput {
  summary: string;
  key_points: string[];
  status: "success" | "error" | "warning";
}

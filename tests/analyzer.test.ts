import { describe, expect, it } from "bun:test";
import {
  analyzeCandidates,
  classifyCandidate,
  deriveContextKey,
  deriveStructuredFields,
} from "../src/memory/analyzer";
import {
  MemoryBucket,
  MemoryType,
  type CandidateMemory,
} from "../src/models/memory";

function candidate(partial: Partial<CandidateMemory>): CandidateMemory {
  return {
    content: "placeholder",
    type: MemoryType.FACT,
    scores: {
      confidence: 0.8,
      importance: 0.7,
      stability: 0.6,
      freshness: 1,
      informationGain: 0.8,
    },
    sourceMessageIds: ["msg-1"],
    topicKey: "project.database",
    authority: "user",
    isCorrection: false,
    ...partial,
  };
}

describe("Memory Analyzer classification", () => {
  it("classifies durable identity facts as store", () => {
    const c = candidate({ content: "My name is Mahadi" });
    expect(classifyCandidate(c)).toBe(MemoryBucket.STORE);
  });

  it("classifies durable technology facts as store", () => {
    const c = candidate({ content: "I use Hono for this project" });
    expect(classifyCandidate(c)).toBe(MemoryBucket.STORE);
  });

  it("classifies currently-debugging statements as context", () => {
    const c = candidate({ content: "I'm currently debugging an authentication bug" });
    expect(classifyCandidate(c)).toBe(MemoryBucket.CONTEXT);
  });

  it("classifies current error state as context", () => {
    const c = candidate({ content: "The current error is 401" });
    expect(classifyCandidate(c)).toBe(MemoryBucket.CONTEXT);
  });

  it("routes context candidates to the right context key", () => {
    expect(deriveContextKey(candidate({ content: "The error is 401" }))).toBe(
      "current_error"
    );
    expect(
      deriveContextKey(candidate({ content: "I'm debugging auth" }))
    ).toBe("active_debugging_context");
    expect(
      deriveContextKey(candidate({ content: "Working on the checkout flow" }))
    ).toBe("current_task");
  });

  it("derives structured fields from a structured fact", () => {
    const c = candidate({
      content: "Database: Neon",
      structuredFact: {
        entity: "project",
        attribute: "database",
        value: "Neon",
        memoryType: MemoryType.DECISION,
        rawText: "project uses Neon",
        key: "project.database",
        scope: "project",
      },
    });
    const fields = deriveStructuredFields(c);
    expect(fields.subject).toBe("project");
    expect(fields.predicate).toBe("database");
    expect(fields.value).toBe("Neon");
    expect(fields.scope).toBe("project");
  });

  it("runs analyzeCandidates splitting store/context/discard", () => {
    const result = analyzeCandidates([
      candidate({ content: "My name is Mahadi" }),
      candidate({ content: "Currently debugging auth", type: MemoryType.ACTIVE_TASK }),
      candidate({ content: "haha" }),
    ]);
    expect(result.store.map((c) => c.content)).toEqual(["My name is Mahadi"]);
    expect(result.context.map((c) => c.content)).toEqual(["Currently debugging auth"]);
    expect(result.discard.map((c) => c.content)).toEqual(["haha"]);
    expect(result.contextEntries.length).toBeGreaterThan(0);
    expect(result.contextEntries[0].ttlSeconds).toBeGreaterThan(0);
  });

  it("assigns a TTL to context entries", () => {
    const result = analyzeCandidates([
      candidate({ content: "The current error is 401" }),
    ]);
    expect(result.contextEntries[0].ttlSeconds).toBe(3600);
  });
});

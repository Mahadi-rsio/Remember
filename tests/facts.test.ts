import { describe, expect, it } from "bun:test";
import {
  extractStructuredFact,
  extractStructuredFacts,
  extractUsesList,
  splitSentences,
  detectPreferenceDomain,
} from "../src/memory/facts";
import { MemoryType } from "../src/models/memory";

describe("Deterministic Fact Extraction", () => {
  it("extracts building project statement", () => {
    const fact = extractStructuredFact("I am building an AI Memory Gateway called Remember");
    expect(fact).not.toBeNull();
    expect(fact?.entity).toBe("Remember");
    expect(fact?.attribute).toBe("project");
    expect(fact?.value).toBe("Remember");
    expect(fact?.memoryType).toBe(MemoryType.FACT);
  });

  it("extracts technology decision with uses", () => {
    const fact = extractStructuredFact("Cloudisy uses Neon for database");
    expect(fact).not.toBeNull();
    expect(fact?.entity).toBe("Cloudisy");
    expect(fact?.attribute).toBe("database");
    expect(fact?.memoryType).toBe(MemoryType.DECISION);
  });

  it("extracts user preferences", () => {
    const fact = extractStructuredFact("I prefer Tailwind over Bootstrap");
    expect(fact).not.toBeNull();
    expect(fact?.entity).toBe("user");
    expect(fact?.attribute).toBe("ui_library");
    expect(fact?.memoryType).toBe(MemoryType.PREFERENCE);
  });

  it("extracts affect preferences (love/like/hate)", () => {
    const cases: Array<[string, string, string]> = [
      ["I love red", "favorite_color", "red"],
      ["I really like TypeScript", "language", "TypeScript"],
      ["I hate MongoDB", "disliked_database", "MongoDB"],
      ["I love blue now", "favorite_color", "blue"],
      ["My favorite colour is green", "favorite_color", "green"],
      ["My preferred database is Neon", "preferred_database", "Neon"],
    ];
    for (const [phrase, predicate, value] of cases) {
      const fact = extractStructuredFact(phrase);
      expect(fact).not.toBeNull();
      expect(fact?.memoryType).toBe(MemoryType.PREFERENCE);
      expect(fact?.scope).toBe("user");
      expect(fact?.entity).toBe("user");
      expect(fact?.attribute).toBe(predicate);
      expect(fact?.value).toBe(value);
    }
  });

  it("does not extract reaction / discourse preferences", () => {
    expect(extractStructuredFact("I love this response")).toBeNull();
    expect(extractStructuredFact("I like how you explained that")).toBeNull();
    expect(extractStructuredFact("I love this")).toBeNull();
  });

  it("detects color preference domain (excluding rust)", () => {
    expect(detectPreferenceDomain("red")).toEqual([
      "favorite_color",
      "preference:favorite_color",
    ]);
    expect(detectPreferenceDomain("rust")[0]).toBe("language");
  });

  it("extracts possessive statements", () => {
    const fact = extractStructuredFact("Cloudisy's architecture is event-driven microservices");
    expect(fact).not.toBeNull();
    expect(fact?.entity).toBe("Cloudisy");
    expect(fact?.attribute).toBe("architecture");
    expect(fact?.memoryType).toBe(MemoryType.ARCHITECTURE);
  });

  it("splits messages into atomic sentences", () => {
    const sentences = splitSentences(
      "I am building a project called Remember. It uses Cloudflare Workers with Hono, Turso as the database."
    );
    expect(sentences).toHaveLength(2);
    expect(sentences[0]).toContain("Remember");
    expect(sentences[1]).toContain("Turso");
  });

  it("does not split on commas within a clause list", () => {
    const sentences = splitSentences("It uses Cloudflare Workers, Hono, and Turso as the database.");
    expect(sentences).toHaveLength(1);
  });

  it("extracts multiple atomic facts from a multi-clause uses statement", () => {
    const facts = extractUsesList(
      "It uses Cloudflare Workers with Hono, Turso as the database, Upstash Redis for caching, and Groq for summarization."
    );
    expect(facts.length).toBeGreaterThanOrEqual(4);
    const byKey = new Map(facts.map((f) => [f.key, f]));
    expect(byKey.get("project.database")?.value).toContain("Turso");
    expect(byKey.get("project.runtime")?.value).toContain("Cloudflare Workers");
    expect(byKey.get("project.framework")?.value).toContain("Hono");
    expect(byKey.get("project.summarization")?.value).toContain("Groq");
  });

  it("extracts structured facts from a full multi-fact message", () => {
    const facts = extractStructuredFacts(
      "I am building an AI memory gateway called Remember. It uses Cloudflare Workers with Hono, Turso as the database."
    );
    expect(facts.length).toBeGreaterThanOrEqual(4);
    const keys = new Set(facts.map((f) => f.key));
    expect(keys.has("project.name")).toBe(true);
    expect(keys.has("project.database")).toBe(true);
  });
});

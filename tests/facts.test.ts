import { describe, expect, it, afterEach } from "bun:test";
import {
  extractStructuredFact,
  extractStructuredFacts,
  extractUsesList,
  splitSentences,
  splitSentencesByBoundary,
  detectPreferenceDomain,
  shouldConsiderMemory,
  extractLocalFacts,
  extractStructuredFactsHybrid,
  createGroqExtractor,
  applyLocalSemanticValidation,
  mergeFacts,
  GROQ_FACT_SCHEMA,
  type GroqFactInput,
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

describe("Memory Gate (shouldConsiderMemory)", () => {
  it("skips greetings and acknowledgements", () => {
    for (const t of ["hey there!", "Hello.", "ok", "thanks!", "Ok great thanks", "nope"]) {
      const g = shouldConsiderMemory(t);
      expect(g.candidateKinds).toHaveLength(0);
      expect(g.reasons.some((r) => r === "greeting_or_acknowledgement" || r === "low_info")).toBe(true);
    }
  });

  it("skips pure questions", () => {
    const g = shouldConsiderMemory("What is the capital of France?");
    expect(g.candidateKinds).toHaveLength(0);
  });

  it("does NOT treat first-person statements as low-info (substring regression)", () => {
    // These contain low-info substrings ("k" in workers, "no" in now) but are real memories
    const g1 = shouldConsiderMemory("I use Cloudflare Workers with D1 for storage.");
    expect(g1.candidateKinds).toContain("usage");

    const g2 = shouldConsiderMemory("I used to use Supabase but now I use Neon Postgres.");
    expect(g2.candidateKinds.length).toBeGreaterThan(0);
  });

  it("routes explicit usage locally without Groq", () => {
    const g = shouldConsiderMemory("I use Cloudflare Workers with D1 for storage.");
    expect(g.candidateKinds).toContain("usage");
  });

  it("routes identity statements to Groq (ambiguous)", () => {
    const g = shouldConsiderMemory("I am Mahadi Hasan");
    expect(g.shouldCallGroq).toBe(true);
    expect(g.candidateKinds).toContain("ambiguous");
  });
});

describe("Clause Splitting", () => {
  it("splits contrast clauses on 'but now'", () => {
    const parts = splitSentencesByBoundary("I used to use Supabase but now I use Neon Postgres.");
    expect(parts).toHaveLength(2);
    expect(parts[0]).toContain("Supabase");
    expect(parts[1]).toContain("Neon Postgres");
  });

  it("splits comma-separated first-person clauses", () => {
    const parts = splitSentencesByBoundary("I don't like MongoDB anymore, I stopped using it last year.");
    expect(parts.length).toBeGreaterThanOrEqual(2);
  });

  it("does not split comma lists", () => {
    const parts = splitSentencesByBoundary("I use React, Vue and Svelte at work.");
    expect(parts).toHaveLength(1);
  });
});

describe("Hybrid Local Extraction", () => {
  it("extracts identity, ownership and usage facts locally", () => {
    const facts = extractLocalFacts("My name is Mahadi. I use Cloudflare Workers.");
    const kinds = facts.map((f) => f.fact?.attribute);
    expect(kinds).toContain("name");
  });

  it("splits past vs current usage into separate facts with states", () => {
    const facts = extractLocalFacts("I used to use Supabase but now I use Neon Postgres.")
      .map((r) => r.fact)
      .filter((f): f is NonNullable<typeof f> => f !== null);

    const past = facts.find((f) => f.state === "past");
    const current = facts.find((f) => f.state === "current");
    expect(past?.value).toBe("Supabase");
    expect(current?.value).toBe("Neon Postgres");
  });

  it("extracts dislike without 'anymore' residue", () => {
    const facts = extractLocalFacts("I don't like MongoDB anymore, I stopped using it last year.")
      .map((r) => r.fact)
      .filter((f): f is NonNullable<typeof f> => f !== null);

    const dislike = facts.find((f) => f.attribute === "dislike");
    expect(dislike?.value).toBe("MongoDB");
  });

  it("extracts goals, plans, possible plans and decisions", () => {
    const goal = extractLocalFacts("I want to use GraphQL for my next project.").map((r) => r.fact);
    expect(goal[0]?.memoryType).toBe(MemoryType.GOAL);
    expect(goal[0]?.state).toBe("planned");

    const plan = extractLocalFacts("I plan to migrate to Bun.").map((r) => r.fact);
    expect(plan[0]?.state).toBe("planned");

    const possible = extractLocalFacts("I might switch to Deno later.").map((r) => r.fact);
    expect(possible[0]?.state).toBe("possible");

    const decision = extractLocalFacts("I decided to use Hono for routing.").map((r) => r.fact);
    expect(decision[0]?.memoryType).toBe(MemoryType.DECISION);
  });

  it("skips non-memory messages entirely without calling Groq", async () => {
    const originalFetch = globalThis.fetch;
    let called = false;
    globalThis.fetch = (async () => {
      called = true;
      throw new Error("Groq must not be called");
    }) as typeof fetch;
    try {
      const res = await extractStructuredFactsHybrid("hey there, thanks!", {
        groqApiKey: "fake-key-for-test",
      });
      expect(res.route).toBe("skip");
      expect(res.facts).toHaveLength(0);
      expect(called).toBe(false);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("forceLocal returns local facts without Groq", async () => {
    const res = await extractStructuredFactsHybrid("I prefer Material UI over Ant Design.", {
      forceLocal: true,
      groqApiKey: "fake-key-for-test",
    });
    expect(res.route).toBe("local");
    expect(res.facts.length).toBeGreaterThan(0);
  });
});

// ---- Groq mock helpers ----

type FetchMock = (input: string | URL | Request, init?: RequestInit) => Response | Promise<Response>;

function groqResponse(content: string): Response {
  return new Response(
    JSON.stringify({
      id: "test",
      object: "chat.completion",
      created: 0,
      model: "openai/gpt-oss-20b",
      choices: [{ index: 0, message: { role: "assistant", content }, finish_reason: "stop" }],
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

function mockFetch(content: string | null, capture?: { body?: string[] }): typeof fetch {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url.includes("groq")) {
      if (capture) capture.body?.push(String(init?.body ?? ""));
      return groqResponse(content ?? "{}");
    }
    return globalThis.fetch(input as RequestInfo, init);
  }) as typeof fetch;
}

describe("Groq Integration (mocked HTTP)", () => {
  it("validates scope null → user, maps types and sets rawText to source", async () => {
    const ex = createGroqExtractor({ baseUrl: "https://api.groq.com/openai/v1", apiKey: "k", fetchImpl: mockFetch(JSON.stringify({
      facts: [
        { entity: "Mahadi Hasan", attribute: "name", value: "Mahadi Hasan", type: "identity", state: "current", scope: null, confidence: 1.0 },
      ],
    })) });
    const facts = await ex.extract("I am Mahadi Hasan.");
    expect(facts).toHaveLength(1);
    expect(facts[0].scope).toBe("user");
    expect(facts[0].key).toBe("user.name");
    expect(facts[0].memoryType).toBe(MemoryType.FACT);
    expect(facts[0].rawText).toBe("I am Mahadi Hasan.");
  });

  it("rejects invalid confidence and unknown types", async () => {
    const ex = createGroqExtractor({ baseUrl: "https://api.groq.com/openai/v1", apiKey: "k", fetchImpl: mockFetch(JSON.stringify({
      facts: [
        { entity: "a", attribute: "b", value: "c", type: "identity", state: "current", scope: null, confidence: 2.5 },
        { entity: "a", attribute: "b", value: "c", type: "alien_concept", state: "current", scope: null, confidence: 0.9 },
      ],
    })) });
    const facts = await ex.extract("test input");
    expect(facts).toHaveLength(0);
  });

  it("local validation blocks 'I don't like MongoDB' from becoming current usage", async () => {
    const res = await extractStructuredFactsHybrid("I don't like MongoDB anymore.", {
      groqApiKey: "fake",
      groqBaseUrl: "https://api.groq.com/openai/v1",
      fetchImpl: mockFetch(JSON.stringify({
        facts: [
          { entity: "user", attribute: "technology", value: "MongoDB", type: "usage", state: "current", scope: null, confidence: 0.99 },
        ],
      })),
    });
    const usage = res.facts.filter((f) => f.attribute === "technology" && f.state === "current");
    expect(usage).toHaveLength(0);
  });

  it("falls back to local facts when Groq fails", async () => {
    const res = await extractStructuredFactsHybrid("I prefer Material UI over Ant Design.", {
      groqApiKey: "fake",
      groqBaseUrl: "https://api.groq.com/openai/v1",
      fetchImpl: (async () => {
        throw new Error("network down");
      }) as typeof fetch,
    });
    expect(res.route).toBe("local");
    expect(res.facts.length).toBeGreaterThan(0);
  });

  it("merges and deduplicates local + Groq facts", async () => {
    const res = await extractStructuredFactsHybrid("I prefer Material UI over Ant Design and I use Neovim.", {
      groqApiKey: "fake",
      groqBaseUrl: "https://api.groq.com/openai/v1",
      fetchImpl: mockFetch(JSON.stringify({
        facts: [
          { entity: "user", attribute: "preference", value: "Material UI over Ant Design", type: "preference", state: "current", scope: null, confidence: 0.9 },
          { entity: "user", attribute: "editor", value: "Neovim", type: "usage", state: "current", scope: null, confidence: 0.9 },
        ],
      })),
    });
    const editorFacts = res.facts.filter((f) => f.value === "Neovim");
    expect(editorFacts).toHaveLength(1);
  });

  it("deduplicates facts via mergeFacts helper", () => {
    const fact = {
      entity: "user",
      attribute: "technology",
      value: "Neon",
      memoryType: MemoryType.FACT,
      rawText: "t",
      key: "user.technology",
      scope: "user" as const,
      state: "current" as const,
      confidence: 0.9,
    };
    const merged = mergeFacts([fact], [{ ...fact, confidence: 0.8 }]);
    expect(merged).toHaveLength(1);
  });

  it("exposes a strict schema", () => {
    expect(GROQ_FACT_SCHEMA.additionalProperties).toBe(false);
    const items = (GROQ_FACT_SCHEMA.properties.facts as { items: { additionalProperties: boolean } }).items;
    expect(items.additionalProperties).toBe(false);
  });
});

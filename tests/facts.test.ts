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
  CANONICAL_ATTRIBUTES,
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

function groqFact(partial: Record<string, unknown>) {
  return {
    entity: "user",
    attribute: "name",
    value: "x",
    type: "identity",
    state: "current",
    scope: null,
    confidence: 0.9,
    rawText: "",
    metadata: { preferred_over: null, condition: null, reason: null },
    ...partial,
  };
}

const MEMORYBOX_MESSAGE = [
  "My name is Alex.",
  "I am a full-stack developer.",
  "I am building a project called MemoryBox.",
  "I use Cloudflare Workers with D1 and Redis for MemoryBox.",
  "I used MongoDB.",
  "I stopped using Firebase because of pricing.",
  "I prefer MUI over shadcn.",
  "I don't like Bootstrap.",
  "I avoid Bootstrap.",
  "I plan to use Neon.",
  "I might switch to PlanetScale if latency is high.",
  "I am experimenting with Bun.",
  "What do you think about Redis?",
].join(" ");

describe("Groq Integration (mocked HTTP)", () => {
  it("forces entity=user for identity and keeps clause-level rawText", async () => {
    const ex = createGroqExtractor({
      baseUrl: "https://api.groq.com/openai/v1",
      apiKey: "k",
      fetchImpl: mockFetch(
        JSON.stringify({
          facts: [
            groqFact({
              entity: "Mahadi Hasan",
              attribute: "name",
              value: "Mahadi Hasan",
              type: "identity",
              state: "current",
              scope: null,
              confidence: 1.0,
              rawText: "I am Mahadi Hasan.",
            }),
          ],
        }),
      ),
    });
    const facts = await ex.extract("I am Mahadi Hasan.");
    expect(facts).toHaveLength(1);
    expect(facts[0].entity).toBe("user");
    expect(facts[0].scope).toBe("user");
    expect(facts[0].key).toBe("user.name");
    expect(facts[0].memoryType).toBe(MemoryType.FACT);
    expect(facts[0].rawText).toBe("I am Mahadi Hasan.");
  });

  it("rejects invalid confidence, unknown types, and invented attributes", async () => {
    const ex = createGroqExtractor({
      baseUrl: "https://api.groq.com/openai/v1",
      apiKey: "k",
      fetchImpl: mockFetch(
        JSON.stringify({
          facts: [
            groqFact({ entity: "a", attribute: "name", value: "c", type: "identity", confidence: 2.5 }),
            groqFact({ entity: "a", attribute: "name", value: "c", type: "alien_concept", confidence: 0.9 }),
            groqFact({
              entity: "user",
              attribute: "favorite_snack",
              value: "chips",
              type: "identity",
              confidence: 0.9,
              rawText: "I like chips",
            }),
          ],
        }),
      ),
    });
    const facts = await ex.extract("I like chips");
    expect(facts).toHaveLength(0);
  });

  it("local validation blocks 'I don't like MongoDB' from becoming current uses", async () => {
    const message = "I don't like MongoDB anymore.";
    const res = await extractStructuredFactsHybrid(message, {
      groqApiKey: "fake",
      groqBaseUrl: "https://api.groq.com/openai/v1",
      forceGroq: true,
      fetchImpl: mockFetch(
        JSON.stringify({
          facts: [
            groqFact({
              entity: "user",
              attribute: "uses",
              value: "MongoDB",
              type: "usage",
              state: "current",
              scope: null,
              confidence: 0.99,
              rawText: message,
            }),
          ],
        }),
      ),
    });
    const usage = res.facts.filter((f) => f.attribute === "uses" && f.state === "current");
    expect(usage).toHaveLength(0);
    expect(res.facts.some((f) => f.attribute === "dislike" && /mongodb/i.test(f.value))).toBe(true);
  });

  it("splits project stack into atomic uses facts", async () => {
    const message = "I use Cloudflare Workers with D1 and Redis for my project";
    const ex = createGroqExtractor({
      baseUrl: "https://api.groq.com/openai/v1",
      apiKey: "k",
      fetchImpl: mockFetch(
        JSON.stringify({
          facts: [
            groqFact({
              entity: "Mahadi",
              attribute: "uses",
              value: "Cloudflare Workers with D1 and Redis",
              type: "usage",
              state: "current",
              scope: "user",
              confidence: 0.95,
              rawText: message,
            }),
          ],
        }),
      ),
    });
    const facts = await ex.extract(message);
    expect(facts.length).toBeGreaterThanOrEqual(3);
    expect(facts.every((f) => f.entity !== "Mahadi")).toBe(true);
    expect(facts.every((f) => f.attribute === "uses")).toBe(true);
    expect(facts.every((f) => f.scope === "project")).toBe(true);
    const values = facts.map((f) => f.value.toLowerCase());
    expect(values.some((v) => v.includes("cloudflare") || v.includes("workers"))).toBe(true);
    expect(values.some((v) => v.includes("d1"))).toBe(true);
    expect(values.some((v) => v.includes("redis"))).toBe(true);
  });

  it("keeps preference comparisons in preferred_over metadata", async () => {
    const message = "I prefer MUI over shadcn.";
    const ex = createGroqExtractor({
      baseUrl: "https://api.groq.com/openai/v1",
      apiKey: "k",
      fetchImpl: mockFetch(
        JSON.stringify({
          facts: [
            groqFact({
              attribute: "preference",
              value: "MUI over shadcn",
              type: "preference",
              state: "current",
              confidence: 0.95,
              rawText: message,
            }),
          ],
        }),
      ),
    });
    const facts = await ex.extract(message);
    expect(facts).toHaveLength(1);
    expect(facts[0].entity).toBe("user");
    expect(facts[0].attribute).toBe("preference");
    expect(facts[0].value.toLowerCase()).toBe("mui");
    expect(facts[0].value.toLowerCase().includes("over")).toBe(false);
    expect(facts[0].metadata?.preferred_over?.toLowerCase()).toContain("shadcn");
  });

  it("normalizes past/stopped/plan states and conditional metadata", async () => {
    const message =
      "I used MongoDB. I stopped using Firebase because of pricing. I plan to use Neon. I might use Redis if latency is high.";
    const ex = createGroqExtractor({
      baseUrl: "https://api.groq.com/openai/v1",
      apiKey: "k",
      fetchImpl: mockFetch(
        JSON.stringify({
          facts: [
            groqFact({
              attribute: "uses",
              value: "MongoDB",
              type: "past_usage",
              state: "past",
              rawText: "I used MongoDB.",
            }),
            groqFact({
              attribute: "uses",
              value: "Firebase",
              type: "stopped_usage",
              state: "stopped",
              rawText: "I stopped using Firebase because of pricing.",
              metadata: { preferred_over: null, condition: null, reason: "pricing" },
            }),
            groqFact({
              attribute: "plan",
              value: "Neon",
              type: "plan",
              state: "planned",
              rawText: "I plan to use Neon.",
            }),
            groqFact({
              attribute: "plan",
              value: "Redis",
              type: "possible_plan",
              state: "conditional",
              rawText: "I might use Redis if latency is high.",
              metadata: {
                preferred_over: null,
                condition: "latency is high",
                reason: null,
              },
            }),
            groqFact({
              attribute: "goal",
              value: "latency is high",
              type: "goal",
              state: "current",
              rawText: "if latency is high",
            }),
          ],
        }),
      ),
    });
    const facts = await ex.extract(message);
    expect(facts.find((f) => f.value === "MongoDB")?.state).toBe("past");
    const stopped = facts.find((f) => f.value === "Firebase");
    expect(stopped?.state).toBe("stopped");
    expect(stopped?.metadata?.reason?.toLowerCase()).toContain("pricing");
    const plan = facts.find((f) => f.attribute === "plan" && f.value === "Neon");
    expect(plan?.state).toBe("planned");
    expect(plan?.memoryType).toBe(MemoryType.GOAL);
    const conditional = facts.find((f) => f.value === "Redis");
    expect(conditional?.attribute).toBe("plan");
    expect(["conditional", "possible"]).toContain(conditional?.state);
    expect(conditional?.metadata?.condition?.toLowerCase()).toContain("latency");
    // Condition must not become its own unrelated fact
    expect(facts.some((f) => /latency is high/i.test(f.value) && f.attribute !== "plan")).toBe(false);
  });

  it("collapses duplicate dislikes into one dislike fact", async () => {
    const message = "I don't like MongoDB. I avoid MongoDB. I hate MongoDB.";
    const ex = createGroqExtractor({
      baseUrl: "https://api.groq.com/openai/v1",
      apiKey: "k",
      fetchImpl: mockFetch(
        JSON.stringify({
          facts: [
            groqFact({
              attribute: "dislike",
              value: "MongoDB",
              type: "dislike",
              rawText: "I don't like MongoDB.",
            }),
            groqFact({
              attribute: "dislike",
              value: "MongoDB",
              type: "dislike",
              rawText: "I avoid MongoDB.",
            }),
            groqFact({
              attribute: "dislike",
              value: "MongoDB",
              type: "dislike",
              rawText: "I hate MongoDB.",
            }),
          ],
        }),
      ),
    });
    const facts = await ex.extract(message);
    const neg = facts.filter((f) => f.attribute === "dislike" && f.value.toLowerCase() === "mongodb");
    expect(neg).toHaveLength(1);
  });

  it("does not treat temporary experimentation as permanent uses", async () => {
    const message = "I'm experimenting with Redis for a bit.";
    const ex = createGroqExtractor({
      baseUrl: "https://api.groq.com/openai/v1",
      apiKey: "k",
      fetchImpl: mockFetch(
        JSON.stringify({
          facts: [
            groqFact({
              attribute: "uses",
              value: "Redis",
              type: "usage",
              state: "current",
              rawText: message,
            }),
          ],
        }),
      ),
    });
    const facts = await ex.extract(message);
    expect(facts.some((f) => f.attribute === "uses" && f.state === "current")).toBe(false);
    expect(facts.some((f) => f.attribute === "experiment")).toBe(true);
  });

  it("normalizes the long MemoryBox example into clean atomic facts", async () => {
    const ex = createGroqExtractor({
      baseUrl: "https://api.groq.com/openai/v1",
      apiKey: "k",
      fetchImpl: mockFetch(
        JSON.stringify({
          facts: [
            groqFact({
              entity: "Alex",
              attribute: "name",
              value: "Alex",
              type: "identity",
              rawText: MEMORYBOX_MESSAGE,
            }),
            groqFact({
              entity: "Alex",
              attribute: "occupation",
              value: "full-stack developer",
              type: "identity",
              rawText: MEMORYBOX_MESSAGE,
            }),
            groqFact({
              entity: "Alex",
              attribute: "project",
              value: "MemoryBox",
              type: "identity",
              rawText: MEMORYBOX_MESSAGE,
            }),
            groqFact({
              entity: "Alex",
              attribute: "uses",
              value: "Cloudflare Workers with D1 and Redis",
              type: "usage",
              rawText: MEMORYBOX_MESSAGE,
            }),
            groqFact({
              entity: "Alex",
              attribute: "uses",
              value: "MongoDB",
              type: "past_usage",
              state: "past",
              rawText: MEMORYBOX_MESSAGE,
            }),
            groqFact({
              entity: "Alex",
              attribute: "uses",
              value: "Firebase",
              type: "stopped_usage",
              state: "stopped",
              rawText: MEMORYBOX_MESSAGE,
              metadata: { preferred_over: null, condition: null, reason: "pricing" },
            }),
            groqFact({
              entity: "Alex",
              attribute: "preference",
              value: "MUI over shadcn",
              type: "preference",
              rawText: MEMORYBOX_MESSAGE,
            }),
            groqFact({
              entity: "Alex",
              attribute: "dislike",
              value: "Bootstrap",
              type: "dislike",
              rawText: "I don't like Bootstrap.",
            }),
            groqFact({
              entity: "Alex",
              attribute: "dislike",
              value: "Bootstrap",
              type: "dislike",
              rawText: "I avoid Bootstrap.",
            }),
            groqFact({
              entity: "Alex",
              attribute: "plan",
              value: "Neon",
              type: "plan",
              state: "planned",
              rawText: "I plan to use Neon.",
            }),
            groqFact({
              entity: "Alex",
              attribute: "plan",
              value: "PlanetScale",
              type: "possible_plan",
              state: "conditional",
              rawText: "I might switch to PlanetScale if latency is high.",
              metadata: {
                preferred_over: null,
                condition: "latency is high",
                reason: null,
              },
            }),
            groqFact({
              entity: "Alex",
              attribute: "uses",
              value: "Bun",
              type: "usage",
              state: "current",
              rawText: "I am experimenting with Bun.",
            }),
            groqFact({
              entity: "Alex",
              attribute: "preference",
              value: "Redis",
              type: "preference",
              rawText: "What do you think about Redis?",
            }),
          ],
        }),
      ),
    });

    const facts = await ex.extract(MEMORYBOX_MESSAGE);

    // No invented attributes
    expect(facts.every((f) => CANONICAL_ATTRIBUTES.has(f.attribute))).toBe(true);
    // Never use the person's name as entity
    expect(facts.every((f) => f.entity !== "Alex")).toBe(true);
    // Never store the entire message as rawText
    expect(facts.every((f) => f.rawText !== MEMORYBOX_MESSAGE)).toBe(true);
    expect(facts.every((f) => f.rawText.length < MEMORYBOX_MESSAGE.length)).toBe(true);

    const byAttr = (a: string) => facts.filter((f) => f.attribute === a);

    expect(byAttr("name")).toHaveLength(1);
    expect(byAttr("name")[0].entity).toBe("user");
    expect(byAttr("name")[0].value).toBe("Alex");

    expect(byAttr("occupation")[0].entity).toBe("user");
    expect(byAttr("occupation")[0].value.toLowerCase()).toContain("full-stack");

    expect(byAttr("project")[0].value).toBe("MemoryBox");
    expect(byAttr("project")[0].entity).toBe("MemoryBox");

    const uses = byAttr("uses");
    const currentUses = uses.filter((f) => f.state === "current");
    expect(currentUses.length).toBeGreaterThanOrEqual(3);
    expect(currentUses.every((f) => f.entity === "MemoryBox" || f.scope === "project")).toBe(true);
    const currentVals = currentUses.map((f) => f.value.toLowerCase());
    expect(currentVals.some((v) => v.includes("cloudflare") || v.includes("workers"))).toBe(true);
    expect(currentVals.some((v) => v.includes("d1"))).toBe(true);
    expect(currentVals.some((v) => v.includes("redis"))).toBe(true);

    expect(uses.find((f) => /mongodb/i.test(f.value))?.state).toBe("past");
    const firebase = uses.find((f) => /firebase/i.test(f.value));
    expect(firebase?.state).toBe("stopped");
    expect(firebase?.metadata?.reason?.toLowerCase()).toContain("pricing");

    const pref = byAttr("preference");
    expect(pref).toHaveLength(1);
    expect(pref[0].value.toLowerCase()).toBe("mui");
    expect(pref[0].metadata?.preferred_over?.toLowerCase()).toContain("shadcn");

    expect(byAttr("dislike")).toHaveLength(1);
    expect(byAttr("dislike")[0].value.toLowerCase()).toBe("bootstrap");

    const plans = byAttr("plan");
    expect(plans.find((f) => /neon/i.test(f.value))?.state).toBe("planned");
    const conditional = plans.find((f) => /planetscale/i.test(f.value));
    expect(["conditional", "possible"]).toContain(conditional?.state);
    expect(conditional?.metadata?.condition?.toLowerCase()).toContain("latency");

    expect(byAttr("experiment").some((f) => /bun/i.test(f.value))).toBe(true);
    expect(facts.some((f) => f.attribute === "uses" && /bun/i.test(f.value) && f.state === "current")).toBe(
      false,
    );

    // Question about Redis must not invent a preference
    expect(pref.every((f) => !/redis/i.test(f.value))).toBe(true);

    // Semantic dedupe: no duplicate dislike / identical uses
    const keys = facts.map((f) => `${f.attribute}|${f.value.toLowerCase()}|${f.state}`);
    expect(new Set(keys).size).toBe(keys.length);
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
    expect(res.facts[0].metadata?.preferred_over?.toLowerCase()).toContain("ant");
  });

  it("merges and deduplicates local + Groq facts", async () => {
    const res = await extractStructuredFactsHybrid("I prefer Material UI over Ant Design and I use Neovim.", {
      groqApiKey: "fake",
      groqBaseUrl: "https://api.groq.com/openai/v1",
      fetchImpl: mockFetch(
        JSON.stringify({
          facts: [
            groqFact({
              attribute: "preference",
              value: "Material UI over Ant Design",
              type: "preference",
              state: "current",
              confidence: 0.9,
              rawText: "I prefer Material UI over Ant Design",
            }),
            groqFact({
              attribute: "uses",
              value: "Neovim",
              type: "usage",
              state: "current",
              confidence: 0.9,
              rawText: "I use Neovim.",
            }),
          ],
        }),
      ),
    });
    const editorFacts = res.facts.filter((f) => f.value === "Neovim");
    expect(editorFacts).toHaveLength(1);
  });

  it("deduplicates facts via mergeFacts helper", () => {
    const fact = {
      entity: "user",
      attribute: "uses",
      value: "Neon",
      memoryType: MemoryType.FACT,
      rawText: "t",
      key: "user.uses.neon",
      scope: "user" as const,
      state: "current" as const,
      confidence: 0.9,
    };
    const merged = mergeFacts([fact], [{ ...fact, confidence: 0.8 }]);
    expect(merged).toHaveLength(1);
  });

  it("exposes a strict schema with canonical attributes and preferred_over", () => {
    expect(GROQ_FACT_SCHEMA.additionalProperties).toBe(false);
    const items = (GROQ_FACT_SCHEMA.properties.facts as {
      items: {
        additionalProperties: boolean;
        required: string[];
        properties: { attribute: { enum: string[] }; metadata: { required: string[] } };
      };
    }).items;
    expect(items.additionalProperties).toBe(false);
    expect(items.required).toContain("rawText");
    expect(items.required).toContain("metadata");
    expect(items.properties.attribute.enum).toEqual([
      "name",
      "occupation",
      "project",
      "uses",
      "database",
      "preference",
      "dislike",
      "experiment",
      "goal",
      "plan",
    ]);
    expect(items.properties.metadata.required).toContain("preferred_over");
  });
});

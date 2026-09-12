import { describe, expect, it } from "bun:test";
import { extractStructuredFact, detectPreferenceDomain } from "../src/memory/facts";
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

  it("extracts possessive statements", () => {
    const fact = extractStructuredFact("Cloudisy's architecture is event-driven microservices");
    expect(fact).not.toBeNull();
    expect(fact?.entity).toBe("Cloudisy");
    expect(fact?.attribute).toBe("architecture");
    expect(fact?.memoryType).toBe(MemoryType.ARCHITECTURE);
  });
});

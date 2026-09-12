import { describe, expect, it } from "bun:test";
import { isInterrogative } from "../src/memory/interrogative";

describe("Interrogative Detection (FIX.md §1)", () => {
  it("flags direct questions ending with ?", () => {
    expect(isInterrogative("What database do we use?")).toBe(true);
    expect(isInterrogative("Is PostgreSQL supported?")).toBe(true);
    expect(isInterrogative("Where is the project deployed?")).toBe(true);
  });

  it("flags inverted questions and wh-inquiries without question marks", () => {
    expect(isInterrogative("What is my name")).toBe(true);
    expect(isInterrogative("Why did we choose PostgreSQL")).toBe(true);
    expect(isInterrogative("Tell me what database we use")).toBe(true);
    expect(isInterrogative("Can you explain how the cache works")).toBe(true);
  });

  it("preserves declarative statements that contain question words", () => {
    expect(isInterrogative("The reason why we chose PostgreSQL is reliability")).toBe(false);
    expect(isInterrogative("Where we deploy is AWS Lambda")).toBe(false);
    expect(isInterrogative("I prefer TypeScript")).toBe(false);
    expect(isInterrogative("What we decided is to use Neon")).toBe(false);
  });
});

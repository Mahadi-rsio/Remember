import { describe, expect, it } from "bun:test";
import { estimateTokens, estimateMessagesTokens } from "../src/context/tokens";
import { compileContext } from "../src/context/compiler";

describe("Context Compilation and Token Estimation", () => {
  it("estimates token counts conservatively", () => {
    const tokens = estimateTokens("Hello world! This is a test string.");
    expect(tokens).toBeGreaterThan(5);
    expect(tokens).toBeLessThan(20);
  });

  it("compiles context within specified token budget without dropping system/latest message", async () => {
    const messages = [
      { role: "system", content: "You are an intelligent coding assistant." },
      { role: "user", content: "Can you help me design an architecture?" },
      { role: "assistant", content: "Sure! Let's start with the database design and API layer." },
      { role: "user", content: "Let's proceed with Cloudflare Workers." },
    ];

    const result = await compileContext(null, messages, "test-user", {
      budget: 500,
      persistSnapshot: false,
    });

    expect(result.messages.length).toBeGreaterThanOrEqual(2);
    expect(result.totalTokens).toBeLessThanOrEqual(500);
    // System message should be preserved
    expect(result.messages[0].role).toBe("system");
    // Latest message should be preserved
    expect(result.messages[result.messages.length - 1].content).toBe(
      "Let's proceed with Cloudflare Workers."
    );
  });
});

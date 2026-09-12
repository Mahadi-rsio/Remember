import { describe, expect, it, afterEach } from "bun:test";
import app from "../src/index";

const UPSTREAM_BODY = {
  id: "chatcmpl-123",
  object: "chat.completion",
  created: 1712345678,
  model: "gpt-test",
  choices: [
    {
      index: 0,
      message: { role: "assistant", content: "Hello from upstream" },
      finish_reason: "stop",
    },
  ],
};

const SSE_CHUNKS = [
  'data: {"id":"chatcmpl-s1","choices":[{"index":0,"delta":{"content":"Hel"}}]}\n\n',
  'data: {"id":"chatcmpl-s1","choices":[{"index":0,"delta":{"content":"lo"}}]}\n\n',
  "data: [DONE]\n\n",
];

function sseResponse(): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of SSE_CHUNKS) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function chatRequestEnv() {
  return {
    UPSTREAM_BASE_URL: "https://upstream.test/v1",
    CONTEXT_BUDGET: "8000",
  };
}

describe("Transparent Proxy Integration (fail-open, response identity)", () => {
  it("forwards non-streaming chat completions with byte-identical upstream response", async () => {
    const upstreamBody = { ...UPSTREAM_BODY };
    globalThis.fetch = (async (url: any, init: any) => {
      expect(String(url)).toBe("https://upstream.test/v1/chat/completions");
      const sent = JSON.parse(init.body);
      expect(sent.messages[0].role).toBe("user");
      return new Response(JSON.stringify(upstreamBody), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as any;

    const res = await app.request(
      "/v1/chat/completions",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "gpt-test",
          messages: [{ role: "user", content: "I prefer PostgreSQL" }],
        }),
      },
      chatRequestEnv()
    );

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("application/json");
    const json = await res.json();
    expect(json).toEqual(UPSTREAM_BODY);
  });

  it("streams SSE responses unchanged through the gateway", async () => {
    globalThis.fetch = (async () => sseResponse()) as any;

    const res = await app.request(
      "/v1/chat/completions",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "gpt-test",
          stream: true,
          messages: [{ role: "user", content: "hi" }],
        }),
      },
      chatRequestEnv()
    );

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/event-stream");

    const text = await res.text();
    expect(text).toBe(SSE_CHUNKS.join(""));
  });

  it("returns 400 with OpenAI-style error for malformed JSON", async () => {
    const res = await app.request(
      "/v1/chat/completions",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{not valid json",
      },
      chatRequestEnv()
    );

    expect(res.status).toBe(400);
    const json = await res.json();
    expect(json.error.type).toBe("invalid_request_error");
    expect(json.error.code).toBe("invalid_json");
  });

  it("maps upstream failures to 502 without leaking internals", async () => {
    globalThis.fetch = (async () => {
      throw new Error("connection refused with secret-details");
    }) as any;

    const res = await app.request(
      "/v1/chat/completions",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "gpt-test",
          messages: [{ role: "user", content: "hi" }],
        }),
      },
      chatRequestEnv()
    );

    expect(res.status).toBe(502);
    const json = await res.json();
    expect(json.error.type).toBe("upstream_error");
    expect(JSON.stringify(json)).not.toContain("secret-details");
  });

  it("fails open: missing DB config does not block upstream forwarding", async () => {
    let upstreamCalled = false;
    globalThis.fetch = (async () => {
      upstreamCalled = true;
      return new Response(JSON.stringify(UPSTREAM_BODY), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as any;

    const res = await app.request(
      "/v1/chat/completions",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "gpt-test",
          messages: [{ role: "user", content: "I prefer PostgreSQL" }],
        }),
      },
      { UPSTREAM_BASE_URL: "https://upstream.test/v1" }
    );

    expect(res.status).toBe(200);
    expect(upstreamCalled).toBe(true);
    const json = await res.json();
    expect(json.choices[0].message.content).toBe("Hello from upstream");
  });
});

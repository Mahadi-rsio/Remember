import { describe, expect, it } from "bun:test";
import app from "../src/index";

describe("Hono Worker App Endpoints", () => {
  it("responds on GET / with service metadata", async () => {
    const res = await app.request("/");
    expect(res.status).toBe(200);
    const json = (await res.json()) as any;
    expect(json.name).toBe("remember-memory-gateway");
    expect(json.runtime).toBe("Cloudflare Workers");
    expect(json.database).toContain("Neon");
  });

  it("responds on GET /health", async () => {
    const res = await app.request("/health", {}, {
      UPSTREAM_BASE_URL: "https://api.openai.com/v1",
      CONTEXT_BUDGET: "8000",
    });
    expect(res.status).toBe(200);
    const json = (await res.json()) as any;
    expect(json.status).toBe("ok");
    expect(json.service).toBe("remember-memory-gateway");
    expect(json.database.provider).toBe("neon");
  });

  it("enforces authentication: missing key returns 401", async () => {
    const res = await app.request(
      "/v1/models",
      {
        headers: {
          "Content-Type": "application/json",
        },
      },
      {}
    );
    expect(res.status).toBe(401);
  });

  it("rejects invalid API key with 401", async () => {
    const res = await app.request(
      "/v1/models",
      {
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer wrong-key",
        },
      },
      {}
    );
    expect(res.status).toBe(401);
  });

  it("rejects non-Bearer authorization with 401", async () => {
    const res = await app.request(
      "/v1/models",
      {
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": "1234",
        },
      },
      {}
    );
    expect(res.status).toBe(401);
  });
});

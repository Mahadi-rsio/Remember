import { Hono } from "hono";
import type { HonoContext } from "../env";

export const v1Router = new Hono<HonoContext>();

// GET /v1/models - List upstream models
v1Router.get("/models", async (c) => {
  const env = c.env;
  const upstreamBase = env.UPSTREAM_BASE_URL ?? "https://api.openai.com/v1";
  const apiKey = env.UPSTREAM_API_KEY;

  if (!apiKey) {
    return c.json(
      {
        error: {
          message: "UPSTREAM_API_KEY is not configured on gateway",
          type: "server_error",
        },
      },
      500
    );
  }

  try {
    const upstreamUrl = `${upstreamBase.replace(/\/+$/, "")}/models`;
    const response = await fetch(upstreamUrl, {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
    });

    const data = await response.json();
    return c.json(data, response.status as any);
  } catch (error: any) {
    return c.json(
      {
        error: {
          message: error.message || "Failed to fetch models from upstream",
          type: "upstream_error",
        },
      },
      502
    );
  }
});

// POST /v1/chat/completions - OpenAI-compatible Chat Completions proxy stub
v1Router.post("/chat/completions", async (c) => {
  return c.json({
    message: "Chat completions endpoint setup ready for migration pipeline",
  });
});

// POST /v1/responses - OpenAI-compatible Responses proxy stub
v1Router.post("/responses", async (c) => {
  return c.json({
    message: "Responses endpoint setup ready for migration pipeline",
  });
});

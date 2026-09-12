import { Hono } from "hono";
import { cors } from "hono/cors";
import { logger } from "hono/logger";
import { prettyJSON } from "hono/pretty-json";
import type { HonoContext } from "./env";
import { healthRouter } from "./routes/health";
import { v1Router } from "./routes/v1";

const app = new Hono<HonoContext>();

// Middleware
app.use("*", logger());
app.use("*", cors());
app.use("*", prettyJSON());

// Health checks
app.route("/", healthRouter);
app.route("/v1", healthRouter);

// V1 OpenAI-compatible routes
app.route("/v1", v1Router);

// Root route
app.get("/", (c) => {
  return c.json({
    name: "remember-memory-gateway",
    description: "OpenAI-compatible AI Memory Gateway",
    runtime: "Cloudflare Workers",
    framework: "Hono",
    orm: "Drizzle",
    database: "Cloudflare D1 (SQLite)",
    cache: "Upstash Redis",
    version: "0.1.0",
    endpoints: {
      health: "/health",
      v1_models: "/v1/models",
      v1_chat_completions: "/v1/chat/completions",
      v1_responses: "/v1/responses",
    },
  });
});

export default app;

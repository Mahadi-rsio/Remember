export interface Env {
  // Turso / LibSQL
  TURSO_DATABASE_URL: string;
  TURSO_AUTH_TOKEN?: string;

  // Upstream AI Provider (OpenAI / OpenRouter / etc.)
  UPSTREAM_PROVIDER?: string;
  UPSTREAM_BASE_URL?: string;
  UPSTREAM_API_KEY?: string;

  // Gateway Auth (Optional)
  GATEWAY_API_KEY?: string;

  // Context Compiler Budget
  CONTEXT_BUDGET?: string | number;

  // Optional Memory AI Compressor
  MEMORY_AI_ENABLED?: string | boolean;
  MEMORY_AI_PROVIDER?: string;
  MEMORY_AI_BASE_URL?: string;
  MEMORY_AI_MODEL?: string;
  MEMORY_AI_API_KEY?: string;

  // Logging
  LOG_LEVEL?: string;
}

export type HonoContext = {
  Bindings: Env;
};

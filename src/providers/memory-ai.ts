import type { MemoryAIOutput, ToolSummaryOutput } from "../models/memory";
import type { Env } from "../env";

const JSON_BLOCK_RE = /```(?:json)?\s*(?<json>\{.*\}|\[.*\])\s*```/s;

export const EXTRACTION_SYSTEM_PROMPT = `You are an AI Memory Compressor. Your role is ONLY to extract and compress memory items from conversation messages.
You NEVER answer the user directly.

Split multi-fact messages into ATOMIC facts. Each fact is ONE independent, self-contained statement (one entity, one attribute, one value). Do not merge multiple facts into a single bullet.

Output strictly valid JSON conforming to this schema:
{
  "summary": "Brief 1-2 sentence overview of what changed or happened",
  "facts": ["Stable facts about project/user/environment"],
  "decisions": ["Confirmed choices and decisions"],
  "constraints": ["Rules, restrictions, and negative requirements"],
  "preferences": ["User preferences and stylistic choices"],
  "goals": ["Active objectives and desired outcomes"],
  "architecture": ["System design and technical stack details"],
  "important_events": ["Key milestones, releases, or deployments"],
  "active_tasks": ["Pending or in-progress todos and tasks"],
  "obsolete_items": ["Previous facts/decisions that are now obsolete"],
  "contradictions": ["Previous items contradicted or superseded by new input"],
  "confidence": 0.95
}

Rules:
1. Extract only high-value information.
2. Each bullet must be a single atomic fact. For example, "Uses Cloudflare Workers, Hono, Turso, Upstash Redis, Groq" must become separate entries, not one.
3. When the user switches/changes a previously stated value (e.g. "we switched X to Y"), list the new value under the appropriate list and add the old one to "obsolete_items".
4. User statements and explicit decisions have highest authority.
5. Assistant speculation must NOT be recorded as confirmed facts/decisions.
6. Output ONLY valid JSON. No commentary outside the JSON.
`;

export const TOOL_COMPRESSION_SYSTEM_PROMPT = `You are a Tool Output Compressor. Your role is to summarize tool/command execution output.
Keep crucial exit statuses, error codes, file paths, IDs, and core outputs.
Remove repetitive logs, progress bars, and boilerplate.

Output strictly valid JSON:
{
  "summary": "Concise 1-3 sentence summary of the execution outcome",
  "key_points": ["Specific result item, path, or error"],
  "status": "success | error | warning"
}
`;

export function extractJsonText(text: string): string {
  const trimmed = text.trim();
  const match = trimmed.match(JSON_BLOCK_RE);
  if (match && match.groups && match.groups.json) {
    return match.groups.json.trim();
  }
  const firstBrace = trimmed.indexOf("{");
  const lastBrace = trimmed.lastIndexOf("}");
  if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
    return trimmed.slice(firstBrace, lastBrace + 1);
  }
  return trimmed;
}

export class MemoryAIAdapter {
  private baseUrl: string;
  private apiKey?: string;
  private model: string;
  private retryOnce: boolean;

  constructor(options: {
    baseUrl: string;
    apiKey?: string;
    model: string;
    retryOnce?: boolean;
  }) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.apiKey = options.apiKey;
    this.model = options.model;
    this.retryOnce = options.retryOnce ?? true;
  }

  private authHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.apiKey) {
      headers["Authorization"] = `Bearer ${this.apiKey}`;
    }
    return headers;
  }

  private async postChat(messages: Array<{ role: string; content: string }>): Promise<string> {
    const url = `${this.baseUrl}/chat/completions`;
    const payload = {
      model: this.model,
      messages,
      temperature: 0.0,
    };
    const response = await fetch(url, {
      method: "POST",
      headers: this.authHeaders(),
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Memory AI HTTP error ${response.status}: ${await response.text()}`);
    }

    const data = (await response.json()) as any;
    const choices = data?.choices || [];
    if (choices.length === 0) {
      throw new Error("No completion choices returned by Memory AI");
    }
    return String(choices[0]?.message?.content || "");
  }

  async extractMemory(
    messagesText: string,
    currentMemorySummary?: string | null
  ): Promise<MemoryAIOutput | null> {
    let userPrompt = `Delta Messages to analyze:\n${messagesText}`;
    if (currentMemorySummary) {
      userPrompt = `Current Memory State:\n${currentMemorySummary}\n\n${userPrompt}`;
    }

    const conversation: Array<{ role: string; content: string }> = [
      { role: "system", content: EXTRACTION_SYSTEM_PROMPT },
      { role: "user", content: userPrompt },
    ];

    let rawResponse: string | null = null;
    try {
      rawResponse = await this.postChat(conversation);
      return this.parseAndValidateMemory(rawResponse);
    } catch (parseErr) {
      if (!this.retryOnce) {
        return null;
      }
      try {
        const retryConv = [...conversation];
        if (rawResponse) {
          retryConv.push({ role: "assistant", content: rawResponse });
        }
        retryConv.push({
          role: "user",
          content: `Previous output was not valid JSON matching the schema: ${parseErr}. Please output ONLY the valid JSON object.`,
        });
        const retryRaw = await this.postChat(retryConv);
        return this.parseAndValidateMemory(retryRaw);
      } catch {
        return null;
      }
    }
  }

  private parseAndValidateMemory(rawText: string): MemoryAIOutput {
    const clean = extractJsonText(rawText);
    const parsed = JSON.parse(clean);
    return {
      summary: String(parsed.summary || ""),
      facts: Array.isArray(parsed.facts) ? parsed.facts.map(String) : [],
      decisions: Array.isArray(parsed.decisions) ? parsed.decisions.map(String) : [],
      constraints: Array.isArray(parsed.constraints) ? parsed.constraints.map(String) : [],
      preferences: Array.isArray(parsed.preferences) ? parsed.preferences.map(String) : [],
      goals: Array.isArray(parsed.goals) ? parsed.goals.map(String) : [],
      architecture: Array.isArray(parsed.architecture) ? parsed.architecture.map(String) : [],
      important_events: Array.isArray(parsed.important_events) ? parsed.important_events.map(String) : [],
      active_tasks: Array.isArray(parsed.active_tasks) ? parsed.active_tasks.map(String) : [],
      obsolete_items: Array.isArray(parsed.obsolete_items) ? parsed.obsolete_items.map(String) : [],
      contradictions: Array.isArray(parsed.contradictions) ? parsed.contradictions.map(String) : [],
      confidence: typeof parsed.confidence === "number" ? parsed.confidence : 0.95,
    };
  }

  async compressToolOutput(
    toolName: string,
    outputText: string,
    maxCharsThreshold = 300
  ): Promise<string> {
    if (outputText.length <= maxCharsThreshold) {
      return outputText;
    }

    const prompt = `Tool Name: ${toolName}\nRaw Output:\n${outputText}`;
    const conv = [
      { role: "system", content: TOOL_COMPRESSION_SYSTEM_PROMPT },
      { role: "user", content: prompt },
    ];

    try {
      const raw = await this.postChat(conv);
      const clean = extractJsonText(raw);
      const val = JSON.parse(clean) as ToolSummaryOutput;
      return `[Tool: ${toolName} | ${val.status || "success"}] ${val.summary || ""}`;
    } catch {
      return `[Tool: ${toolName}] ${outputText.slice(0, maxCharsThreshold)}... (truncated)`;
    }
  }
}

export function createMemoryAIAdapter(env: Env): MemoryAIAdapter | null {
  const isEnabled = String(env.MEMORY_AI_ENABLED).toLowerCase() === "true";
  if (!isEnabled) {
    return null;
  }
  const baseUrl = env.MEMORY_AI_BASE_URL || "https://openrouter.ai/api/v1";
  const model = env.MEMORY_AI_MODEL || "cheap-model";
  return new MemoryAIAdapter({
    baseUrl,
    apiKey: env.MEMORY_AI_API_KEY,
    model,
    retryOnce: true,
  });
}

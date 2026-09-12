const WORD_OR_PUNCT_RE = /\w+|[^\w\s]+/gu;

export function estimateTokens(text: string): number {
  if (!text) return 0;
  const clean = text.trim();
  if (!clean) return 0;

  const matches = clean.match(WORD_OR_PUNCT_RE);
  const tokensByRegex = matches ? matches.length : 0;
  const tokensByChars = Math.max(1, Math.round(clean.length / 3.8));

  return Math.max(1, Math.max(tokensByRegex, tokensByChars));
}

export function estimateMessageTokens(message: Record<string, any>): number {
  let tokens = 3; // overhead

  const content = message.content;
  if (typeof content === "string") {
    tokens += estimateTokens(content);
  } else if (Array.isArray(content)) {
    for (const part of content) {
      if (typeof part === "string") {
        tokens += estimateTokens(part);
      } else if (typeof part === "object" && part !== null && part.text) {
        tokens += estimateTokens(String(part.text));
      }
    }
  }

  if (message.name) {
    tokens += estimateTokens(String(message.name)) + 1;
  }
  if (message.tool_call_id) {
    tokens += estimateTokens(String(message.tool_call_id)) + 1;
  }
  if (Array.isArray(message.tool_calls)) {
    for (const tc of message.tool_calls) {
      if (typeof tc === "object" && tc !== null) {
        const fn = tc.function || {};
        tokens += estimateTokens(String(fn.name || ""));
        tokens += estimateTokens(String(fn.arguments || ""));
        tokens += 3;
      }
    }
  }

  return tokens;
}

export function estimateMessagesTokens(messages: Array<Record<string, any>>): number {
  if (!messages || messages.length === 0) {
    return 0;
  }
  const sum = messages.reduce((acc, m) => acc + estimateMessageTokens(m), 0);
  return sum + 3;
}

/**
 * Deterministic interrogative and question classification (FIX.md §1).
 */

const ENDS_WITH_QUESTION_RE = /\?\s*["']?\s*$/;

const WH_AUX_RE =
  /^\s*(?:what|when|where|why|who|whom|whose|how)(?:'s|'re|'d)?\s+(?:is|are|am|was|were|do|does|did|can|could|will|would|should|shall|have|has|had|may|might|must)\b/i;

const WH_CONTRACTED_RE = /^\s*(?:what|when|where|why|who|how)'s\b/i;

const HOW_MODIFIER_RE = /^\s*how\s+(?:much|many|long|often|fast|far|come)\b/i;

const WH_NOUN_AUX_RE =
  /^\s*(?:what|which)\s+(?!(?:we|i|you|they|he|she|it)\b)(?:[a-z0-9_-]+\s+){1,3}(?:is|are|am|was|were|do|does|did|can|could|will|would|should|shall|have|has|had)\b/i;

const INVERSION_AUX_RE =
  /^\s*(?:is|are|am|was|were|do|does|did|can|could|would|should|shall)\s+(?!(?:not\b|n't\b))(?:we|you|they|he|she|it|i|there|this|that|the|a|an|[a-z0-9_-]+)\b|^\s*will\s+(?:we|you|they|he|she|it|i|there|this|that|the|a|an)\b|^\s*(?:have|had)\s+(?:we|you|they|i)\b|^\s*has\s+(?:the|it|this|that|anyone|everyone|[a-z0-9_-]+)\b|^\s*may\s+(?:i|we)\b/i;

const INQUIRY_REQUEST_RE =
  /^\s*(?:can\s+you\s+|could\s+you\s+|please\s+)?(?:tell\s+me|remind\s+me|show\s+me|explain|let\s+me\s+know|find\s+out|check\s+if|check\s+whether)\b/i;

const STANDALONE_QUESTION_WORDS: ReadonlySet<string> = new Set([
  "what",
  "why",
  "how",
  "who",
  "whom",
  "whose",
  "when",
  "where",
  "which",
]);

const PUNCT_RE = /[^\w\s+]+/g;
const SPACE_RE = /\s+/g;

function normalize(text: string): string {
  if (!text) return "";
  let folded = text.normalize("NFKC").toLowerCase().trim();
  folded = folded.replace(PUNCT_RE, " ");
  folded = folded.replace(SPACE_RE, " ").trim();
  return folded;
}

export function isInterrogative(text: string): boolean {
  if (!text) return false;
  const stripped = text.trim();
  if (!stripped) return false;

  // 1. Trailing question mark: ends with ?
  if (ENDS_WITH_QUESTION_RE.test(stripped)) {
    return true;
  }

  // 2. Standalone question words
  if (STANDALONE_QUESTION_WORDS.has(normalize(stripped))) {
    return true;
  }

  // 3. Direct wh-question + aux
  if (WH_AUX_RE.test(stripped)) {
    return true;
  }

  // 4. Wh-contracted
  if (WH_CONTRACTED_RE.test(stripped)) {
    return true;
  }

  // 5. How + modifier
  if (HOW_MODIFIER_RE.test(stripped)) {
    return true;
  }

  // 6. Wh-noun + aux
  if (WH_NOUN_AUX_RE.test(stripped)) {
    return true;
  }

  // 7. Inversion questions
  if (INVERSION_AUX_RE.test(stripped)) {
    return true;
  }

  // 8. Inquiry requests
  if (INQUIRY_REQUEST_RE.test(stripped)) {
    return true;
  }

  return false;
}

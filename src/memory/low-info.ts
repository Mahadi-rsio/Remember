/**
 * Deterministic low-information message detection.
 */

export const LOW_INFO_PHRASES: ReadonlySet<string> = new Set([
  "ok",
  "okay",
  "k",
  "kk",
  "yes",
  "yep",
  "yeah",
  "yup",
  "no",
  "nope",
  "nah",
  "thanks",
  "thank you",
  "thx",
  "ty",
  "continue",
  "go on",
  "go ahead",
  "run it",
  "do that",
  "do it",
  "sure",
  "sure thing",
  "for sure",
  "cool",
  "got it",
  "got",
  "gotcha",
  "sounds",
  "sounds good",
  "sounds good to me",
  "that works",
  "works for me",
  "fine by me",
  "makes sense",
  "that makes sense",
  "please",
  "pls",
  "lgtm",
  "sgtm",
  "ack",
  "roger",
  "copy",
  "aye",
  "hm",
  "hmm",
  "huh",
  "haha",
  "lol",
  "great",
  "nice",
  "perfect",
  "awesome",
  "good",
  "fine",
  "right",
  "correct",
  "agreed",
  "absolutely",
  "totally",
  "alright",
  "understood",
  "i see",
  "no worries",
  "no problem",
  "np",
  "thanks a lot",
  "thank you very much",
  "much appreciated",
  "on it",
  "will do",
  "go for it",
  "keep going",
  "let us continue",
  "+",
  "++",
  "what",
  "why",
  "how",
  "who",
  "when",
  "where",
  "which",
]);

const PUNCT_RE = /[^\w\s+]+/g;
const SPACE_RE = /\s+/g;

export function normalizeUtterance(text: string): string {
  if (!text) return "";
  let folded = text.normalize("NFKC").toLowerCase().trim();
  folded = folded.replace(PUNCT_RE, " ");
  folded = folded.replace(SPACE_RE, " ").trim();
  return folded;
}

export function isLowInfoMessage(content: string, role = "user"): boolean {
  if (role !== "user" && role !== "assistant") {
    return false;
  }
  const normalized = normalizeUtterance(content);
  if (!normalized) {
    return true;
  }
  if (LOW_INFO_PHRASES.has(normalized)) {
    return true;
  }
  const words = normalized.split(" ");
  if (words.length > 0 && words.every((w) => LOW_INFO_PHRASES.has(w))) {
    return true;
  }
  if (!normalized.includes(" ") && normalized.length <= 3 && /^[a-z]+$/.test(normalized)) {
    return LOW_INFO_PHRASES.has(normalized) || normalized === "ok" || normalized === "k" || normalized === "kk";
  }
  return false;
}

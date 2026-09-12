import { MemoryType, type StructuredFact } from "../models/memory";
import { isInterrogative } from "./interrogative";

export function slugify(text: string): string {
  const parts = text.toLowerCase().match(/[a-z0-9]+/g) || [];
  return parts.slice(0, 6).join("_") || "item";
}

export function cleanVal(val: string): string {
  let v = val.trim().replace(/^['"`]+|['"`]+$/g, "");
  v = v.replace(/[.!?]+$/, "").trim();
  return v;
}

export const INVALID_KEYS: ReadonlySet<string> = new Set([
  "what",
  "when",
  "where",
  "which",
  "who",
  "whom",
  "whose",
  "why",
  "how",
  "is",
  "are",
  "was",
  "were",
  "do",
  "does",
  "did",
  "can",
  "could",
  "will",
  "would",
  "should",
  "shall",
  "have",
  "has",
  "had",
  "may",
  "might",
]);

const DB_KEYWORDS = new Set([
  "postgres",
  "postgresql",
  "neon",
  "supabase",
  "mysql",
  "sqlite",
  "libsql",
  "turso",
  "mongodb",
  "mongo",
  "redis",
  "cockroach",
  "cockroachdb",
  "dynamodb",
  "mariadb",
  "cassandra",
  "oracle",
  "database",
  "db",
]);

const UI_KEYWORDS = new Set([
  "tailwind",
  "mui",
  "shadcn",
  "bootstrap",
  "chakra",
  "antd",
]);

const FRONTEND_KEYWORDS = new Set([
  "react",
  "vue",
  "angular",
  "svelte",
  "solid",
  "next",
  "nextjs",
  "next.js",
  "nuxt",
  "nuxtjs",
  "nuxt.js",
]);

const LANGUAGE_KEYWORDS = new Set([
  "typescript",
  "javascript",
  "python",
  "rust",
  "go",
  "golang",
  "c++",
  "cpp",
  "c#",
  "csharp",
  "java",
  "ruby",
  "php",
  "swift",
  "kotlin",
]);

const THEME_KEYWORDS = new Set([
  "dark",
  "light",
  "dark mode",
  "light mode",
  "dark theme",
  "light theme",
]);

const WORKFLOW_KEYWORDS = new Set([
  "agile",
  "scrum",
  "kanban",
  "waterfall",
  "sprint",
  "workflow",
]);

function setIntersect<T>(a: Set<T>, b: Set<T>): boolean {
  for (const item of a) {
    if (b.has(item)) return true;
  }
  return false;
}

export function detectPreferenceDomain(choice: string, other = ""): [string, string] {
  const combined = `${choice} ${other}`.toLowerCase();
  const words = new Set(combined.match(/[a-z0-9+#.-]+/g) || []);

  if (setIntersect(words, UI_KEYWORDS) || combined.includes("ui library") || words.has("ui")) {
    return ["ui_library", "preference:ui_library"];
  }
  if (setIntersect(words, FRONTEND_KEYWORDS) || combined.includes("frontend") || combined.includes("framework")) {
    return ["frontend_framework", "preference:frontend_framework"];
  }
  if (setIntersect(words, LANGUAGE_KEYWORDS) || combined.includes("language")) {
    return ["language", "preference:language"];
  }
  if (setIntersect(words, THEME_KEYWORDS) || combined.includes("theme") || combined.includes("mode")) {
    return ["theme", "preference:theme"];
  }
  if (setIntersect(words, DB_KEYWORDS) || combined.includes("database") || combined.includes("db")) {
    return ["database", "preference:database"];
  }
  if (setIntersect(words, WORKFLOW_KEYWORDS)) {
    return ["workflow", "preference:workflow"];
  }

  const cSlug = slugify(choice);
  return ["preference", `preference:${cSlug}`];
}

export function scopeForFact(fact: StructuredFact): "user" | "project" | "session" {
  if (fact.scope) return fact.scope;
  const entity = fact.entity.toLowerCase();
  if (entity === "user" || entity === "my") return "user";
  if (fact.key && /^session\./i.test(fact.key)) return "session";
  return "project";
}

export function deriveFactKey(fact: StructuredFact): string {
  if (fact.key) return fact.key;
  const scope = scopeForFact(fact);
  if (fact.attribute === "project") {
    return "project.name";
  }
  const attr = slugify(fact.attribute);
  return `${scope}.${attr}`;
}

export function structuredFactToContent(fact: StructuredFact): string {
  if (fact.memoryType === MemoryType.PREFERENCE) {
    return fact.value;
  }
  if (fact.attribute === "project") {
    return `Project: ${fact.value}`;
  }
  const attrTitle = fact.attribute
    ? fact.attribute[0].toUpperCase() + fact.attribute.slice(1).replace(/_/g, " ")
    : "Item";
  return `${attrTitle}: ${fact.value}`;
}

export function structuredFactToTopicKey(fact: StructuredFact): string {
  if (fact.memoryType === MemoryType.PREFERENCE) {
    const [, topic] = detectPreferenceDomain(fact.value);
    return topic;
  }
  if (fact.attribute === "project") {
    return "project.name";
  }
  return deriveFactKey(fact);
}

// 1. "I am building X"
const BUILDING_RE = /^\s*(?:i\s+am|i'm|we\s+are|we're|building)\s+(?:building\s+)?(?<val>.+?)\s*[.!?]?$/i;

export function extractBuilding(text: string): StructuredFact | null {
  const m = text.match(BUILDING_RE);
  if (!m || !m.groups) return null;
  const val = cleanVal(m.groups.val);
  if (!val || INVALID_KEYS.has(val.toLowerCase())) return null;

  const calledMatch = val.match(/\bcalled\s+([A-Za-z0-9_-]+)/i);
  const projectName = calledMatch ? calledMatch[1] : val;

  return {
    entity: projectName,
    attribute: "project",
    value: projectName,
    memoryType: MemoryType.FACT,
    rawText: text,
    key: "project.name",
    scope: "project",
  };
}

// 2. "X uses Y"
const USES_RE = /^\s*(?:the\s+)?(?<entity>[A-Za-z][\w\s/-]{0,30}?)\s+(?:uses|is\s+using|will\s+use)\s+(?<val>.+?)\s*[.!?]?$/i;

export function extractUses(text: string): StructuredFact | null {
  const m = text.match(USES_RE);
  if (!m || !m.groups) return null;
  const entity = m.groups.entity.trim();
  const val = cleanVal(m.groups.val);
  if (!entity || !val || INVALID_KEYS.has(entity.toLowerCase())) return null;

  const entityClean = entity.toLowerCase().startsWith("the ") ? entity.slice(4).trim() : entity;

  const forMatch = val.match(/^(.+?)\s+for\s+(.+)$/i);
  const purpose = forMatch ? forMatch[2].trim() : "";

  const valLower = val.toLowerCase();
  const words = new Set(valLower.match(/[a-z0-9+#.-]+/g) || []);

  let attr = "technology";
  let mtype = MemoryType.FACT;

  if (purpose && !/\b(project|production|staging|dev|testing)\b/i.test(purpose)) {
    attr = attributeForPurpose(purpose) ?? slugify(purpose);
    mtype = MemoryType.DECISION;
  } else if (attributeForValue(valLower) !== "technology") {
    attr = attributeForValue(valLower);
    mtype = MemoryType.DECISION;
  } else if (setIntersect(words, UI_KEYWORDS)) {
    attr = "ui_library";
    mtype = MemoryType.DECISION;
  } else if (setIntersect(words, FRONTEND_KEYWORDS)) {
    attr = "frontend";
    mtype = MemoryType.DECISION;
  } else if (setIntersect(words, WORKFLOW_KEYWORDS)) {
    attr = "workflow";
    mtype = MemoryType.FACT;
  } else {
    attr = entityClean.toLowerCase() === "team" ? "workflow" : "technology";
    mtype = MemoryType.FACT;
  }

  const entityKey = entityClean.toLowerCase();
  const scope: "user" | "project" = entityKey === "user" || entityKey === "my" ? "user" : "project";

  return {
    entity: entityClean,
    attribute: attr,
    value: val,
    memoryType: mtype,
    rawText: text,
    key: `${scope}.${slugify(attr)}`,
    scope,
  };
}

// 3. "X's Z is ..."
const POSSESSIVE_RE =
  /^\s*(?<entity>[A-Za-z][\w\s/-]{0,30}?)'s\s+(?<attr>[A-Za-z][\w\s/-]{0,30}?)\s+(?:is|are|was|will\s+be|has\s+been|scheduled\s+for)\s+(?<val>.+?)\s*[.!?]?$/i;

export function extractPossessive(text: string): StructuredFact | null {
  const m = text.match(POSSESSIVE_RE);
  if (!m || !m.groups) return null;
  const entity = m.groups.entity.trim();
  const attr = m.groups.attr.trim();
  const val = cleanVal(m.groups.val);
  if (!entity || !attr || !val) return null;
  if (INVALID_KEYS.has(entity.toLowerCase()) || INVALID_KEYS.has(attr.toLowerCase())) return null;

  const attrLower = attr.toLowerCase();
  let mtype = MemoryType.FACT;
  if (attrLower.includes("architecture") || attrLower.includes("design")) {
    mtype = MemoryType.ARCHITECTURE;
  } else if (attrLower.includes("goal") || attrLower.includes("objective")) {
    mtype = MemoryType.GOAL;
  }

  const scope = entity.toLowerCase() === "user" ? "user" : "project";
  return {
    entity,
    attribute: attr,
    value: val,
    memoryType: mtype,
    rawText: text,
    key: `${scope}.${slugify(attr)}`,
    scope,
  };
}

// 4. "I prefer X over Y"
const PREFER_RE =
  /^\s*(?:i\s+)?(?:prefer|would\s+rather|preference)\b[:\s-]*(?<choice>.+?)(?:\s+over\s+(?<other>.+?)|\s+than\s+(?<than>.+?))?\s*[.!?]?$/i;

export function extractPreference(text: string): StructuredFact | null {
  const m = text.match(PREFER_RE);
  if (!m || !m.groups) return null;
  let choice = cleanVal(m.groups.choice);
  const other = cleanVal(m.groups.other || m.groups.than || "");
  if (!choice || INVALID_KEYS.has(choice.toLowerCase())) return null;

  if (choice.toLowerCase().startsWith("use ")) {
    choice = choice.slice(4).trim();
  }

  const val = other && !choice.includes("over") ? `${choice} over ${other}` : other ? `${choice} than ${other}` : choice;
  const [attr] = detectPreferenceDomain(choice, other);

  return {
    entity: "user",
    attribute: attr,
    value: val,
    memoryType: MemoryType.PREFERENCE,
    rawText: text,
    key: `user.preference.${slugify(attr)}`,
    scope: "user",
  };
}

// 5. "The Y is X"
const THE_Y_IS_X_RE =
  /^\s*(?:(?:temporary\s+detail|note|detail)\s*[:\s-]\s*)?(?:the\s+|my\s+)?(?<attr>[A-Za-z][\w\s/-]{0,35}?)\s*(?:=| is | are | was |:=|:)\s*(?<val>.+?)\s*[.!?]?$/i;

export function extractTheYIsX(text: string): StructuredFact | null {
  const m = text.match(THE_Y_IS_X_RE);
  if (!m || !m.groups) return null;
  let attr = m.groups.attr.trim();
  const val = cleanVal(m.groups.val);
  if (!attr || !val || val.endsWith("?")) return null;
  if (INVALID_KEYS.has(attr.toLowerCase())) return null;

  const attrLower = attr.toLowerCase();
  const words = new Set(attrLower.match(/[a-z0-9+#.-]+/g) || []);

  let mtype = MemoryType.FACT;
  if (/\b(target|deployment|database|db|provider|stack|hosting)\b/i.test(attrLower)) {
    mtype = MemoryType.DECISION;
  } else if (words.has("architecture") || words.has("design")) {
    mtype = MemoryType.ARCHITECTURE;
  } else if (words.has("goal") || words.has("objective")) {
    mtype = MemoryType.GOAL;
  } else if (words.has("preference") || words.has("prefer")) {
    mtype = MemoryType.PREFERENCE;
  }

  let entity = attr;
  if (text.trim().toLowerCase().startsWith("my name")) {
    entity = "user";
    attr = "name";
  }

  const scope = entity.toLowerCase() === "user" ? "user" : "project";
  return {
    entity,
    attribute: attr,
    value: val,
    memoryType: mtype,
    rawText: text,
    key: `${scope}.${slugify(attr)}`,
    scope,
  };
}

export function extractStructuredFact(text: string): StructuredFact | null {
  const cleaned = text.trim();
  if (!cleaned || isInterrogative(cleaned)) {
    return null;
  }

  return (
    extractBuilding(cleaned) ||
    extractPossessive(cleaned) ||
    extractPreference(cleaned) ||
    extractUses(cleaned) ||
    extractTheYIsX(cleaned) ||
    null
  );
}

const RUNTIME_RE =
  /\b(cloudflare workers|cloudflare|workers|deno|node|nodejs|bun|lambda|aws lambda|vercel|netlify|edge)\b/i;
const FRAMEWORK_RE =
  /\b(hono|next|nextjs|express|fastify|nuxt|sveltekit|flask|django|spring|rails|fastapi)\b/i;
const CACHE_RE = /\b(upstash|redis|memcached|cloudflare kv|kv store|cache)\b/i;
const STORAGE_RE = /\b(cloudflare r2|r2|s3|gcs|azure blob|minio|object storage|storage)\b/i;
const EMBEDDING_RE = /\b(embedding|embeddings|pgvector|vector|semantic retrieval|semantic)\b/i;
const LLM_RE = /\b(groq|openai|anthropic|claude|gpt|llama|mistral|gemini|mixtral|summariz)\b/i;
const DATABASE_RE = /\b(turso|neon|postgres|postgresql|supabase|mysql|sqlite|libsql|mongodb|mariadb|dynamodb|cockroach|database|db)\b/i;

/** Classify a technology VALUE into a stable project attribute. */
export function attributeForValue(value: string): string {
  const v = value.toLowerCase();
  if (DATABASE_RE.test(v)) return "database";
  if (CACHE_RE.test(v)) return "cache";
  if (STORAGE_RE.test(v)) return "storage";
  if (EMBEDDING_RE.test(v)) return "semantic_retrieval";
  if (LLM_RE.test(v)) return "summarization";
  if (FRAMEWORK_RE.test(v)) return "framework";
  if (RUNTIME_RE.test(v)) return "runtime";
  return "technology";
}

/** Classify a clause PURPOSE phrase into a project attribute. */
export function attributeForPurpose(purpose: string): string | null {
  const p = purpose.toLowerCase();
  if (/\b(database|db|storage\b|data)\b/.test(p)) return "database";
  if (/\b(cache|redis|kv)\b/.test(p)) return "cache";
  if (/\b(object storage|storage|files)\b/.test(p)) return "storage";
  if (/\b(semantic|embedding|retrieval|vector)\b/.test(p)) return "semantic_retrieval";
  if (/\b(summariz|llm|model|ai|generation|completion)\b/.test(p)) return "summarization";
  if (/\b(framework|web framework)\b/.test(p)) return "framework";
  if (/\b(runtime|hosting|deploy|platform|server|edge)\b/.test(p)) return "runtime";
  if (/\b(api|interface|client|sdk)\b/.test(p)) return "technology";
  return null;
}

const USES_SUBJECT_RE =
  /^(?<subject>.*?)\s+(?:uses|is using|will use|relies on|is built on|runs on)\s+(?<rest>.+)$/i;

const PRONOUN_SUBJECTS: ReadonlySet<string> = new Set([
  "it", "this", "that", "the project", "the app", "the application", "the product",
  "the system", "the platform", "the service", "we", "our", "the gateway", "the tool",
]);

function splitClauses(rest: string): string[] {
  const parts = rest
    .split(/,|\band\b|\bwith\b/i)
    .map((s) => s.trim())
    .filter(Boolean);
  return parts;
}

function inferAttributeFromClause(clause: string): { attr: string; value: string } {
  const lower = clause.toLowerCase();

  // "<tech> as the/its/our <attr>"
  let m = clause.match(/^(.+?)\s+as\s+(?:the\s+|its\s+|our\s+)?([a-z0-9 _-]+?)\s*$/i);
  if (m && m[1] && m[2]) {
    return { attr: slugify(m[2].trim()), value: m[1].trim() };
  }

  // "<tech> for <purpose>"
  m = clause.match(/^(.+?)\s+for\s+(.+)$/i);
  if (m && m[1] && m[2]) {
    const purpose = m[2].trim();
    const attr = attributeForPurpose(purpose) ?? slugify(purpose);
    let value = m[1].trim();
    // When the purpose is a known attribute word, keep just the technology name
    // (e.g. "Neon for its database" -> "Neon", "Groq for summarization" -> "Groq").
    if (attributeForPurpose(purpose)) {
      value = cleanVal(value);
    }
    return { attr, value };
  }

  // bare technology -> classify by value
  return { attr: attributeForValue(clause), value: clause.trim() };
}

/**
 * Parse "X uses A with B, C as the database, D for Redis, ..." into multiple
 * atomic project facts.
 */
export function extractUsesList(text: string): StructuredFact[] {
  const cleaned = text.trim();
  const m = cleaned.match(USES_SUBJECT_RE);
  if (!m || !m.groups) return [];

  let subject = m.groups.subject.trim();
  if (PRONOUN_SUBJECTS.has(subject.toLowerCase())) {
    subject = "project";
  }
  if (!subject || INVALID_KEYS.has(subject.toLowerCase())) return [];

  const rest = m.groups.rest.trim();
  const clauses = splitClauses(rest);
  if (clauses.length < 2) return [];

  const scope = subject.toLowerCase() === "user" ? "user" : "project";
  const facts: StructuredFact[] = [];
  const seen = new Set<string>();

  for (const clause of clauses) {
    const { attr, value } = inferAttributeFromClause(clause);
    if (!value) continue;
    const fact: StructuredFact = {
      entity: subject,
      attribute: attr,
      value: cleanVal(value),
      memoryType: MemoryType.DECISION,
      rawText: text,
      key: `${scope}.${slugify(attr)}`,
      scope,
    };
    const factKey = fact.key!;
    if (seen.has(factKey)) continue;
    seen.add(factKey);
    facts.push(fact);
  }

  return facts;
}

/**
 * Split a message into sentences on sentence-ending punctuation, without
 * splitting on commas or decimals.
 */
export function splitSentences(text: string): string[] {
  if (!text) return [];
  return text
    .split(/(?<=[.;!?])\s+(?=[A-Z"'(])/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Extract ALL durable facts explicitly stated in a sentence. Handles the
 * multi-clause "X uses A with B, C as the database, ..." pattern and falls
 * back to a single structured fact otherwise.
 */
export function extractStructuredFacts(text: string): StructuredFact[] {
  const cleaned = text.trim();
  if (!cleaned || isInterrogative(cleaned)) {
    return [];
  }

  const sentences = splitSentences(cleaned);
  if (sentences.length > 1) {
    const out: StructuredFact[] = [];
    const seen = new Set<string>();
    for (const sentence of sentences) {
      for (const fact of extractStructuredFacts(sentence)) {
        const k = fact.key || structuredFactToTopicKey(fact);
        if (seen.has(k)) continue;
        seen.add(k);
        out.push(fact);
      }
    }
    return out;
  }

  const multi = extractUsesList(cleaned);
  if (multi.length > 0) {
    return multi;
  }

  // Compound preference/name: "My name is X and I prefer Y" -> two facts.
  const compound = cleaned.match(/^(?<first>.+?)\s+and\s+I\s+prefer\s+(?<second>.+)$/i);
  if (compound && compound.groups) {
    const firstFacts = extractStructuredFact(compound.groups.first.trim());
    const secondFacts = extractStructuredFact(`I prefer ${compound.groups.second.trim()}`);
    const out: StructuredFact[] = [];
    if (firstFacts) out.push(firstFacts);
    if (secondFacts) out.push(secondFacts);
    if (out.length > 0) return out;
  }

  const single = extractStructuredFact(cleaned);
  return single ? [single] : [];
}

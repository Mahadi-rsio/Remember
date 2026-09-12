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

export function structuredFactToContent(fact: StructuredFact): string {
  if (fact.memoryType === MemoryType.PREFERENCE) {
    return fact.value;
  }
  if (fact.attribute === "project" && fact.entity === fact.value) {
    return `Project = ${fact.value}`;
  }
  if (fact.entity && !["user", fact.attribute.toLowerCase()].includes(fact.entity.toLowerCase())) {
    return `${fact.entity} ${fact.attribute} = ${fact.value}`;
  }
  const attrTitle = fact.attribute ? fact.attribute[0].toUpperCase() + fact.attribute.slice(1) : "Item";
  return `${attrTitle} = ${fact.value}`;
}

export function structuredFactToTopicKey(fact: StructuredFact): string {
  if (fact.memoryType === MemoryType.PREFERENCE) {
    const [, topic] = detectPreferenceDomain(fact.value);
    return topic;
  }
  if (fact.attribute === "project") {
    return "project";
  }
  if (fact.entity && !["user", fact.attribute.toLowerCase()].includes(fact.entity.toLowerCase())) {
    return `${slugify(fact.entity)}_${slugify(fact.attribute)}`;
  }
  return slugify(fact.attribute);
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
    attr = slugify(purpose);
    mtype = MemoryType.DECISION;
  } else if (setIntersect(words, DB_KEYWORDS) || valLower.includes("database") || entityClean.toLowerCase().includes("database")) {
    attr = "database";
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

  return {
    entity: entityClean,
    attribute: attr,
    value: val,
    memoryType: mtype,
    rawText: text,
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

  return {
    entity,
    attribute: attr,
    value: val,
    memoryType: mtype,
    rawText: text,
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

  return {
    entity,
    attribute: attr,
    value: val,
    memoryType: mtype,
    rawText: text,
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

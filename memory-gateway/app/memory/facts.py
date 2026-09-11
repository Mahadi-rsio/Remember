"""Modular deterministic fact extraction and normalization into (entity, attribute, value)."""

from __future__ import annotations

import re

from app.memory.interrogative import is_interrogative
from app.models.memory import MemoryType, StructuredFact


def slugify(text: str) -> str:
    parts = re.findall(r"[a-z0-9]+", text.casefold())
    return "_".join(parts[:6]) or "item"


def clean_val(val: str) -> str:
    v = val.strip().strip("'\"`")
    v = re.sub(r"[.!?]+$", "", v).strip()
    return v


_INVALID_KEYS = frozenset(
    {
        "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
        "is", "are", "was", "were", "do", "does", "did", "can", "could",
        "will", "would", "should", "shall", "have", "has", "had", "may", "might",
    }
)

_DB_KEYWORDS = frozenset(
    {
        "postgres", "postgresql", "neon", "supabase", "mysql", "sqlite",
        "mongodb", "mongo", "redis", "cockroach", "cockroachdb", "dynamodb",
        "mariadb", "cassandra", "oracle", "database", "db",
    }
)

_UI_KEYWORDS = frozenset(
    {
        "tailwind", "mui", "shadcn", "bootstrap", "chakra", "antd",
    }
)

_FRONTEND_KEYWORDS = frozenset(
    {
        "react", "vue", "angular", "svelte", "solid", "next", "nextjs",
        "next.js", "nuxt", "nuxtjs", "nuxt.js",
    }
)

_LANGUAGE_KEYWORDS = frozenset(
    {
        "typescript", "javascript", "python", "rust", "go", "golang",
        "c++", "cpp", "c#", "csharp", "java", "ruby", "php", "swift", "kotlin",
    }
)

_THEME_KEYWORDS = frozenset(
    {
        "dark", "light", "dark mode", "light mode", "dark theme", "light theme",
    }
)

_WORKFLOW_KEYWORDS = frozenset(
    {
        "agile", "scrum", "kanban", "waterfall", "sprint", "workflow",
    }
)


def detect_preference_domain(choice: str, other: str = "") -> tuple[str, str]:
    """Return (attribute, topic_key_slug) for preference."""
    combined = f"{choice} {other}".casefold()
    words = set(re.findall(r"[a-z0-9+#.-]+", combined))

    if words & _UI_KEYWORDS or "ui library" in combined or "ui" in words:
        return "ui_library", "preference:ui_library"
    if words & _FRONTEND_KEYWORDS or "frontend" in combined or "framework" in combined:
        return "frontend_framework", "preference:frontend_framework"
    if words & _LANGUAGE_KEYWORDS or "language" in combined:
        return "language", "preference:language"
    if words & _THEME_KEYWORDS or "theme" in combined or "mode" in combined:
        return "theme", "preference:theme"
    if words & _DB_KEYWORDS or "database" in combined or "db" in combined:
        return "database", "preference:database"
    if words & _WORKFLOW_KEYWORDS:
        return "workflow", "preference:workflow"

    c_slug = slugify(choice)
    return "preference", f"preference:{c_slug}"


# 1. Pattern: "I am building X." / "We are building X."
_BUILDING_RE = re.compile(
    r"^\s*(?:i\s+am|i'm|we\s+are|we're|building)\s+(?:building\s+)?(?P<val>.+?)\s*[.!?]?$",
    re.IGNORECASE,
)


def extract_building(text: str) -> StructuredFact | None:
    m = _BUILDING_RE.match(text)
    if not m:
        return None
    val = clean_val(m.group("val"))
    if not val or val.casefold() in _INVALID_KEYS:
        return None
    called_match = re.search(r"\bcalled\s+([A-Za-z0-9_-]+)", val, re.IGNORECASE)
    project_name = called_match.group(1) if called_match else val
    return StructuredFact(
        entity=project_name,
        attribute="project",
        value=project_name,
        memory_type=MemoryType.FACT,
        raw_text=text,
    )


# 2. Pattern: "X uses Y." / "X is using Y." / "The X uses Y."
_USES_RE = re.compile(
    r"^\s*(?:the\s+)?(?P<entity>[A-Za-z][\w\s/-]{0,30}?)\s+(?:uses|is\s+using|will\s+use)\s+(?P<val>.+?)\s*[.!?]?$",
    re.IGNORECASE,
)


def extract_uses(text: str) -> StructuredFact | None:
    m = _USES_RE.match(text)
    if not m:
        return None
    entity = m.group("entity").strip()
    val = clean_val(m.group("val"))
    if not entity or not val or entity.casefold() in _INVALID_KEYS:
        return None

    if entity.lower().startswith("the "):
        entity_clean = entity[4:].strip()
    else:
        entity_clean = entity

    for_match = re.match(r"^(.+?)\s+for\s+(.+)$", val, re.IGNORECASE)
    purpose = ""
    if for_match:
        purpose = for_match.group(2).strip()

    val_lower = val.casefold()
    words = set(re.findall(r"[a-z0-9+#.-]+", val_lower))

    if purpose and not re.search(r"\b(project|production|staging|dev|testing)\b", purpose, re.IGNORECASE):
        attr = slugify(purpose)
        mtype = MemoryType.DECISION
    elif words & _DB_KEYWORDS or "database" in val_lower or "database" in entity_clean.casefold():
        attr = "database"
        mtype = MemoryType.DECISION
    elif words & _UI_KEYWORDS:
        attr = "ui_library"
        mtype = MemoryType.DECISION
    elif words & _FRONTEND_KEYWORDS:
        attr = "frontend"
        mtype = MemoryType.DECISION
    elif words & _WORKFLOW_KEYWORDS:
        attr = "workflow"
        mtype = MemoryType.FACT
    else:
        attr = "workflow" if entity_clean.casefold() == "team" else "technology"
        mtype = MemoryType.FACT

    return StructuredFact(
        entity=entity_clean,
        attribute=attr,
        value=val,
        memory_type=mtype,
        raw_text=text,
    )


# 3. Pattern: "X's Z is …" / "X's Z was …"
_POSSESSIVE_RE = re.compile(
    r"^\s*(?P<entity>[A-Za-z][\w\s/-]{0,30}?)'s\s+(?P<attr>[A-Za-z][\w\s/-]{0,30}?)\s+(?:is|are|was|will\s+be|has\s+been|scheduled\s+for)\s+(?P<val>.+?)\s*[.!?]?$",
    re.IGNORECASE,
)


def extract_possessive(text: str) -> StructuredFact | None:
    m = _POSSESSIVE_RE.match(text)
    if not m:
        return None
    entity = m.group("entity").strip()
    attr = m.group("attr").strip()
    val = clean_val(m.group("val"))
    if not entity or not attr or not val:
        return None
    if entity.casefold() in _INVALID_KEYS or attr.casefold() in _INVALID_KEYS:
        return None

    attr_lower = attr.casefold()
    if "architecture" in attr_lower or "design" in attr_lower:
        mtype = MemoryType.ARCHITECTURE
    elif "goal" in attr_lower or "objective" in attr_lower:
        mtype = MemoryType.GOAL
    else:
        mtype = MemoryType.FACT

    return StructuredFact(
        entity=entity,
        attribute=attr,
        value=val,
        memory_type=mtype,
        raw_text=text,
    )


# 4. Pattern: "I prefer X over Y." / "I prefer X." / "Preference: X"
_PREFER_RE = re.compile(
    r"^\s*(?:i\s+)?(?:prefer|would\s+rather|preference)\b[:\s-]*(?P<choice>.+?)(?:\s+over\s+(?P<other>.+?)|\s+than\s+(?P<than>.+?))?\s*[.!?]?$",
    re.IGNORECASE,
)


def extract_preference(text: str) -> StructuredFact | None:
    m = _PREFER_RE.match(text)
    if not m:
        return None
    choice = clean_val(m.group("choice"))
    other = clean_val(m.group("other") or m.group("than") or "")
    if not choice or choice.casefold() in _INVALID_KEYS:
        return None

    # Handle "use Vue than React" -> choice="Vue", other="React"
    if choice.lower().startswith("use "):
        choice = choice[4:].strip()

    val = f"{choice} over {other}" if (other and "over" not in choice) else (f"{choice} than {other}" if other else choice)
    attr, _ = detect_preference_domain(choice, other)

    return StructuredFact(
        entity="user",
        attribute=attr,
        value=val,
        memory_type=MemoryType.PREFERENCE,
        raw_text=text,
    )


# 5. Pattern: "The Y is X." / "My Y is X." / "Temporary detail: the Y is X."
_THE_Y_IS_X_RE = re.compile(
    r"^\s*(?:(?:temporary\s+detail|note|detail)\s*[:\s-]\s*)?(?:the\s+|my\s+)?(?P<attr>[A-Za-z][\w\s/-]{0,35}?)\s*(?:=| is | are | was |:=|:)\s*(?P<val>.+?)\s*[.!?]?$",
    re.IGNORECASE,
)


def extract_the_y_is_x(text: str) -> StructuredFact | None:
    m = _THE_Y_IS_X_RE.match(text)
    if not m:
        return None
    attr = m.group("attr").strip()
    val = clean_val(m.group("val"))
    if not attr or not val or val.endswith("?"):
        return None
    if attr.casefold() in _INVALID_KEYS:
        return None

    attr_lower = attr.casefold()
    words = set(re.findall(r"[a-z0-9+#.-]+", attr_lower))

    if re.search(r"\b(target|deployment|database|db|provider|stack|hosting)\b", attr_lower):
        mtype = MemoryType.DECISION
    elif "architecture" in words or "design" in words:
        mtype = MemoryType.ARCHITECTURE
    elif "goal" in words or "objective" in words:
        mtype = MemoryType.GOAL
    elif "preference" in words or "prefer" in words:
        mtype = MemoryType.PREFERENCE
    else:
        mtype = MemoryType.FACT

    entity = attr
    if text.strip().lower().startswith("my name"):
        entity = "user"
        attr = "name"

    return StructuredFact(
        entity=entity,
        attribute=attr,
        value=val,
        memory_type=mtype,
        raw_text=text,
    )


def extract_structured_fact(text: str) -> StructuredFact | None:
    """Try all modular fact extractors on text. Return StructuredFact or None."""
    cleaned = text.strip()
    if not cleaned or is_interrogative(cleaned):
        return None

    fact = extract_building(cleaned)
    if fact:
        return fact

    fact = extract_possessive(cleaned)
    if fact:
        return fact

    fact = extract_preference(cleaned)
    if fact:
        return fact

    fact = extract_uses(cleaned)
    if fact:
        return fact

    fact = extract_the_y_is_x(cleaned)
    if fact:
        return fact

    return None

"""Deterministic candidate extraction from delta messages (no Memory AI)."""

from __future__ import annotations

import re
from typing import Iterable

from app.memory.correction import Correction, parse_correction, strip_correction_prefix
from app.memory.facts import detect_preference_domain, extract_structured_fact, slugify
from app.memory.ids import NormalizedMessage
from app.memory.interrogative import is_interrogative
from app.memory.low_info import is_low_info_message
from app.memory.revocation import parse_revocation
from app.memory.scorer import looks_like_correction, looks_speculative, score_candidate
from app.models.memory import CandidateMemory, MemoryType, StructuredFact

# Explicit typed prefixes: "decision: …", "[fact] …"
_PREFIX_RE = re.compile(
    r"^\s*(?:\[(?P<bracket>[a-z_ ]+)\]|(?P<label>[a-z_ ]+)\s*:)\s*(?P<body>.+)$",
    re.IGNORECASE | re.DOTALL,
)

_LABEL_TO_TYPE: dict[str, MemoryType] = {
    "fact": MemoryType.FACT,
    "facts": MemoryType.FACT,
    "decision": MemoryType.DECISION,
    "decisions": MemoryType.DECISION,
    "constraint": MemoryType.CONSTRAINT,
    "constraints": MemoryType.CONSTRAINT,
    "preference": MemoryType.PREFERENCE,
    "preferences": MemoryType.PREFERENCE,
    "goal": MemoryType.GOAL,
    "goals": MemoryType.GOAL,
    "architecture": MemoryType.ARCHITECTURE,
    "important_event": MemoryType.IMPORTANT_EVENT,
    "important event": MemoryType.IMPORTANT_EVENT,
    "event": MemoryType.IMPORTANT_EVENT,
    "active_task": MemoryType.ACTIVE_TASK,
    "active task": MemoryType.ACTIVE_TASK,
    "task": MemoryType.ACTIVE_TASK,
    "todo": MemoryType.ACTIVE_TASK,
}

# Key = value / Key is value  (captures topic for contradiction matching)
_KV_RE = re.compile(
    r"^\s*(?P<key>[A-Za-z][\w\s/-]{0,40}?)\s*(?:=| is | are |:=|:)\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)

_DECISION_RE = re.compile(
    r"^\s*(?:we\s+)?(?:decided(?:\s+to)?|will\s+use|are\s+using|chose|picked|"
    r"switched(?:\s+production)?\s+to|use)\s+(.+)$",
    re.IGNORECASE,
)

_CONSTRAINT_RE = re.compile(
    r"^\s*(?:(?:do\s+not|don't|never|must\s+not|cannot|can't|constraint)\b[:\s-]*)(.+)$",
    re.IGNORECASE,
)

_PREFERENCE_RE = re.compile(
    r"^\s*(?:i\s+)?(?:prefer|would\s+rather|preference)\b[:\s-]*(.+)$",
    re.IGNORECASE,
)

_GOAL_RE = re.compile(
    r"^\s*(?:goal|objective|we\s+need\s+to|aim\s+to)\b[:\s-]*(.+)$",
    re.IGNORECASE,
)

_TASK_RE = re.compile(
    r"^\s*(?:todo|task|working\s+on|next)\b[:\s-]*(.+)$",
    re.IGNORECASE,
)

_EVENT_RE = re.compile(
    r"^\s*(?:deployed|shipped|launched|released|incident)\b[:\s-]*(.+)$",
    re.IGNORECASE,
)

_ARCH_RE = re.compile(
    r"^\s*(?:architecture|stack|system\s+design)\b[:\s-]*(.+)$",
    re.IGNORECASE,
)


def topic_key_from_content(content: str, memory_type: MemoryType | None = None) -> str:
    """Stable topic key used for duplicate / contradiction matching."""
    if memory_type == MemoryType.PREFERENCE:
        _, pref_topic = detect_preference_domain(content)
        return pref_topic

    kv = _KV_RE.match(content.strip())
    if kv:
        return _slug(kv.group("key"))

    # "We decided to use Neon for production" → focus on object phrase
    decision = _DECISION_RE.match(content.strip())
    if decision:
        body = decision.group(1)
        # Prefer "use X for Y" → key from purpose or product
        for_match = re.search(r"(.+?)\s+for\s+(.+)$", body, re.IGNORECASE)
        if for_match:
            return _slug(for_match.group(2))  # purpose as topic when present
        return _slug(body)

    # Fallback: first few significant tokens
    tokens = re.findall(r"[a-z0-9]+", content.casefold())
    stop = {
        "we", "the", "a", "an", "to", "for", "and", "or", "of", "in", "on",
        "is", "are", "use", "using", "will", "decided", "our", "be",
    }
    meaningful = [t for t in tokens if t not in stop]
    if not meaningful:
        return _slug(content[:48])
    head = meaningful[:3]
    if memory_type:
        return f"{memory_type.value}:{'_'.join(head)}"
    return "_".join(head)


def _slug(text: str) -> str:
    parts = re.findall(r"[a-z0-9]+", text.casefold())
    return "_".join(parts[:6]) or "item"


def _authority_for_role(role: str, content: str) -> str:
    if looks_speculative(content):
        return "speculation"
    if role == "user":
        return "user"
    if role == "assistant":
        return "assistant"
    return "speculation"


_INVALID_KV_KEYS = frozenset(
    {
        "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
        "is", "are", "was", "were", "do", "does", "did", "can", "could",
        "will", "would", "should", "shall", "have", "has", "had", "may", "might",
    }
)


def _parse_prefix(content: str) -> tuple[MemoryType | None, str]:
    match = _PREFIX_RE.match(content)
    if not match:
        return None, content
    label = (match.group("bracket") or match.group("label") or "").strip().casefold()
    body = match.group("body").strip()
    return _LABEL_TO_TYPE.get(label), body


def _classify(content: str) -> tuple[MemoryType, str, StructuredFact | None] | None:
    typed, body = _parse_prefix(content)
    if typed is not None and body:
        if is_interrogative(body):
            return None
        sfact = extract_structured_fact(body)
        return typed, body, sfact

    if is_interrogative(content):
        return None

    # Check modular natural-language structured fact extraction
    sfact = extract_structured_fact(content)
    if sfact is not None:
        return sfact.memory_type, sfact.to_content(), sfact

    text = content.strip()
    for pattern, mtype in (
        (_CONSTRAINT_RE, MemoryType.CONSTRAINT),
        (_PREFERENCE_RE, MemoryType.PREFERENCE),
        (_GOAL_RE, MemoryType.GOAL),
        (_TASK_RE, MemoryType.ACTIVE_TASK),
        (_EVENT_RE, MemoryType.IMPORTANT_EVENT),
        (_ARCH_RE, MemoryType.ARCHITECTURE),
        (_DECISION_RE, MemoryType.DECISION),
    ):
        m = pattern.match(text)
        if m:
            body = m.group(1).strip()
            if mtype == MemoryType.DECISION:
                # Normalize decision body to a compact statement
                body = f"Use {body}" if not body.lower().startswith("use ") else body
                body = body[0].upper() + body[1:] if body else body
            return mtype, body, None

    kv = _KV_RE.match(text)
    if kv:
        key = kv.group("key").strip()
        value = kv.group("value").strip()
        if value.endswith("?") or key.casefold() in _INVALID_KV_KEYS:
            return None
        # Prefer decision when phrasing looks decisive
        if re.search(r"\b(database|db|provider|stack|hosting)\b", key, re.I):
            return MemoryType.DECISION, f"{key} = {value}", None
        return MemoryType.FACT, f"{key} = {value}", None

    return None


def extract_from_message(message: NormalizedMessage) -> list[CandidateMemory]:
    """Extract zero or more candidates from a single normalized message."""
    if message.role not in ("user", "assistant"):
        return []
    if is_low_info_message(message.content, role=message.role):
        return []
    if is_interrogative(message.content):
        return []

    # Strip leading correction markers ("Actually, ", "Correction: ", ...) and
    # re-check the remainder for interrogatives ("Actually, what did we use?").
    stripped, had_prefix = strip_correction_prefix(message.content)
    if is_interrogative(stripped):
        return []

    # Revocation / reset semantics (FIX.md §4 / todo 8.4): these statements
    # invalidate a previously stored fact rather than creating a new one.
    revocation = parse_revocation(stripped)
    if revocation is not None:
        candidate = _build_revocation_candidate(message, revocation)
        return [candidate] if candidate is not None else []

    # Try structured correction phrases: "X changed from A to B", "X now uses B
    # instead of A", "The Y was changed to B", "I changed my preference from A to B".
    correction = parse_correction(stripped)
    if correction is not None:
        candidate = _build_correction_candidate(message, correction, text=stripped)
        if candidate is not None:
            return [candidate]

    # Otherwise reclassify the prefix-stripped text; a stripped prefix still
    # marks the resulting fact as a correction.
    classified = _classify(stripped)
    if classified is None:
        return []

    mtype, body, sfact = classified
    if message.role == "assistant":
        # Assistant natural-language statements must never become user memories.
        # Only explicitly typed prefixes (e.g. [fact]...) are accepted.
        typed, _ = _parse_prefix(message.content)
        if typed is None:
            return []

    authority = _authority_for_role(message.role, message.content)
    if message.role == "assistant" and mtype in (MemoryType.DECISION, MemoryType.CONSTRAINT):
        authority = "speculation"

    topic_key = sfact.to_topic_key() if sfact is not None else topic_key_from_content(body, mtype)

    candidate = CandidateMemory(
        content=body,
        type=mtype,
        source_message_ids=[message.message_key],
        topic_key=topic_key,
        authority=authority,
        is_correction=had_prefix or looks_like_correction(message.content),
        structured_fact=sfact,
    )
    candidate.scores = score_candidate(candidate)
    return [candidate]


def _build_correction_candidate(
    message: NormalizedMessage,
    correction: Correction,
    *,
    text: str,
) -> CandidateMemory | None:
    """Build a CandidateMemory for an explicit correction (FIX.md §3)."""
    target_lower = correction.target.casefold()
    if target_lower in ("preference", "my preference", "choice"):
        # "I changed my preference from A to B" -> user preference domain
        attr, pref_topic = detect_preference_domain(correction.new_value, correction.old_value)
        attr = attr if attr != "preference" else "preference"
        sfact = StructuredFact(
            entity="user",
            attribute=attr,
            value=correction.new_value,
            memory_type=MemoryType.PREFERENCE,
            raw_text=text,
        )
        topic_key = pref_topic
        content = correction.new_value
        mtype = MemoryType.PREFERENCE
    else:
        # "The Y was changed to B" / "The Y changed to B" → target names the attribute
        # directly (deployment target, database, password, ...). Reuse the same
        # conventions as extract_the_y_is_x so the correction supersedes cleanly.
        if not correction.old_value:
            attr = correction.target.strip()
            attr_lower = attr.casefold()
            if re.search(r"\b(target|deployment|database|db|provider|stack|hosting)\b", attr_lower):
                mtype = MemoryType.DECISION
            elif "preference" in attr_lower or "prefer" in attr_lower:
                mtype = MemoryType.PREFERENCE
            else:
                mtype = MemoryType.FACT
            sfact = StructuredFact(
                entity=attr,
                attribute=attr,
                value=correction.new_value,
                memory_type=mtype,
                raw_text=text,
            )
            topic_key = sfact.to_topic_key()
            content = sfact.to_content()
        else:
            # Entity-property correction, e.g. "Cloudisy changed from Neon to ..."
            attr, _ = detect_preference_domain(correction.new_value, correction.old_value)
            if attr in ("database", "ui_library", "frontend_framework", "theme", "workflow"):
                mtype = MemoryType.DECISION
            else:
                attr = "technology"
                mtype = MemoryType.FACT
            sfact = StructuredFact(
                entity=correction.target,
                attribute=attr,
                value=correction.new_value,
                memory_type=mtype,
                raw_text=text,
            )
            topic_key = sfact.to_topic_key()
            content = sfact.to_content()

    authority = _authority_for_role(message.role, message.content)
    candidate = CandidateMemory(
        content=content,
        type=mtype,
        source_message_ids=[message.message_key],
        topic_key=topic_key,
        authority=authority,
        is_correction=True,
        structured_fact=sfact,
        correction=correction,
    )
    candidate.scores = score_candidate(candidate)
    return candidate


def _build_revocation_candidate(
    message: NormalizedMessage,
    revocation: "object",
) -> CandidateMemory | None:
    """Build a CandidateMemory that marks a prior fact as revoked (todo 8.4)."""
    if message.role not in ("user",):
        return None
    from app.memory.revocation import Revocation

    if not isinstance(revocation, Revocation):
        return None
    candidate = CandidateMemory(
        content=f"REVOKE: {revocation.target}",
        type=MemoryType.FACT,
        source_message_ids=[message.message_key],
        topic_key="__revocation__",
        authority="user",
        revocation=revocation,
    )
    candidate.scores = score_candidate(candidate)
    return candidate


def extract_candidates(messages: Iterable[NormalizedMessage]) -> list[CandidateMemory]:
    out: list[CandidateMemory] = []
    for msg in messages:
        out.extend(extract_from_message(msg))
    return out

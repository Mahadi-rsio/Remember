"""Per-item score axes for canonical memory candidates."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.models.memory import CandidateMemory, MemoryScores, MemoryType

# Speculative language lowers confidence / authority.
_SPECULATIVE_RE = re.compile(
    r"\b(might|maybe|perhaps|could|possibly|probably|i think|we might|"
    r"considering|not sure|unsure|tentative)\b",
    re.IGNORECASE,
)

_DECISION_MARKERS = re.compile(
    r"\b(decided|decision|we will|we'll|we are using|we're using|chose|chosen|"
    r"switched to|use .+ for)\b",
    re.IGNORECASE,
)

_CORRECTION_MARKERS = re.compile(
    r"\b(actually|correction|not\b.+\bbut\b|instead of|no longer|"
    r"changed (to|from)|switch(?:ed)? to)\b",
    re.IGNORECASE,
)

# Baseline importance by type
_TYPE_IMPORTANCE: dict[MemoryType, float] = {
    MemoryType.DECISION: 0.90,
    MemoryType.CONSTRAINT: 0.88,
    MemoryType.GOAL: 0.80,
    MemoryType.ARCHITECTURE: 0.82,
    MemoryType.PREFERENCE: 0.70,
    MemoryType.FACT: 0.65,
    MemoryType.IMPORTANT_EVENT: 0.75,
    MemoryType.ACTIVE_TASK: 0.72,
}


def looks_speculative(text: str) -> bool:
    return bool(_SPECULATIVE_RE.search(text))


def looks_like_correction(text: str) -> bool:
    return bool(_CORRECTION_MARKERS.search(text))


def content_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.casefold().strip(), b.casefold().strip()).ratio()


def score_candidate(
    candidate: CandidateMemory,
    *,
    existing_contents: list[str] | None = None,
) -> MemoryScores:
    """Assign confidence / importance / stability / freshness / information_gain."""
    text = candidate.content
    speculative = looks_speculative(text) or candidate.authority == "speculation"
    user_authority = candidate.authority == "user" and not speculative

    if candidate.type == MemoryType.DECISION and user_authority:
        confidence = 0.95
    elif user_authority:
        confidence = 0.88
    elif candidate.authority == "assistant" and not speculative:
        confidence = 0.70
    else:
        confidence = 0.55

    if speculative:
        confidence = min(confidence, 0.60)

    if candidate.is_correction or looks_like_correction(text):
        confidence = max(confidence, 0.92)

    if _DECISION_MARKERS.search(text) and user_authority:
        confidence = max(confidence, 0.93)

    importance = _TYPE_IMPORTANCE.get(candidate.type, 0.60)
    if candidate.is_correction:
        importance = max(importance, 0.90)

    stability = 0.55 if user_authority else 0.35
    if speculative:
        stability = min(stability, 0.30)

    freshness = 1.0

    info_gain = _information_gain(text, existing_contents or [])
    return MemoryScores(
        confidence=round(confidence, 3),
        importance=round(importance, 3),
        stability=round(stability, 3),
        freshness=freshness,
        information_gain=round(info_gain, 3),
    )


def _information_gain(content: str, existing: list[str]) -> float:
    if not existing:
        return 0.85
    best = max(content_similarity(content, other) for other in existing)
    if best >= 0.92:
        return 0.05  # near-duplicate confirmation
    if best >= 0.75:
        return 0.25  # soft update / paraphrase
    return 0.80  # new information


# Gate: below this, skip creating a new row (merge/confirm handled separately).
INFO_GAIN_WRITE_THRESHOLD = 0.15


def should_write_new_item(scores: MemoryScores) -> bool:
    return scores.information_gain >= INFO_GAIN_WRITE_THRESHOLD

"""Revocation / reset detection (FIX.md §4 / todo 8.4).

Recognizes statements that invalidate previously stored memory (e.g. "the
password was reset", "ignore the previous password") and captures what should be
revoked (a target like "password") plus an optional value to match (e.g.
"temp1234"). The memory engine marks the matching active item(s) REVOKED while
preserving them in the raw archive; revoked items are excluded from compiled
context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Revocation:
    """Structured revocation: what to invalidate, and optionally which value."""

    target: str
    value: str = ""


# "The demo password was reset."
# "The temporary password was reset; ignore temp1234."
_RESET_RE = re.compile(
    r"^(?:the\s+|that\s+|this\s+|temporary\s+|previous\s+|old\s+)?"
    r"(?P<target>[\w\s/-]+?)\s+was\s+reset\b",
    re.IGNORECASE,
)

# "Ignore the previous password."
_IGNORE_RE = re.compile(
    r"^(?:please\s+)?ignore\s+(?:the\s+)?(?:previous|old|earlier|last)\s+"
    r"(?P<target>[\w\s/-]+?)\s*[.!]?$",
    re.IGNORECASE,
)

# "That password is no longer valid."
_NO_LONGER_VALID_RE = re.compile(
    r"^(?:the\s+|that\s+|this\s+)?(?P<target>[\w\s/-]+?)\s+(?:is|are)\s+no\s+"
    r"longer\s+valid\b",
    re.IGNORECASE,
)

# "X has been revoked."
_REVOKED_RE = re.compile(
    r"^(?:the\s+)?(?P<target>[\w\s/-]+?)\s+has\s+been\s+revoked\b",
    re.IGNORECASE,
)

# "Forget the previous value." / "Forget the password."
_FORGET_RE = re.compile(
    r"^forget\s+(?:the\s+)?(?:previous|old|earlier|last\s+)?"
    r"(?P<target>[\w\s/-]*?)\s*[.!]?$",
    re.IGNORECASE,
)

# Trailing value after a semicolon/comma or following "ignore"/"instead", e.g.
# "temp1234", "ABCxyz". The captured token must not be a common English word so
# verbs like "was"/"reset" are not mistaken for a value.
_COMMON_WORDS = frozenset(
    {
        "was", "were", "is", "are", "has", "have", "had", "been", "reset",
        "ignored", "revoked", "the", "and", "that", "this", "its", "it",
        "from", "to", "for", "with", "now", "previous", "old", "new",
    }
)
_VALUE_RE = re.compile(
    r"(?:ignore|instead|forget)\s+(?:it\s+)?(?:the\s+)?(?:old\s+|previous\s+)?"
    r"[\"']?(?P<value>[A-Za-z0-9][A-Za-z0-9_-]{2,})[\"']?",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    return text.strip().strip("'\"`").strip().rstrip(".!?").strip()


def _extract_value(text: str, target: str) -> str:
    target_words = {w for w in re.findall(r"[a-z0-9]+", target.casefold())}
    for m in _VALUE_RE.finditer(text):
        val = _clean(m.group("value"))
        if val.casefold() not in _COMMON_WORDS and val.casefold() not in target_words:
            return val
    return ""


def parse_revocation(text: str) -> Revocation | None:
    """Parse a revocation/reset phrase into a Revocation, or None.

    Recognizes forms like:
      - "The demo password was reset."
      - "Ignore the previous password."
      - "That password is no longer valid."
      - "X has been revoked."
      - "Forget the previous value."
    """
    if not text:
        return None

    target: str | None = None
    for regex in (_RESET_RE, _IGNORE_RE, _NO_LONGER_VALID_RE, _REVOKED_RE, _FORGET_RE):
        m = regex.match(text.strip())
        if m:
            target = m.group("target").strip()
            if target:
                break

    if not target:
        return None

    value = _extract_value(text, target)
    return Revocation(target=_clean(target), value=value)

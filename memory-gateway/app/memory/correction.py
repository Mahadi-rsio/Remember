"""Explicit correction detection and structured records (FIX.md §3 / todo 8.3).

Corrections are represented explicitly (target, old_value, new_value) rather than
silently creating an independent contradictory fact. A correction supersedes the
matching active fact and records a structured CorrectionRecord.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Correction:
    """Structured correction: what changed, from what, to what."""

    target: str
    old_value: str
    new_value: str


# Prefixes that signal a correction but carry no structural content of their own.
_CORRECTION_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"actually[,:]?\s+|"
    r"correction[,:]?\s+|"
    r"no[,:]?\s+|"
    r"wait[,:]?\s+|"
    r"on\s+second\s+thought[,:]?\s+|"
    r"to\s+clarify[,:]?\s+|"
    r"i\s+meant[,:]?\s+|"
    r"let\s+me\s+correct\s+that[,:]?\s+|"
    r"scratch\s+that[,:]?\s+"
    r")",
    re.IGNORECASE,
)


def strip_correction_prefix(text: str) -> tuple[str, bool]:
    """Strip a leading correction marker like 'Actually, '.

    Returns (stripped_text, was_correction). If no marker is present the original
    text is returned unchanged with was_correction=False.
    """
    m = _CORRECTION_PREFIX_RE.match(text)
    if not m:
        return text, False
    return text[m.end():].strip(), True


# "Cloudisy changed from Neon to self-hosted PostgreSQL."
_CHANGED_FROM_TO_RE = re.compile(
    r"^(?:the\s+)?(?P<target>[A-Za-z][\w\s/-]{0,30}?)\s+changed\s+from\s+"
    r"(?P<old>.+?)\s+to\s+(?P<new>.+?)\s*[.!]?$",
    re.IGNORECASE,
)

# "Cloudisy now uses self-hosted PostgreSQL instead of Neon."
# "Cloudisy uses self-hosted PostgreSQL instead of Neon."
_USES_INSTEAD_OF_RE = re.compile(
    r"^(?:the\s+)?(?P<target>[A-Za-z][\w\s/-]{0,30}?)\s+(?:now\s+)?uses\s+"
    r"(?P<new>.+?)\s+instead\s+of\s+(?P<old>.+?)\s*[.!]?$",
    re.IGNORECASE,
)

# "The database was changed to self-hosted PostgreSQL."
_WAS_CHANGED_TO_RE = re.compile(
    r"^the\s+(?P<target>[A-Za-z][\w\s/-]{0,30}?)\s+was\s+changed\s+to\s+"
    r"(?P<new>.+?)\s*[.!]?$",
    re.IGNORECASE,
)

# "I changed my preference from dark mode to light mode."
_I_CHANGED_FROM_TO_RE = re.compile(
    r"^i\s+changed\s+(?:my\s+)?(?P<target>[A-Za-z][\w\s/-]{0,30}?)\s+from\s+"
    r"(?P<old>.+?)\s+to\s+(?P<new>.+?)\s*[.!]?$",
    re.IGNORECASE,
)

# "The deployment target changed to AWS Lambda."
_TARGET_CHANGED_TO_RE = re.compile(
    r"^the\s+(?P<target>[A-Za-z][\w\s/-]{0,30}?)\s+changed\s+to\s+"
    r"(?P<new>.+?)\s*[.!]?$",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    return text.strip().strip("'\"`").strip().rstrip(".!?").strip()


def parse_correction(text: str) -> Correction | None:
    """Parse a structured correction phrase into a Correction, or None.

    Accepts forms like:
      - "X changed from A to B"
      - "X now uses B instead of A"
      - "The Y was changed to B"
      - "I changed my preference from A to B"
      - "The Y changed to B" (no explicit old value)
    """
    if not text:
        return None

    m = _CHANGED_FROM_TO_RE.match(text)
    if m:
        return Correction(
            target=_clean(m.group("target")),
            old_value=_clean(m.group("old")),
            new_value=_clean(m.group("new")),
        )

    m = _USES_INSTEAD_OF_RE.match(text)
    if m:
        return Correction(
            target=_clean(m.group("target")),
            old_value=_clean(m.group("old")),
            new_value=_clean(m.group("new")),
        )

    m = _I_CHANGED_FROM_TO_RE.match(text)
    if m:
        return Correction(
            target=_clean(m.group("target")),
            old_value=_clean(m.group("old")),
            new_value=_clean(m.group("new")),
        )

    m = _WAS_CHANGED_TO_RE.match(text)
    if m:
        return Correction(
            target=_clean(m.group("target")),
            old_value="",
            new_value=_clean(m.group("new")),
        )

    m = _TARGET_CHANGED_TO_RE.match(text)
    if m:
        return Correction(
            target=_clean(m.group("target")),
            old_value="",
            new_value=_clean(m.group("new")),
        )

    return None

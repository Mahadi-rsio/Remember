"""Deterministic low-information message detection."""

from __future__ import annotations

import re
import unicodedata

# Phrases that carry negligible new memory (PROMT §7 / plan Phase 3).
_LOW_INFO_PHRASES: frozenset[str] = frozenset(
    {
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
    }
)

_PUNCT_RE = re.compile(r"[^\w\s+]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def normalize_utterance(text: str) -> str:
    """Lowercase, strip punctuation/emoji noise, collapse whitespace."""
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", text).casefold().strip()
    folded = _PUNCT_RE.sub(" ", folded)
    folded = _SPACE_RE.sub(" ", folded).strip()
    return folded


def is_low_info_message(content: str, *, role: str = "user") -> bool:
    """
    True when the turn should skip memory extraction / Memory AI.

    Only short acknowledgements and confirmations qualify. Assistant/tool
    messages are not treated as low-info by phrase match alone (tool outputs
    may still be skipped later by role filters in the extractor).
    """
    if role not in ("user", "assistant"):
        return False
    normalized = normalize_utterance(content)
    if not normalized:
        return True
    if normalized in _LOW_INFO_PHRASES:
        return True
    words = normalized.split()
    if words and all(w in _LOW_INFO_PHRASES for w in words):
        return True
    # Very short single-token acks after normalization
    if " " not in normalized and len(normalized) <= 3 and normalized.isalpha():
        return normalized in _LOW_INFO_PHRASES or normalized in {"ok", "k", "kk"}
    return False

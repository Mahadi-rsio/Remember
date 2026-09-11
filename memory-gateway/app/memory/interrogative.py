"""Deterministic interrogative and question classification.

Ensures questions, inquiries, and interrogative noise are never extracted as
factual memories (FIX.md §1 / todo.md §8.1).
Guards legitimate declarative statements containing question words.
"""

from __future__ import annotations

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^\w\s+]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")

# 1. Trailing question mark: ends with ? (ignoring trailing quotes / whitespace)
_ENDS_WITH_QUESTION_RE = re.compile(r"\?\s*[\"']?\s*$")

# 2. Direct wh-question with inverted auxiliary verb:
# e.g. "What is my name", "Why did we choose PostgreSQL", "When is the launch",
# "Where is the project deployed", "How does Cloudisy work", "Who is the lead"
_WH_AUX_RE = re.compile(
    r"^\s*(?:what|when|where|why|who|whom|whose|how)"
    r"(?:'s|'re|'d)?\s+"
    r"(?:is|are|am|was|were|do|does|did|can|could|will|would|should|shall|have|has|had|may|might|must)\b",
    re.IGNORECASE,
)

# 3. Wh-contracted forms: "what's ...", "who's ...", "where's ...", "how's ...", "when's ..."
_WH_CONTRACTED_RE = re.compile(
    r"^\s*(?:what|when|where|why|who|how)'s\b",
    re.IGNORECASE,
)

# 4. How + quantity/degree modifier:
# "how much", "how many", "how long", "how often", "how fast", "how far", "how come"
_HOW_MODIFIER_RE = re.compile(
    r"^\s*how\s+(?:much|many|long|often|fast|far|come)\b",
    re.IGNORECASE,
)

# 5. Wh-determiner + noun phrase + auxiliary:
# e.g. "Which UI library do I prefer", "What database does Cloudisy use", "Which database is active"
# Negative lookahead ensures subject pronouns (we, i, they, etc.) are excluded so declarative
# pseudo-cleft sentences like "What we decided is to use Neon" are never matched.
_WH_NOUN_AUX_RE = re.compile(
    r"^\s*(?:what|which)\s+"
    r"(?!(?:we|i|you|they|he|she|it)\b)"
    r"(?:[a-z0-9_-]+\s+){1,3}"
    r"(?:is|are|am|was|were|do|does|did|can|could|will|would|should|shall|have|has|had)\b",
    re.IGNORECASE,
)

# 6. Inversion questions starting with auxiliary verbs:
# e.g. "Do we use PostgreSQL", "Did we choose Neon", "Is PostgreSQL supported",
# "Can you tell me...", "Are we using Redis", "Will the launch be next month"
# Excludes negative imperatives/constraints like "Do not ...", "Don't ...", "Must not ..."
_INVERSION_AUX_RE = re.compile(
    r"^\s*(?:is|are|am|was|were|do|does|did|can|could|would|should|shall)\s+"
    r"(?!(?:not\b|n't\b))"
    r"(?:we|you|they|he|she|it|i|there|this|that|the|a|an|[a-z0-9_-]+)\b|"
    r"^\s*will\s+(?:we|you|they|he|she|it|i|there|this|that|the|a|an)\b|"
    r"^\s*(?:have|had)\s+(?:we|you|they|i)\b|"
    r"^\s*has\s+(?:the|it|this|that|anyone|everyone|[a-z0-9_-]+)\b|"
    r"^\s*may\s+(?:i|we)\b",
    re.IGNORECASE,
)

# 7. Inquiry requests:
# e.g. "tell me what ...", "can you tell me ...", "please explain ...", "remind me ..."
_INQUIRY_REQUEST_RE = re.compile(
    r"^\s*(?:can\s+you\s+|could\s+you\s+|please\s+)?(?:tell\s+me|remind\s+me|show\s+me|explain|let\s+me\s+know|find\s+out|check\s+if|check\s+whether)\b",
    re.IGNORECASE,
)

# 8. Standalone question words / conversational filler
_STANDALONE_QUESTION_WORDS = frozenset(
    {"what", "why", "how", "who", "whom", "whose", "when", "where", "which"}
)


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", text).casefold().strip()
    folded = _PUNCT_RE.sub(" ", folded)
    folded = _SPACE_RE.sub(" ", folded).strip()
    return folded


def is_interrogative(text: str) -> bool:
    """
    Return True if the text is an interrogative sentence or question.

    Guards legitimate declarative statements containing question-like words
    (e.g. 'The reason why we chose PostgreSQL is reliability',
    'Where we deploy is AWS Lambda', 'I prefer TypeScript', etc.).
    """
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False

    # 1. Trailing question mark: ends with ? (ignoring trailing quotes / whitespace)
    if _ENDS_WITH_QUESTION_RE.search(stripped):
        return True

    # 2. Standalone question words (e.g. "what", "why?", "how")
    if _normalize(stripped) in _STANDALONE_QUESTION_WORDS:
        return True

    # 3. Direct wh-question + aux: "What is my name", "Why did we choose PostgreSQL"
    if _WH_AUX_RE.search(stripped):
        return True

    # 4. Wh-contracted: "What's my name", "Where's the server"
    if _WH_CONTRACTED_RE.search(stripped):
        return True

    # 5. How + modifier: "How much memory...", "How long..."
    if _HOW_MODIFIER_RE.search(stripped):
        return True

    # 6. Wh-noun + aux: "Which database do we use", "What database does Cloudisy use now"
    if _WH_NOUN_AUX_RE.search(stripped):
        return True

    # 7. Inversion questions: "Do we use PostgreSQL", "Is the deployment target AWS Lambda"
    if _INVERSION_AUX_RE.search(stripped):
        return True

    # 8. Inquiry requests: "Tell me what database we use", "Can you explain..."
    if _INQUIRY_REQUEST_RE.search(stripped):
        return True

    return False

"""Context selection scoring and budget optimization (no naive head/tail truncation)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.context.tokens import estimate_message_tokens, estimate_tokens
from app.memory.low_info import is_low_info_message, normalize_utterance, _LOW_INFO_PHRASES
from app.memory.scorer import _DECISION_MARKERS
from app.storage.models import MemoryItem

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "at", "by",
    "for", "with", "about", "against", "between", "into", "through", "during", "before",
    "after", "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
    "over", "under", "again", "further", "then", "once", "here", "there", "all", "any",
    "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "s", "t", "can", "will", "just",
    "don", "should", "now", "i", "me", "my", "we", "our", "you", "your", "he", "she",
    "it", "they", "them", "what", "which", "who", "whom", "this", "that", "these", "those",
    "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "having",
    "do", "does", "did", "doing",
}


def _extract_keywords(text: str) -> set[str]:
    words = _WORD_RE.findall(text.casefold())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def compute_relevance(text: str, query_keywords: set[str]) -> float:
    """Compute lexical relevance score between item content and user query keywords."""
    if not query_keywords:
        return 0.5  # Neutral baseline when query has no specific keywords
    item_keywords = _extract_keywords(text)
    if not item_keywords:
        return 0.3
    overlap = len(query_keywords.intersection(item_keywords))
    if overlap == 0:
        return 0.25
    # Jaccard-like boost with ceiling
    ratio = overlap / len(query_keywords)
    return min(1.0, 0.4 + (ratio * 0.6))


@dataclass
class SelectableItem:
    item_id: str
    kind: str  # "system" | "canonical_memory" | "message" | "tool_result" | "new_message"
    content: str
    token_cost: int
    raw_message: dict[str, Any] | None = None
    memory_item: MemoryItem | None = None
    ordinal: int = 0
    mandatory: bool = False

    # 6 score dimensions:
    relevance: float = 0.5
    confidence: float = 0.5
    importance: float = 0.5
    freshness: float = 0.5
    stability: float = 0.5
    information_gain: float = 0.5

    @property
    def value(self) -> float:
        """Composite value across the 6 axes (range ~ 0.0 to 1.0)."""
        score = (
            0.25 * self.relevance
            + 0.25 * self.importance
            + 0.20 * self.freshness
            + 0.10 * self.confidence
            + 0.10 * self.stability
            + 0.10 * self.information_gain
        )
        return round(min(1.0, max(0.0, score)), 4)

    @property
    def selection_score(self) -> float:
        """Knapsack density: value / token_cost."""
        return self.value / max(1, self.token_cost)


def score_message_item(
    message: dict[str, Any],
    *,
    index: int,
    total_messages: int,
    query_keywords: set[str],
    is_latest: bool = False,
) -> SelectableItem:
    role = message.get("role", "user")
    content = str(message.get("content") or "")
    tokens = estimate_message_tokens(message)

    if role == "system":
        return SelectableItem(
            item_id=f"msg-{index}",
            kind="system",
            content=content,
            token_cost=tokens,
            raw_message=message,
            ordinal=index,
            mandatory=True,
            relevance=0.8,
            confidence=1.0,
            importance=1.0,
            freshness=1.0,
            stability=1.0,
            information_gain=0.9,
        )

    if is_latest:
        return SelectableItem(
            item_id=f"msg-{index}",
            kind="new_message",
            content=content,
            token_cost=tokens,
            raw_message=message,
            ordinal=index,
            mandatory=True,
            relevance=1.0,
            confidence=1.0,
            importance=1.0,
            freshness=1.0,
            stability=0.9,
            information_gain=0.95,
        )

    turns_from_end = (total_messages - 1) - index
    freshness = max(0.2, 1.0 - (turns_from_end * 0.08))
    low_info = is_low_info_message(content, role=role)

    # Base importance by role and content
    if role == "tool":
        kind = "tool_result"
        importance = 0.65 if turns_from_end <= 2 else 0.40
        stability = 0.70
        confidence = 0.90
    else:
        kind = "message"
        importance = 0.85 if turns_from_end <= 3 else 0.50
        stability = 0.80 if role == "user" else 0.65
        confidence = 0.95 if role == "user" else 0.80

    norm = normalize_utterance(content)
    is_ack = low_info or (norm in _LOW_INFO_PHRASES) or (all(w in _LOW_INFO_PHRASES for w in norm.split()) if norm else True)

    if _DECISION_MARKERS.search(content):
        importance = max(importance, 0.92)
        stability = max(stability, 0.90)

    if is_ack:
        importance = 0.05
        information_gain = 0.05
        stability = 0.10
        freshness = 0.10
    else:
        information_gain = 0.85 if turns_from_end <= 2 else 0.60

    relevance = compute_relevance(content, query_keywords)

    return SelectableItem(
        item_id=f"msg-{index}",
        kind=kind,
        content=content,
        token_cost=tokens,
        raw_message=message,
        ordinal=index,
        mandatory=False,
        relevance=round(relevance, 3),
        confidence=confidence,
        importance=importance,
        freshness=round(freshness, 3),
        stability=stability,
        information_gain=information_gain,
    )


def score_canonical_item(
    item: MemoryItem,
    *,
    ordinal: int,
    query_keywords: set[str],
) -> SelectableItem:
    tokens = estimate_tokens(f"{item.type}: {item.content}") + 2
    relevance = compute_relevance(item.content, query_keywords)

    return SelectableItem(
        item_id=f"mem-{item.id or ordinal}",
        kind="canonical_memory",
        content=item.content,
        token_cost=tokens,
        memory_item=item,
        ordinal=ordinal,
        mandatory=False,
        relevance=round(relevance, 3),
        confidence=item.confidence or 0.85,
        importance=item.importance or 0.80,
        freshness=item.freshness or 0.90,
        stability=item.stability or 0.80,
        information_gain=item.information_gain or 0.75,
    )


def _greedy_density(items: Sequence[SelectableItem], capacity: int) -> list[SelectableItem]:
    sorted_items = sorted(
        items,
        key=lambda x: (x.selection_score, x.value, x.freshness),
        reverse=True,
    )
    chosen: list[SelectableItem] = []
    rem = capacity
    for item in sorted_items:
        if item.token_cost <= rem:
            chosen.append(item)
            rem -= item.token_cost
    return chosen


def _greedy_value(items: Sequence[SelectableItem], capacity: int) -> list[SelectableItem]:
    sorted_items = sorted(
        items,
        key=lambda x: (x.value, x.selection_score, x.freshness),
        reverse=True,
    )
    chosen: list[SelectableItem] = []
    rem = capacity
    for item in sorted_items:
        if item.token_cost <= rem:
            chosen.append(item)
            rem -= item.token_cost
    return chosen


def _solve_knapsack(items: Sequence[SelectableItem], capacity: int) -> list[SelectableItem]:
    if not items or capacity <= 0:
        return []

    # Fast path: if all items fit, return them all
    total_w = sum(x.token_cost for x in items)
    if total_w <= capacity:
        return list(items)

    # Use DP for standard budgets to guarantee globally optimal value selection
    if capacity * len(items) <= 400_000:
        n = len(items)
        dp = [0.0] * (capacity + 1)
        # Bitmask or array for tracking selected items
        keep = [[False] * (capacity + 1) for _ in range(n)]

        for i, item in enumerate(items):
            w = item.token_cost
            v = item.value
            if w > capacity:
                continue
            for cap in range(capacity, w - 1, -1):
                if dp[cap - w] + v > dp[cap]:
                    dp[cap] = dp[cap - w] + v
                    keep[i][cap] = True

        selected: list[SelectableItem] = []
        curr_cap = capacity
        for i in range(n - 1, -1, -1):
            if keep[i][curr_cap]:
                selected.append(items[i])
                curr_cap -= items[i].token_cost
        return selected

    # 2-pass greedy approximation for very large budgets
    cand1 = _greedy_density(items, capacity)
    cand2 = _greedy_value(items, capacity)
    v1 = sum(x.value for x in cand1)
    v2 = sum(x.value for x in cand2)
    return cand1 if v1 >= v2 else cand2


def select_items_for_budget(
    candidates: Sequence[SelectableItem],
    budget: int,
) -> list[SelectableItem]:
    """
    Select items respecting token budget without naive head/tail truncation.

    1. Mandatory items (system prompt, new user message) are always retained.
    2. Remaining budget is filled using constrained optimization (0/1 knapsack).
    3. Final selection is returned sorted by ordinal to preserve logical order.
    """
    mandatory = [c for c in candidates if c.mandatory]
    optional = [c for c in candidates if not c.mandatory]

    mandatory_tokens = sum(m.token_cost for m in mandatory)
    remaining_budget = budget - mandatory_tokens

    selected = list(mandatory)

    if remaining_budget <= 0:
        # Budget already saturated by mandatory items
        selected.sort(key=lambda x: x.ordinal)
        return selected

    chosen_optional = _solve_knapsack(optional, remaining_budget)
    selected.extend(chosen_optional)

    # Restore original chronological / logical ordering
    selected.sort(key=lambda x: x.ordinal)
    return selected

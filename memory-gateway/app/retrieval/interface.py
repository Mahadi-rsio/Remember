"""Abstract Retriever interface."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RetrievalResult:
    """A single retrieved item."""

    source: str  # 'messages' | 'memory_items'
    row_id: int
    content: str
    role: str = ""
    item_type: str = ""
    topic_key: str = ""
    conversation_id: str = ""
    score: float = 0.0
    metadata: dict = field(default_factory=dict)


class Retriever(ABC):
    @abstractmethod
    def search_messages(
        self,
        query: str,
        conversation_id: str,
        limit: int = 10,
    ) -> list[RetrievalResult]: ...

    @abstractmethod
    def search_memory(
        self,
        query: str,
        conversation_id: str,
        limit: int = 10,
    ) -> list[RetrievalResult]: ...

    def search_all(
        self,
        query: str,
        conversation_id: str,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        msgs = self.search_messages(query, conversation_id, limit)
        mems = self.search_memory(query, conversation_id, limit)
        combined = msgs + mems
        combined.sort(key=lambda r: r.score, reverse=True)
        return combined[:limit]

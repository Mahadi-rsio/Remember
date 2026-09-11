"""Stub embedding retriever — placeholder for future vector search.

This module intentionally does nothing in MVP (Phase 6).  It will be
activated in a later phase when an embedding model is configured.
All code in this module MUST remain off the hot path.
"""
from __future__ import annotations

import logging

from app.retrieval.interface import Retriever, RetrievalResult

logger = logging.getLogger(__name__)


class EmbeddingRetriever(Retriever):
    """Stub: always returns empty; not wired into any hot path."""

    def search_messages(
        self,
        query: str,
        conversation_id: str,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        logger.debug("EmbeddingRetriever.search_messages called (stub — returning [])")
        return []

    def search_memory(
        self,
        query: str,
        conversation_id: str,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        logger.debug("EmbeddingRetriever.search_memory called (stub — returning [])")
        return []

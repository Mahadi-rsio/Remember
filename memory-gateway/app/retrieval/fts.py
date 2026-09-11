"""SQLite FTS5 Retriever backend."""
from __future__ import annotations

import logging

from sqlalchemy import text

from app.retrieval.interface import Retriever, RetrievalResult
from app.storage.db import get_engine

logger = logging.getLogger(__name__)


class FTSRetriever(Retriever):
    """FTS5-backed retriever. Scoped to a conversation."""

    def search_messages(
        self,
        query: str,
        conversation_id: str,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        if not query.strip():
            return []
        try:
            engine = get_engine()
            with engine.connect() as conn:
                rows = conn.execute(
                    text("""
                        SELECT m.id, m.content, m.role, m.conversation_id,
                               bm25(messages_fts) AS score
                        FROM messages_fts
                        JOIN messages m ON m.id = messages_fts.rowid
                        WHERE messages_fts MATCH :q
                          AND m.conversation_id = :conv_id
                        ORDER BY score
                        LIMIT :lim
                    """),
                    {"q": query, "conv_id": conversation_id, "lim": limit},
                ).fetchall()
            return [
                RetrievalResult(
                    source="messages",
                    row_id=r[0],
                    content=r[1],
                    role=r[2],
                    conversation_id=r[3],
                    score=-r[4],  # bm25 returns negative; invert to positive
                )
                for r in rows
            ]
        except Exception:
            logger.exception("FTS messages search failed")
            return []

    def search_memory(
        self,
        query: str,
        conversation_id: str,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        if not query.strip():
            return []
        try:
            engine = get_engine()
            with engine.connect() as conn:
                rows = conn.execute(
                    text("""
                        SELECT mi.id, mi.content, mi.type, mi.topic_key,
                               mi.conversation_id, bm25(memory_items_fts) AS score
                        FROM memory_items_fts
                        JOIN memory_items mi ON mi.id = memory_items_fts.rowid
                        WHERE memory_items_fts MATCH :q
                          AND mi.conversation_id = :conv_id
                          AND mi.status = 'active'
                        ORDER BY score
                        LIMIT :lim
                    """),
                    {"q": query, "conv_id": conversation_id, "lim": limit},
                ).fetchall()
            return [
                RetrievalResult(
                    source="memory_items",
                    row_id=r[0],
                    content=r[1],
                    item_type=r[2],
                    topic_key=r[3],
                    conversation_id=r[4],
                    score=-r[5],
                )
                for r in rows
            ]
        except Exception:
            logger.exception("FTS memory search failed")
            return []

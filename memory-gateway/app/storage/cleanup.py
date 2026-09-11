"""Retention cleanup: delete records older than retention_days.

Only runs when retention_days > 0. Removes:
- messages older than the cutoff
- memory_items older than the cutoff
- context_versions older than the cutoff
- conversations with no remaining messages (orphaned)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.storage.db import get_engine

logger = logging.getLogger(__name__)


def run_retention_cleanup(db_path: str | None = None, retention_days: int = 0) -> None:
    """Delete data older than retention_days from all tables.

    Args:
        db_path: Unused (engine already initialised by app startup). Kept
                 for API compatibility with callers that pass it.
        retention_days: Records created before (now - retention_days) are
                        deleted. 0 means keep forever (no-op).
    """
    if retention_days <= 0:
        logger.debug("[cleanup] retention disabled (retention_days=%d)", retention_days)
        return

    cutoff: datetime = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_iso: str = cutoff.isoformat()

    logger.info(
        "[cleanup] running retention cleanup: deleting records older than %s (cutoff=%s)",
        retention_days,
        cutoff_iso,
    )

    try:
        engine = get_engine()
    except RuntimeError:
        logger.warning("[cleanup] database not initialised; skipping retention cleanup")
        return

    try:
        with engine.connect() as conn:
            # Delete old messages
            result = conn.execute(
                text("DELETE FROM messages WHERE created_at < :cutoff"),
                {"cutoff": cutoff_iso},
            )
            logger.info("[cleanup] deleted %d old messages", result.rowcount)

            # Delete old memory items
            result = conn.execute(
                text("DELETE FROM memory_items WHERE created_at < :cutoff"),
                {"cutoff": cutoff_iso},
            )
            logger.info("[cleanup] deleted %d old memory_items", result.rowcount)

            # Delete old context versions
            result = conn.execute(
                text("DELETE FROM context_versions WHERE created_at < :cutoff"),
                {"cutoff": cutoff_iso},
            )
            logger.info("[cleanup] deleted %d old context_versions", result.rowcount)

            # Remove orphaned conversations (those with no messages left)
            result = conn.execute(
                text(
                    """DELETE FROM conversations
                       WHERE id NOT IN (SELECT DISTINCT conversation_id FROM messages)"""
                )
            )
            logger.info("[cleanup] deleted %d orphaned conversations", result.rowcount)

            conn.commit()

        logger.info("[cleanup] retention cleanup complete")
    except Exception:
        logger.exception("[cleanup] retention cleanup failed")

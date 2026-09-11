"""Background job hooks for embeddings, consolidation, repair, and cleanup.

All jobs are fire-and-forget coroutines. They must:
- Never raise out (fail-open).
- Never block the main forwarding hot path.
- Be idempotent (safe to run multiple times).

Phase 6 implementation: stubs wired to asyncio hooks. Actual logic
(embedding generation, consolidation) is a future extension.
Phase 7 additions: retention cleanup on startup + daily recurring task.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# Handle for the daily retention task so it can be cancelled cleanly.
_retention_task: asyncio.Task | None = None


async def run_embedding_job(conversation_id: str) -> None:
    """Stub: generate / upsert embeddings for new messages and memory items.

    Will call an embedding model and store vectors when embeddings are
    enabled (off by default in MVP).
    """
    try:
        logger.debug("[background] embedding job skipped (stub) conv=%s", conversation_id)
        await asyncio.sleep(0)  # yield control
    except Exception:
        logger.exception("[background] embedding job failed conv=%s", conversation_id)


async def run_consolidation_job(conversation_id: str) -> None:
    """Stub: merge low-importance memory items and prune redundant entries.

    In a full implementation this runs the memory engine's consolidation
    pass over the entire conversation history to detect new contradictions
    or merge duplicates that weren't caught at write time.
    """
    try:
        logger.debug("[background] consolidation job skipped (stub) conv=%s", conversation_id)
        await asyncio.sleep(0)
    except Exception:
        logger.exception("[background] consolidation job failed conv=%s", conversation_id)


async def run_repair_job(conversation_id: str) -> None:
    """Stub: rebuild compact memory from raw archive if corruption detected.

    The raw archive is authoritative; compact memory is derived and
    repairable. This job re-derives memory from scratch when needed.
    """
    try:
        logger.debug("[background] repair job skipped (stub) conv=%s", conversation_id)
        await asyncio.sleep(0)
    except Exception:
        logger.exception("[background] repair job failed conv=%s", conversation_id)


async def _run_retention_async(retention_days: int) -> None:
    """Async wrapper: run retention cleanup without blocking the event loop."""
    try:
        from app.storage.cleanup import run_retention_cleanup

        await asyncio.get_event_loop().run_in_executor(
            None, run_retention_cleanup, None, retention_days
        )
    except Exception:
        logger.exception("[background] retention cleanup failed")


async def _daily_retention_loop(retention_days: int) -> None:
    """Run retention cleanup once immediately, then every 24 hours."""
    while True:
        await _run_retention_async(retention_days)
        await asyncio.sleep(86_400)  # 24 hours


def start_retention_scheduler(retention_days: int) -> None:
    """Schedule the daily retention cleanup task.

    Call once from app lifespan after the database is ready.
    No-op when retention_days == 0 (keep-forever mode).
    """
    global _retention_task
    if retention_days <= 0:
        logger.debug("[background] retention disabled (retention_days=0)")
        return
    try:
        loop = asyncio.get_event_loop()
        _retention_task = loop.create_task(_daily_retention_loop(retention_days))
        logger.info("[background] retention scheduler started (retention_days=%d)", retention_days)
    except RuntimeError:
        logger.debug("[background] no event loop; skipping retention scheduler")


def stop_retention_scheduler() -> None:
    """Cancel the daily retention task on shutdown."""
    global _retention_task
    if _retention_task is not None and not _retention_task.done():
        _retention_task.cancel()
        logger.debug("[background] retention scheduler stopped")
    _retention_task = None


def schedule_background_jobs(conversation_id: str) -> None:
    """Schedule all background jobs as asyncio tasks (non-blocking).

    Call this after archiving a request. It is safe to call in a sync
    context — it will schedule tasks on the running event loop.
    """
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(run_embedding_job(conversation_id))
        loop.create_task(run_consolidation_job(conversation_id))
    except RuntimeError:
        # No running event loop (e.g. in tests) — skip silently.
        logger.debug(
            "[background] no event loop; skipping job scheduling for conv=%s",
            conversation_id,
        )

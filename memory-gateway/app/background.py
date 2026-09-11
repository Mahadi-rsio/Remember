"""Background job hooks for embeddings, consolidation, and repair.

All jobs are fire-and-forget coroutines. They must:
- Never raise out (fail-open).
- Never block the main forwarding hot path.
- Be idempotent (safe to run multiple times).

Phase 6 implementation: stubs wired to asyncio hooks. Actual logic
(embedding generation, consolidation) is a future extension.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


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

"""Memory compressor: tool output compaction and Memory AI item transformation."""

from __future__ import annotations

import logging
from typing import Sequence

from app.memory.extractor import topic_key_from_content
from app.memory.ids import NormalizedMessage
from app.memory.scorer import score_candidate
from app.models.memory import CandidateMemory, MemoryAIOutput, MemoryScores, MemoryType
from app.providers.memory_ai import MemoryAIAdapter

logger = logging.getLogger(__name__)


def memory_ai_output_to_candidates(
    output: MemoryAIOutput,
    source_message_ids: Sequence[str],
) -> list[CandidateMemory]:
    """Convert structured MemoryAIOutput into scored CandidateMemory items."""
    candidates: list[CandidateMemory] = []

    type_mapping: list[tuple[Sequence[str], MemoryType]] = [
        (output.facts, MemoryType.FACT),
        (output.decisions, MemoryType.DECISION),
        (output.constraints, MemoryType.CONSTRAINT),
        (output.preferences, MemoryType.PREFERENCE),
        (output.goals, MemoryType.GOAL),
        (output.architecture, MemoryType.ARCHITECTURE),
        (output.important_events, MemoryType.IMPORTANT_EVENT),
        (output.active_tasks, MemoryType.ACTIVE_TASK),
    ]

    source_ids = list(source_message_ids)

    for items, mtype in type_mapping:
        for text in items:
            cleaned = text.strip()
            if not cleaned:
                continue
            topic = topic_key_from_content(cleaned, mtype)
            candidate = CandidateMemory(
                content=cleaned,
                type=mtype,
                source_message_ids=source_ids,
                topic_key=topic,
                authority="user",  # High authority since Memory AI extracted confirmed items
                is_correction=False,
            )
            scores = score_candidate(candidate)
            # Memory AI reported confidence scales the baseline confidence
            scores.confidence = min(1.0, max(0.0, output.confidence * max(0.85, scores.confidence)))
            scores.information_gain = max(0.5, scores.information_gain)
            candidate.scores = scores
            candidates.append(candidate)

    return candidates


async def compress_tool_message(
    message: NormalizedMessage,
    adapter: MemoryAIAdapter | None = None,
) -> str:
    """
    Compress a tool output message using Memory AI (if available).

    The raw output is always preserved in the raw archive; this compressed summary
    is used when compiling compact context.
    """
    if message.role != "tool":
        return message.content

    tool_name = (
        message.raw.get("name")
        or message.raw.get("tool_name")
        or message.raw.get("tool_call_id")
        or "tool"
    )

    if adapter is None:
        # Fallback without Memory AI: return content unchanged
        return message.content

    try:
        return await adapter.compress_tool_output(tool_name=str(tool_name), output_text=message.content)
    except Exception as exc:
        logger.warning("Failed to compress tool message: %s; keeping raw", exc)
        return message.content

"""Context assembler: combines system instructions, canonical memory, recent context, tool results, and new message."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

from app.context.selector import SelectableItem
from app.storage.models import MemoryItem


def format_canonical_memory_block(items: Sequence[MemoryItem]) -> str:
    """Format selected canonical memory items into a compact structured block."""
    if not items:
        return ""

    grouped: dict[str, list[str]] = defaultdict(list)
    for item in items:
        mtype = (item.type or "fact").replace("_", " ").title()
        grouped[mtype].append(item.content)

    lines = ["[Project Memory & Canonical State]"]
    for category, entries in sorted(grouped.items()):
        lines.append(f"• {category}:")
        for entry in entries:
            lines.append(f"  - {entry}")

    return "\n".join(lines)


def assemble_context_messages(
    selected_items: Sequence[SelectableItem],
    *,
    has_canonical_memory: bool = False,
) -> list[dict[str, Any]]:
    """
    Assemble the final message list for upstream AI in correct sequence.

    Order:
    1. System instructions (incorporating Canonical Memory if present)
    2. Selected conversation turns & tool results in chronological sequence
    3. New user message
    """
    system_items = [item for item in selected_items if item.kind == "system"]
    canonical_items = [
        item.memory_item
        for item in selected_items
        if item.kind == "canonical_memory" and item.memory_item is not None
    ]
    conversation_items = [
        item for item in selected_items if item.kind in ("message", "tool_result")
    ]
    new_message_items = [item for item in selected_items if item.kind == "new_message"]

    memory_text = format_canonical_memory_block(canonical_items) if canonical_items else ""

    assembled: list[dict[str, Any]] = []

    # 1. System instructions
    if system_items:
        # If there's an existing system message, inject canonical memory block
        for s in system_items:
            base_msg = dict(s.raw_message or {"role": "system", "content": s.content})
            if memory_text:
                existing_content = str(base_msg.get("content") or "")
                combined_content = f"{existing_content}\n\n{memory_text}".strip()
                base_msg["content"] = combined_content
                # Only inject once into the first system message
                memory_text = ""
            assembled.append(base_msg)
    elif memory_text:
        # No system message existed, synthesize one for canonical memory
        assembled.append({"role": "system", "content": memory_text})

    # 2. Selected chronological conversation turns & tool results
    conversation_items_sorted = sorted(conversation_items, key=lambda x: x.ordinal)
    for item in conversation_items_sorted:
        if item.raw_message is not None:
            assembled.append(dict(item.raw_message))
        else:
            assembled.append({"role": "user", "content": item.content})

    # 3. New user message (always at the end)
    for item in new_message_items:
        if item.raw_message is not None:
            assembled.append(dict(item.raw_message))
        else:
            assembled.append({"role": "user", "content": item.content})

    return assembled

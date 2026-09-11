"""Token estimation utilities for context budget calculation."""

from __future__ import annotations

import re
from typing import Any

# Heuristic pattern matching word tokens, punctuation sequences, and numbers
_WORD_OR_PUNCT_RE = re.compile(r"\w+|[^\w\s]+", re.UNICODE)


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for a text string.

    Heuristic approximation:
    - Splits on whitespace/words/punctuation
    - Takes max of word-like token split and char_len / 3.8
    - Guarantees non-negative integer
    """
    if not text:
        return 0
    clean = text.strip()
    if not clean:
        return 0

    tokens_by_regex = len(_WORD_OR_PUNCT_RE.findall(clean))
    tokens_by_chars = max(1, int(len(clean) / 3.8 + 0.5))

    # Real BPE tokenizers usually produce a count between regex tokens and char count / 3.8
    return max(1, max(tokens_by_regex, tokens_by_chars))


def estimate_message_tokens(message: dict[str, Any]) -> int:
    """
    Estimate tokens for a single OpenAI-format message dictionary.

    Includes role metadata overhead (~3 tokens per message in OpenAI format).
    """
    overhead = 3
    content = message.get("content")
    tokens = overhead

    if isinstance(content, str):
        tokens += estimate_tokens(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                tokens += estimate_tokens(part)
            elif isinstance(part, dict):
                text = part.get("text", "")
                if text:
                    tokens += estimate_tokens(str(text))

    # Name and tool metadata
    name = message.get("name")
    if name:
        tokens += estimate_tokens(str(name)) + 1

    tool_call_id = message.get("tool_call_id")
    if tool_call_id:
        tokens += estimate_tokens(str(tool_call_id)) + 1

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if isinstance(tc, dict):
                fn = tc.get("function", {})
                tokens += estimate_tokens(str(fn.get("name", "")))
                tokens += estimate_tokens(str(fn.get("arguments", "")))
                tokens += 3

    return tokens


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """
    Estimate total tokens for a list of messages, plus priming tokens (~3 tokens).
    """
    if not messages:
        return 0
    return sum(estimate_message_tokens(m) for m in messages) + 3

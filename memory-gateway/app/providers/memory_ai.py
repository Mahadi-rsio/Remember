"""Memory AI adapter (pluggable cheap model for extraction and compression)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.models.memory import MemoryAIOutput, ToolSummaryOutput

logger = logging.getLogger(__name__)

# Pattern to extract JSON payload even if wrapped in markdown code blocks
_JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*(?P<json>\{.*\}|\[.*\])\s*```",
    re.DOTALL,
)

EXTRACTION_SYSTEM_PROMPT = """You are an AI Memory Compressor. Your role is ONLY to extract and compress memory items from conversation messages.
You NEVER answer the user directly.

Output strictly valid JSON conforming to this schema:
{
  "summary": "Brief 1-2 sentence overview of what changed or happened",
  "facts": ["Stable facts about project/user/environment"],
  "decisions": ["Confirmed choices and decisions"],
  "constraints": ["Rules, restrictions, and negative requirements"],
  "preferences": ["User preferences and stylistic choices"],
  "goals": ["Active objectives and desired outcomes"],
  "architecture": ["System design and technical stack details"],
  "important_events": ["Key milestones, releases, or deployments"],
  "active_tasks": ["Pending or in-progress todos and tasks"],
  "obsolete_items": ["Previous facts/decisions that are now obsolete"],
  "contradictions": ["Previous items contradicted or superseded by new input"],
  "confidence": 0.95
}

Rules:
1. Extract only high-value information.
2. User statements and explicit decisions have highest authority.
3. Assistant speculation must NOT be recorded as confirmed facts/decisions.
4. Output ONLY valid JSON. No commentary outside the JSON.
"""

TOOL_COMPRESSION_SYSTEM_PROMPT = """You are a Tool Output Compressor. Your role is to summarize tool/command execution output.
Keep crucial exit statuses, error codes, file paths, IDs, and core outputs.
Remove repetitive logs, progress bars, and boilerplate.

Output strictly valid JSON:
{
  "summary": "Concise 1-3 sentence summary of the execution outcome",
  "key_points": ["Specific result item, path, or error"],
  "status": "success | error | warning"
}
"""


def extract_json_text(text: str) -> str:
    """Extract raw JSON substring from model output, handling code fences."""
    trimmed = text.strip()
    match = _JSON_BLOCK_RE.search(trimmed)
    if match:
        return match.group("json").strip()
    first_brace = trimmed.find("{")
    last_brace = trimmed.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return trimmed[first_brace : last_brace + 1]
    return trimmed


class MemoryAIAdapter:
    """
    Adapter for invoking a cheap Memory AI model.

    Designed with failure isolation: failures never raise out to break the hot path;
    instead they log and return None / fallback.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        retry_once: bool = True,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._retry_once = retry_once
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    def _auth_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _post_chat(self, messages: list[dict[str, str]]) -> str:
        url = "/chat/completions"
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.0,
        }
        response = await self._client.post(
            url,
            json=payload,
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("No completion choices returned by Memory AI")
        content = choices[0].get("message", {}).get("content", "")
        return str(content)

    async def extract_memory(
        self,
        messages_text: str,
        current_memory_summary: str | None = None,
    ) -> MemoryAIOutput | None:
        """
        Call Memory AI to extract structured items.

        Returns MemoryAIOutput on success, or None on failure (preserving prior state).
        """
        user_prompt = f"Delta Messages to analyze:\n{messages_text}"
        if current_memory_summary:
            user_prompt = f"Current Memory State:\n{current_memory_summary}\n\n{user_prompt}"

        conversation: list[dict[str, str]] = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # First attempt
        raw_response: str | None = None
        try:
            raw_response = await self._post_chat(conversation)
            return self._parse_and_validate_memory(raw_response)
        except (ValidationError, json.JSONDecodeError, ValueError) as parse_err:
            if not self._retry_once:
                logger.warning("Memory AI output parsing failed: %s; keeping prior memory", parse_err)
                return None

            logger.info("Memory AI output parse failed (%s); retrying once with schema reminder", parse_err)
            # Retry once
            try:
                retry_conv = list(conversation)
                if raw_response:
                    retry_conv.append({"role": "assistant", "content": raw_response})
                retry_conv.append({
                    "role": "user",
                    "content": (
                        f"Previous output was not valid JSON matching the schema: {parse_err}. "
                        "Please output ONLY the valid JSON object without any additional text."
                    ),
                })
                retry_raw = await self._post_chat(retry_conv)
                return self._parse_and_validate_memory(retry_raw)
            except Exception as retry_err:
                logger.warning(
                    "Memory AI retry also failed: %s; keeping prior memory unchanged",
                    retry_err,
                )
                return None
        except Exception as exc:
            logger.warning("Memory AI request failed: %s; keeping prior memory unchanged", exc)
            return None

    def _parse_and_validate_memory(self, raw_text: str) -> MemoryAIOutput:
        clean = extract_json_text(raw_text)
        return MemoryAIOutput.model_validate_json(clean)

    async def compress_tool_output(
        self,
        tool_name: str,
        output_text: str,
        max_chars_threshold: int = 300,
    ) -> str:
        """
        Compress tool output into a concise summary.

        If output is already short or Memory AI fails, returns safe fallback.
        """
        if len(output_text) <= max_chars_threshold:
            return output_text

        prompt = f"Tool Name: {tool_name}\nRaw Output:\n{output_text}"
        conv = [
            {"role": "system", "content": TOOL_COMPRESSION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = await self._post_chat(conv)
            clean = extract_json_text(raw)
            validated = ToolSummaryOutput.model_validate_json(clean)
            return f"[Tool: {tool_name} | {validated.status}] {validated.summary}"
        except Exception as exc:
            logger.warning("Tool compression failed (%s); falling back to truncated output", exc)
            return f"[Tool: {tool_name}] {output_text[:max_chars_threshold]}... (truncated)"

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def create_memory_ai_adapter(settings: Settings | None = None) -> MemoryAIAdapter | None:
    """Create MemoryAIAdapter if MEMORY_AI_ENABLED is True, otherwise return None."""
    cfg = settings or get_settings()
    if not cfg.memory_ai_enabled:
        return None
    return MemoryAIAdapter(
        base_url=cfg.memory_ai_base_url,
        api_key=cfg.memory_ai_api_key,
        model=cfg.memory_ai_model,
        timeout=cfg.memory_ai_timeout,
        retry_once=cfg.memory_ai_retry_once,
    )

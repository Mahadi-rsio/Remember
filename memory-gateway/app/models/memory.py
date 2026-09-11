"""Canonical memory schema: types, statuses, scores, and candidates."""

from __future__ import annotations

from enum import Enum
from typing import Sequence

from pydantic import BaseModel, Field, field_validator

from app.memory.correction import Correction
from app.memory.revocation import Revocation


class MemoryType(str, Enum):
    FACT = "fact"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    PREFERENCE = "preference"
    GOAL = "goal"
    ARCHITECTURE = "architecture"
    IMPORTANT_EVENT = "important_event"
    ACTIVE_TASK = "active_task"


CANONICAL_TYPES: tuple[MemoryType, ...] = tuple(MemoryType)


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"
    EXPIRED = "expired"
    OBSOLETE = "obsolete"


class MemoryScores(BaseModel):
    """Separate score axes — never collapse into one metric."""

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.0, ge=0.0, le=1.0)
    stability: float = Field(default=0.0, ge=0.0, le=1.0)
    freshness: float = Field(default=1.0, ge=0.0, le=1.0)
    information_gain: float = Field(default=0.0, ge=0.0, le=1.0)


class StructuredFact(BaseModel):
    """Structured representation (entity, attribute, value) of an extracted fact."""

    entity: str
    attribute: str
    value: str
    memory_type: MemoryType = MemoryType.FACT
    raw_text: str = ""

    def to_content(self) -> str:
        if self.memory_type == MemoryType.PREFERENCE:
            return self.value
        if self.attribute == "project" and self.entity == self.value:
            return f"Project = {self.value}"
        if self.entity and self.entity.lower() not in ("user", self.attribute.lower()):
            return f"{self.entity} {self.attribute} = {self.value}"
        attr_title = self.attribute[0].upper() + self.attribute[1:] if self.attribute else "Item"
        return f"{attr_title} = {self.value}"

    def to_topic_key(self) -> str:
        from app.memory.facts import detect_preference_domain, slugify

        if self.memory_type == MemoryType.PREFERENCE:
            _, topic = detect_preference_domain(self.value)
            return topic
        if self.attribute == "project":
            return "project"
        if self.entity and self.entity.lower() not in ("user", self.attribute.lower()):
            return f"{slugify(self.entity)}_{slugify(self.attribute)}"
        return slugify(self.attribute)


class CandidateMemory(BaseModel):
    """In-memory candidate before persistence / merge."""

    content: str
    type: MemoryType
    scores: MemoryScores = Field(default_factory=MemoryScores)
    source_message_ids: list[str] = Field(default_factory=list)
    topic_key: str = ""
    authority: str = "user"  # user | assistant | speculation
    is_correction: bool = False
    structured_fact: StructuredFact | None = None
    correction: "Correction | None" = None
    revocation: "Revocation | None" = None

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("content must be non-empty")
        return text


class CanonicalMemorySnapshot(BaseModel):
    """Grouped active memory for versioned context state."""

    facts: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    architecture: list[str] = Field(default_factory=list)
    important_events: list[str] = Field(default_factory=list)
    active_tasks: list[str] = Field(default_factory=list)

    @classmethod
    def from_items(cls, items: Sequence[object]) -> CanonicalMemorySnapshot:
        field_for = {
            MemoryType.FACT: "facts",
            MemoryType.DECISION: "decisions",
            MemoryType.CONSTRAINT: "constraints",
            MemoryType.PREFERENCE: "preferences",
            MemoryType.GOAL: "goals",
            MemoryType.ARCHITECTURE: "architecture",
            MemoryType.IMPORTANT_EVENT: "important_events",
            MemoryType.ACTIVE_TASK: "active_tasks",
        }
        data: dict[str, list[str]] = {name: [] for name in field_for.values()}
        for item in items:
            type_raw = getattr(item, "type", None)
            content = getattr(item, "content", None)
            if not isinstance(content, str) or not content:
                continue
            try:
                mtype = MemoryType(type_raw) if not isinstance(type_raw, MemoryType) else type_raw
            except ValueError:
                continue
            data[field_for[mtype]].append(content)
        return cls(**data)


class MemoryAIOutput(BaseModel):
    """Structured JSON contract expected from Memory AI compressor."""

    summary: str = ""
    facts: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    architecture: list[str] = Field(default_factory=list)
    important_events: list[str] = Field(default_factory=list)
    active_tasks: list[str] = Field(default_factory=list)
    obsolete_items: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


class ToolSummaryOutput(BaseModel):
    """Structured JSON contract for tool output compression."""

    summary: str
    key_points: list[str] = Field(default_factory=list)
    status: str = "success"

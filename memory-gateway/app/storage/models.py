"""SQLModel tables for conversations, raw archive, memory, and context versions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: str = Field(primary_key=True, max_length=128)
    user_key: Optional[str] = Field(default=None, index=True, max_length=128)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    metadata_json: Optional[str] = Field(default=None, sa_column=Column(Text))


class Message(SQLModel, table=True):
    """Raw archive entry — authoritative transcript; never destroyed."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "message_key", name="uq_conv_message_key"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id", index=True, max_length=128)
    message_key: str = Field(index=True, max_length=128)
    role: str = Field(max_length=32)
    content: str = Field(sa_column=Column(Text, nullable=False))
    content_hash: str = Field(max_length=64)
    ordinal: int = Field(default=0)
    client_message_id: Optional[str] = Field(default=None, max_length=128)
    metadata_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utcnow)


class MemoryItem(SQLModel, table=True):
    """Canonical compact memory item with separate score axes."""

    __tablename__ = "memory_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id", index=True, max_length=128)
    content: str = Field(sa_column=Column(Text, nullable=False))
    type: str = Field(max_length=64, index=True)
    topic_key: str = Field(default="", max_length=128, index=True)
    confidence: float = Field(default=0.0)
    importance: float = Field(default=0.0)
    stability: float = Field(default=0.0)
    freshness: float = Field(default=0.0)
    information_gain: float = Field(default=0.0)
    source_message_ids_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    status: str = Field(default="active", max_length=32, index=True)
    version: int = Field(default=1)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ContextVersion(SQLModel, table=True):
    """Versioned context snapshot metadata (populated by later phases)."""

    __tablename__ = "context_versions"
    __table_args__ = (
        UniqueConstraint("conversation_id", "version", name="uq_conv_context_version"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id", index=True, max_length=128)
    version: int = Field(default=1)
    state_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    source_message_ids_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=utcnow)


# Re-export for typing convenience
AnyTable = Any

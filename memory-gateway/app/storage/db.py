"""SQLite engine, session factory, and schema bootstrap."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.storage import models as _models  # noqa: F401 — register tables

_engine = None


def _sqlite_url(path: str) -> str:
    resolved = Path(path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{resolved}"


_FTS_DDL = [
    # ── FTS5 virtual tables ────────────────────────────────────────────────
    """CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
        content, role, conversation_id UNINDEXED,
        content=messages, content_rowid=id
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts USING fts5(
        content, type, topic_key, conversation_id UNINDEXED,
        content=memory_items, content_rowid=id
    )""",
    # ── messages triggers ──────────────────────────────────────────────────
    """CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
        INSERT INTO messages_fts(rowid, content, role, conversation_id)
        VALUES (new.id, new.content, new.role, new.conversation_id);
    END""",
    """CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content, role, conversation_id)
        VALUES ('delete', old.id, old.content, old.role, old.conversation_id);
    END""",
    """CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content, role, conversation_id)
        VALUES ('delete', old.id, old.content, old.role, old.conversation_id);
        INSERT INTO messages_fts(rowid, content, role, conversation_id)
        VALUES (new.id, new.content, new.role, new.conversation_id);
    END""",
    # ── memory_items triggers ──────────────────────────────────────────────
    """CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items BEGIN
        INSERT INTO memory_items_fts(rowid, content, type, topic_key, conversation_id)
        VALUES (new.id, new.content, new.type, new.topic_key, new.conversation_id);
    END""",
    """CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items BEGIN
        INSERT INTO memory_items_fts(memory_items_fts, rowid, content, type, topic_key, conversation_id)
        VALUES ('delete', old.id, old.content, old.type, old.topic_key, old.conversation_id);
    END""",
    """CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items BEGIN
        INSERT INTO memory_items_fts(memory_items_fts, rowid, content, type, topic_key, conversation_id)
        VALUES ('delete', old.id, old.content, old.type, old.topic_key, old.conversation_id);
        INSERT INTO memory_items_fts(rowid, content, type, topic_key, conversation_id)
        VALUES (new.id, new.content, new.type, new.topic_key, new.conversation_id);
    END""",
]


def _init_fts(engine) -> None:
    """Create FTS5 virtual tables and sync triggers (idempotent)."""
    with engine.connect() as conn:
        for ddl in _FTS_DDL:
            conn.execute(text(ddl))
        conn.commit()


def init_db(sqlite_path: str) -> None:
    """Create engine (if needed) and ensure all tables and FTS indexes exist."""
    global _engine
    url = _sqlite_url(sqlite_path)
    if _engine is None or str(_engine.url) != url:
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    SQLModel.metadata.create_all(_engine)
    _init_fts(_engine)


def get_engine():
    if _engine is None:
        raise RuntimeError("database not initialized; call init_db() first")
    return _engine


def reset_engine() -> None:
    """Dispose engine — used by tests to switch SQLite paths."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


@contextmanager
def session_scope() -> Iterator[Session]:
    engine = get_engine()
    with Session(engine, expire_on_commit=False) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

"""SQLite engine, session factory, and schema bootstrap."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.storage import models as _models  # noqa: F401 — register tables

_engine = None


def _sqlite_url(path: str) -> str:
    resolved = Path(path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{resolved}"


def init_db(sqlite_path: str) -> None:
    """Create engine (if needed) and ensure all tables exist."""
    global _engine
    url = _sqlite_url(sqlite_path)
    if _engine is None or str(_engine.url) != url:
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    SQLModel.metadata.create_all(_engine)


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
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

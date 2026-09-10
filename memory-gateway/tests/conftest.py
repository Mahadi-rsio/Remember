"""Shared fixtures: isolated SQLite per test session app."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.storage.db import init_db, reset_engine


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_file))
    get_settings.cache_clear()
    reset_engine()
    init_db(str(db_file))
    yield db_file
    reset_engine()
    get_settings.cache_clear()

"""Phase 0: health endpoint smoke tests."""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.storage.db import reset_engine


def test_health_returns_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "health.db"))
    get_settings.cache_clear()
    reset_engine()
    try:
        with TestClient(create_app()) as client:
            response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["service"] == "memory-gateway"
        assert body["sqlite_ready"] is True
        assert body["schema_ready"] is True
        assert "context_budget" in body
    finally:
        reset_engine()
        get_settings.cache_clear()

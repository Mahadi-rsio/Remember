"""Phase 0: health endpoint smoke tests."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert body["service"] == "memory-gateway"
    assert "sqlite_ready" in body
    assert "context_budget" in body

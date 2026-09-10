"""Liveness / readiness endpoints (gateway-local, not proxied)."""

from pathlib import Path

from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    db_path = Path(settings.sqlite_path).expanduser()
    db_parent = db_path.resolve().parent if db_path.parent.exists() else db_path.parent
    sqlite_ok = db_parent.exists() and db_parent.is_dir()
    schema_ok = False
    try:
        from app.storage.db import get_engine

        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        schema_ok = True
        sqlite_ok = True
    except Exception:
        schema_ok = False

    ready = sqlite_ok and schema_ok
    return {
        "status": "ok" if ready else "degraded",
        "service": settings.app_name,
        "sqlite_path": settings.sqlite_path,
        "sqlite_ready": sqlite_ok,
        "schema_ready": schema_ok,
        "memory_ai_enabled": settings.memory_ai_enabled,
        "context_budget": settings.context_budget,
    }

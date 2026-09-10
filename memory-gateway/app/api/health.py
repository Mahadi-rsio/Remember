"""Liveness / readiness endpoints (gateway-local, not proxied)."""

from pathlib import Path

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    db_parent = Path(settings.sqlite_path).expanduser().resolve().parent
    sqlite_ok = db_parent.exists() and db_parent.is_dir()
    return {
        "status": "ok" if sqlite_ok else "degraded",
        "service": settings.app_name,
        "sqlite_path": settings.sqlite_path,
        "sqlite_ready": sqlite_ok,
        "memory_ai_enabled": settings.memory_ai_enabled,
        "context_budget": settings.context_budget,
    }

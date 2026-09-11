"""FastAPI entrypoint for the AI Memory Gateway."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.proxy import router as proxy_router
from app.background import start_retention_scheduler, stop_retention_scheduler
from app.cache.redis_adapter import create_cache_backend
from app.config import get_settings
from app.logging_setup import setup_logging
from app.providers import create_memory_ai_adapter, create_upstream_provider
from app.storage.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db_path = Path(settings.sqlite_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(str(db_path))

    provider = create_upstream_provider(settings)
    app.state.upstream_provider = provider
    memory_ai = create_memory_ai_adapter(settings)
    app.state.memory_ai_adapter = memory_ai

    cache = create_cache_backend(settings.redis_url)
    app.state.cache = cache

    # Phase 7: start retention cleanup scheduler (no-op if retention_days=0)
    start_retention_scheduler(settings.retention_days)

    try:
        yield
    finally:
        stop_retention_scheduler()
        if memory_ai is not None:
            await memory_ai.aclose()
        await provider.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings)
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(proxy_router)
    return app


app = create_app()

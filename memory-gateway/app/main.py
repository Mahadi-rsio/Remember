"""FastAPI entrypoint for the AI Memory Gateway."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.proxy import router as proxy_router
from app.config import get_settings
from app.providers import create_upstream_provider
from app.storage.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db_path = Path(settings.sqlite_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(str(db_path))

    provider = create_upstream_provider(settings)
    app.state.upstream_provider = provider
    try:
        yield
    finally:
        await provider.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(proxy_router)
    return app


app = create_app()

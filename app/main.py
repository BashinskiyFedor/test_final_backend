from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (register models on Base.metadata)
from app.api.errors import register_exception_handlers
from app.api.router import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.services.keitaro import build_keitaro_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Для простоты таблицы создаются на старте; для продакшена лучше Alembic.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.state.keitaro = build_keitaro_client()
    yield
    await app.state.keitaro.aclose()
    await engine.dispose()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)
app.include_router(api_router, prefix="/api")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}

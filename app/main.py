from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
import app.models  # noqa: F401  (register models on Base.metadata)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Для простоты таблицы создаются на старте; для продакшена лучше Alembic.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.include_router(api_router, prefix="/api")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}

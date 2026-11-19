from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError
from app.models import Stream


async def load_streams(session: AsyncSession, campaign_id: int) -> list[Stream]:
    result = await session.scalars(
        select(Stream)
        .where(Stream.campaign_id == campaign_id)
        .options(selectinload(Stream.offers))
        .order_by(Stream.position, Stream.id)
    )
    return list(result.all())


async def get_stream(session: AsyncSession, stream_id: int) -> Stream:
    stream = await session.scalar(
        select(Stream).where(Stream.id == stream_id).options(selectinload(Stream.offers))
    )
    if stream is None:
        raise NotFoundError("Поток не найден")
    return stream

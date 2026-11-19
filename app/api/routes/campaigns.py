import asyncio
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Campaign
from app.models.campaign import STATUS_CREATED
from app.schemas.campaign import CampaignCreate, CampaignRead, CampaignStored, OfferRead
from app.services.keitaro import (
    KeitaroClient,
    KeitaroError,
    ensure_campaign_with_stream,
    get_keitaro,
    make_alias,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
offers_router = APIRouter(prefix="/offers", tags=["offers"])

KeitaroDep = Annotated[KeitaroClient, Depends(get_keitaro)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Одновременные запросы с одним alias обрабатываются по очереди (в пределах процесса).
_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


@offers_router.get("", response_model=list[OfferRead])
async def list_offers(keitaro: KeitaroDep):
    """Офферы из Keitaro (без удалённых) для выпадающего списка."""
    try:
        offers = await keitaro.list_offers()
    except KeitaroError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
    return [
        OfferRead(id=o["id"], name=o["name"])
        for o in offers
        if o.get("state") != "deleted"
    ]


@router.get("", response_model=list[CampaignStored])
async def list_campaigns(session: SessionDep, skip: int = 0, limit: int = 100):
    result = await session.scalars(
        select(Campaign)
        .where(Campaign.status == STATUS_CREATED)
        .order_by(Campaign.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.all()


def _read(record: Campaign, already_exists: bool) -> CampaignRead:
    assert record.keitaro_campaign_id is not None and record.keitaro_stream_id is not None
    return CampaignRead(
        campaign_id=record.keitaro_campaign_id,
        stream_id=record.keitaro_stream_id,
        name=record.name,
        alias=record.alias,
        country=record.country,
        offer_id=record.offer_id,
        already_exists=already_exists,
    )


@router.post("", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    data: CampaignCreate, keitaro: KeitaroDep, session: SessionDep, response: Response
):
    """Идемпотентно создаёт кампанию в Keitaro (+ flow с гео и оффером) и запись в БД.

    Повтор того же запроса (имя + гео + оффер) не создаёт дубль ни в Keitaro, ни у нас:
    возвращается уже существующая кампания. Если прошлая попытка оборвалась между Keitaro
    и БД, запись достраивается по alias.
    """
    alias = make_alias(data.name, data.country, data.offer_id)

    async with _locks[alias]:
        record = await session.scalar(select(Campaign).where(Campaign.alias == alias))
        if record is not None and record.status == STATUS_CREATED:
            response.status_code = status.HTTP_200_OK
            return _read(record, already_exists=True)

        inserted = False
        if record is None:
            # Сначала резервируем строку — фиксируем намерение до обращения к Keitaro.
            record = Campaign(
                alias=alias, name=data.name, country=data.country, offer_id=data.offer_id
            )
            session.add(record)
            try:
                await session.commit()
                inserted = True
            except IntegrityError:  # параллельный запрос в другом процессе
                await session.rollback()
                record = await session.scalar(select(Campaign).where(Campaign.alias == alias))
                if record is None:
                    raise HTTPException(status.HTTP_409_CONFLICT, "Повторите запрос")
                if record.status == STATUS_CREATED:
                    response.status_code = status.HTTP_200_OK
                    return _read(record, already_exists=True)

        try:
            if not any(o["id"] == data.offer_id for o in await keitaro.list_offers()):
                raise KeitaroError(f"Оффер #{data.offer_id} не найден в Keitaro", 422)
            campaign, stream = await ensure_campaign_with_stream(
                keitaro, data.name, alias, data.country, data.offer_id
            )
        except KeitaroError as exc:
            if inserted:  # в Keitaro ничего не осталось — снимаем резерв
                await session.delete(record)
                await session.commit()
            raise HTTPException(exc.status_code, exc.message) from exc

        record.keitaro_campaign_id = campaign["id"]
        record.keitaro_stream_id = stream["id"]
        record.status = STATUS_CREATED
        await session.commit()
        return _read(record, already_exists=False)

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.campaign import CampaignCreate, CampaignRead, CampaignStored, OfferRead
from app.services import campaign_service
from app.services.keitaro import KeitaroClient, get_keitaro
from app.services.offers import search_offers

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
offers_router = APIRouter(prefix="/offers", tags=["offers"])

KeitaroDep = Annotated[KeitaroClient, Depends(get_keitaro)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@offers_router.get("", response_model=list[OfferRead])
async def list_offers(
    keitaro: KeitaroDep, q: str | None = None, limit: int = 50, refresh: bool = False
):
    """Офферы из Keitaro (без удалённых); ``q`` — поиск по названию или ID.

    Список кэшируется; ``refresh=true`` принудительно перечитывает его из Keitaro.
    """
    offers = await search_offers(keitaro, q, limit, refresh=refresh)
    return [OfferRead(id=o.id, name=o.name) for o in offers]


@router.get("", response_model=list[CampaignStored])
async def list_campaigns(session: SessionDep, skip: int = 0, limit: int = 100):
    return await campaign_service.list_created_campaigns(session, skip, limit)


@router.get("/{campaign_id}", response_model=CampaignStored)
async def get_campaign(campaign_id: int, session: SessionDep):
    return await campaign_service.get_created_campaign(session, campaign_id)


@router.post("", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    data: CampaignCreate, keitaro: KeitaroDep, session: SessionDep, response: Response
):
    """Создаёт кампанию в Keitaro и у нас; повтор того же запроса возвращает существующую (200)."""
    result = await campaign_service.create_campaign(session, keitaro, data)
    if result.already_exists:
        response.status_code = status.HTTP_200_OK
    return CampaignRead.from_record(result.campaign, result.already_exists)

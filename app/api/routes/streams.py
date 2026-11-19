from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.stream import OfferAdd, OfferPin, StreamRead
from app.services import campaign_service, stream_editor, stream_sync
from app.services.keitaro import KeitaroClient, get_keitaro
from app.services.stream_queries import get_stream, load_streams

router = APIRouter(tags=["editor"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
KeitaroDep = Annotated[KeitaroClient, Depends(get_keitaro)]


@router.get("/campaigns/{campaign_id}/streams", response_model=list[StreamRead])
async def list_streams(campaign_id: int, session: SessionDep):
    await campaign_service.get_created_campaign(session, campaign_id)
    return await load_streams(session, campaign_id)


@router.post("/campaigns/{campaign_id}/streams/sync", response_model=list[StreamRead])
async def sync_streams(campaign_id: int, session: SessionDep, keitaro: KeitaroDep):
    """Fetch streams: получить потоки и офферы кампании из Keitaro."""
    campaign = await campaign_service.get_created_campaign(session, campaign_id)
    return await stream_sync.sync_streams(session, keitaro, campaign)


@router.post("/streams/{stream_id}/offers", response_model=StreamRead)
async def add_offer(stream_id: int, data: OfferAdd, session: SessionDep, keitaro: KeitaroDep):
    stream = await get_stream(session, stream_id)
    await stream_editor.add_offer(session, keitaro, stream, data.offer_id)
    return stream


@router.delete("/streams/{stream_id}/offers/{offer_pk}", response_model=StreamRead)
async def remove_offer(stream_id: int, offer_pk: int, session: SessionDep):
    stream = await get_stream(session, stream_id)
    await stream_editor.remove_offer(session, stream, offer_pk)
    return stream


@router.post("/streams/{stream_id}/offers/{offer_pk}/restore", response_model=StreamRead)
async def restore_offer(stream_id: int, offer_pk: int, session: SessionDep):
    stream = await get_stream(session, stream_id)
    await stream_editor.restore_offer(session, stream, offer_pk)
    return stream


@router.patch("/streams/{stream_id}/offers/{offer_pk}", response_model=StreamRead)
async def pin_offer(stream_id: int, offer_pk: int, data: OfferPin, session: SessionDep):
    stream = await get_stream(session, stream_id)
    await stream_editor.set_pinned(session, stream, offer_pk, data.pinned)
    return stream


@router.post("/streams/{stream_id}/cancel", response_model=StreamRead)
async def cancel(stream_id: int, session: SessionDep):
    stream = await get_stream(session, stream_id)
    await stream_editor.cancel_changes(session, stream)
    return stream


@router.post("/streams/{stream_id}/push", response_model=StreamRead)
async def push(stream_id: int, session: SessionDep, keitaro: KeitaroDep):
    stream = await get_stream(session, stream_id)
    await stream_editor.push_stream(session, keitaro, stream)
    return stream

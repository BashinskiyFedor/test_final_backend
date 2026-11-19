"""«Fetch streams»: подтягивает потоки и офферы из Keitaro, не затирая наши черновики."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Campaign, Stream, StreamOffer
from app.services.keitaro import KeitaroClient
from app.services.keitaro_models import RemoteStream, RemoteStreamOffer
from app.services.stream_queries import load_streams


async def sync_streams(
    session: AsyncSession, keitaro: KeitaroClient, campaign: Campaign
) -> list[Stream]:
    keitaro_campaign_id, _ = campaign.keitaro_ids()
    remote_streams = await keitaro.list_streams(keitaro_campaign_id)
    offer_names = {o.id: o.name for o in await keitaro.list_offers()}
    local = {s.keitaro_stream_id: s for s in await load_streams(session, campaign.id)}

    for position, remote in enumerate(remote_streams):
        stream = local.pop(remote.id, None) or _new_stream(session, campaign, remote)
        _update_stream(stream, remote, position)
        _sync_offers(stream, remote.offers, offer_names)

    for gone in local.values():  # потоков больше нет в Keitaro
        await session.delete(gone)

    await session.commit()
    return await load_streams(session, campaign.id)


def _new_stream(session: AsyncSession, campaign: Campaign, remote: RemoteStream) -> Stream:
    stream = Stream(campaign_id=campaign.id, keitaro_stream_id=remote.id, name="")
    stream.offers = []
    session.add(stream)
    return stream


def _update_stream(stream: Stream, remote: RemoteStream, position: int) -> None:
    stream.name = remote.name or f"Поток #{remote.id}"
    stream.type = remote.type
    stream.position = position


def _sync_offers(
    stream: Stream, remote_offers: list[RemoteStreamOffer], offer_names: dict[int, str]
) -> None:
    remote_by_id: dict[int, RemoteStreamOffer] = {}
    for remote in remote_offers:
        remote_by_id.setdefault(remote.offer_id, remote)

    for offer_id, remote in remote_by_id.items():
        row = stream.find_offer(offer_id)
        if row is None:
            name = offer_names.get(offer_id, f"Оффер #{offer_id}")
            stream.offers.append(StreamOffer.from_keitaro(offer_id, name, remote.share))
        else:
            row.apply_keitaro_state(remote.share, offer_names.get(offer_id, row.name))

    for row in stream.offers:
        if row.offer_id not in remote_by_id:
            row.mark_missing_in_keitaro()

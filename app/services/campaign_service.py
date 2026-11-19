"""Создание кампаний: идемпотентно, без дублей в Keitaro и с гарантированной записью у нас."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, DomainError, KeitaroError, NotFoundError
from app.core.locks import KeyedLock
from app.models import Campaign, CampaignStatus
from app.schemas.campaign import CampaignCreate
from app.services.keitaro import KeitaroClient
from app.services.keitaro_models import RemoteCampaign, RemoteStream
from app.services.naming import make_alias, stream_name
from app.services.offers import require_offer

# Одновременные запросы с одним alias обрабатываются по очереди (в пределах процесса).
_alias_locks = KeyedLock()


@dataclass(frozen=True)
class CreationResult:
    campaign: Campaign
    already_exists: bool


async def get_created_campaign(session: AsyncSession, campaign_id: int) -> Campaign:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or campaign.status != CampaignStatus.CREATED:
        raise NotFoundError("Кампания не найдена")
    return campaign


async def list_created_campaigns(session: AsyncSession, skip: int, limit: int) -> list[Campaign]:
    result = await session.scalars(
        select(Campaign)
        .where(Campaign.status == CampaignStatus.CREATED)
        .order_by(Campaign.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.all())


async def create_campaign(
    session: AsyncSession, keitaro: KeitaroClient, data: CampaignCreate
) -> CreationResult:
    """Идемпотентно создаёт кампанию в Keitaro (+ flow с гео и оффером) и запись в БД.

    Повтор того же запроса (имя + гео + оффер) не создаёт дубль ни в Keitaro, ни у нас.
    Если прошлая попытка оборвалась между Keitaro и БД, запись достраивается по alias.
    """
    alias = make_alias(data.name, data.country, data.offer_id)

    async with _alias_locks(alias):
        record = await _find_by_alias(session, alias)
        reserved_now = False
        if record is None:
            record, reserved_now = await _reserve(session, data, alias)
        if record.status == CampaignStatus.CREATED:
            return CreationResult(record, already_exists=True)

        await _provision(session, keitaro, record, release_on_failure=reserved_now)
        return CreationResult(record, already_exists=False)


async def _find_by_alias(session: AsyncSession, alias: str) -> Campaign | None:
    return await session.scalar(select(Campaign).where(Campaign.alias == alias))


async def _reserve(
    session: AsyncSession, data: CampaignCreate, alias: str
) -> tuple[Campaign, bool]:
    """Резервирует строку до обращения к Keitaro. Возвращает (запись, создана ли нами)."""
    record = Campaign(alias=alias, name=data.name, country=data.country, offer_id=data.offer_id)
    session.add(record)
    try:
        await session.commit()
    except IntegrityError:  # параллельный запрос в другом процессе успел раньше
        await session.rollback()
        existing = await _find_by_alias(session, alias)
        if existing is None:
            raise ConflictError("Повторите запрос") from None
        return existing, False
    return record, True


async def _provision(
    session: AsyncSession, keitaro: KeitaroClient, record: Campaign, *, release_on_failure: bool
) -> None:
    try:
        await require_offer(keitaro, record.offer_id)
        campaign, stream = await ensure_campaign_with_stream(
            keitaro,
            record.name,
            record.alias,
            record.country,
            record.offer_id,
            # Свежезарезервированной строке в Keitaro взяться неоткуда — полный перебор кампаний
            # (самый медленный вызов) нужен только при достройке оборванной прошлой попытки.
            look_for_existing=not release_on_failure,
        )
    except DomainError:
        if release_on_failure:  # в Keitaro ничего не осталось — снимаем резерв
            await session.delete(record)
            await session.commit()
        raise

    record.keitaro_campaign_id = campaign.id
    record.keitaro_stream_id = stream.id
    record.name = campaign.name or record.name
    record.status = CampaignStatus.CREATED
    await session.commit()


async def ensure_campaign_with_stream(
    keitaro: KeitaroClient,
    name: str,
    alias: str,
    country: str,
    offer_id: int,
    *,
    look_for_existing: bool = True,
) -> tuple[RemoteCampaign, RemoteStream]:
    """Находит или создаёт кампанию и flow в Keitaro — повторный вызов дублей не создаёт."""
    campaign = await keitaro.find_campaign_by_alias(alias) if look_for_existing else None
    if campaign is not None:
        return campaign, await _find_or_create_stream(keitaro, campaign.id, country, offer_id)

    campaign = await keitaro.create_campaign(name, alias)
    try:
        stream = await keitaro.create_stream(campaign.id, country, offer_id)
    except KeitaroError:
        await _delete_quietly(keitaro, campaign.id)  # не оставляем кампанию без flow
        raise
    return campaign, stream


async def _find_or_create_stream(
    keitaro: KeitaroClient, campaign_id: int, country: str, offer_id: int
) -> RemoteStream:
    expected = stream_name(country)
    for stream in await keitaro.list_streams(campaign_id):
        if stream.name == expected:
            return stream
    return await keitaro.create_stream(campaign_id, country, offer_id)


async def _delete_quietly(keitaro: KeitaroClient, campaign_id: int) -> None:
    try:
        await keitaro.delete_campaign(campaign_id)
    except KeitaroError:
        pass  # основная ошибка важнее; «осиротевшая» кампания подхватится по alias при повторе

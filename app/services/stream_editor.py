"""Черновики потока: добавление/удаление/пин офферов, cancel и push в Keitaro."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, InvalidInputError, NotFoundError
from app.models import Stream, StreamOffer
from app.services.keitaro import KeitaroClient
from app.services.offers import require_offer
from app.services.weights import TOTAL_WEIGHT, WeightError, recalc_weights


def _get_offer(stream: Stream, offer_pk: int) -> StreamOffer:
    for offer in stream.offers:
        if offer.id == offer_pk:
            return offer
    raise NotFoundError("Оффер в потоке не найден")


async def _commit_recalculated(session: AsyncSession, stream: Stream) -> None:
    try:
        recalc_weights(stream.offers)
    except WeightError:
        await session.rollback()
        raise
    await session.commit()


async def add_offer(
    session: AsyncSession, keitaro: KeitaroClient, stream: Stream, offer_id: int
) -> None:
    """Добавляет оффер в черновик потока (в Keitaro уйдёт при push)."""
    if not stream.has_offers:
        raise ConflictError("В этот поток нельзя добавлять офферы")

    existing = stream.find_offer(offer_id)
    if existing is not None and existing.active:
        raise ConflictError("Оффер уже есть в потоке")

    if existing is not None:  # был в архиве — просто возвращаем
        existing.activate()
    else:
        offer = await require_offer(keitaro, offer_id)
        stream.offers.append(StreamOffer.draft(offer.id, offer.name))
    await _commit_recalculated(session, stream)


async def remove_offer(session: AsyncSession, stream: Stream, offer_pk: int) -> None:
    offer = _get_offer(stream, offer_pk)
    if not offer.active:
        raise ConflictError("Оффер уже удалён")
    if offer.was_published:
        offer.deactivate()
    else:  # черновик, которого нет в Keitaro, — убираем совсем
        stream.offers.remove(offer)
    await _commit_recalculated(session, stream)


async def restore_offer(session: AsyncSession, stream: Stream, offer_pk: int) -> None:
    offer = _get_offer(stream, offer_pk)
    if offer.active:
        raise ConflictError("Оффер уже активен")
    offer.activate()
    await _commit_recalculated(session, stream)


async def set_pinned(session: AsyncSession, stream: Stream, offer_pk: int, pinned: bool) -> None:
    offer = _get_offer(stream, offer_pk)
    if not offer.active:
        raise ConflictError("Нельзя запинить удалённый оффер")
    offer.pinned = pinned
    await _commit_recalculated(session, stream)


async def cancel_changes(session: AsyncSession, stream: Stream) -> None:
    """Откатывает черновик потока к тому, что сейчас в Keitaro."""
    for offer in list(stream.offers):
        if not offer.revert_to_keitaro():
            stream.offers.remove(offer)
    await session.commit()


async def push_stream(session: AsyncSession, keitaro: KeitaroClient, stream: Stream) -> None:
    active = stream.active_offers
    if active and sum(o.share for o in active) != TOTAL_WEIGHT:
        raise InvalidInputError(f"Сумма долей активных офферов должна быть равна {TOTAL_WEIGHT}%")

    await keitaro.update_stream_offers(stream.keitaro_stream_id, {o.offer_id: o.share for o in active})
    for offer in stream.offers:
        offer.mark_pushed()
    await session.commit()

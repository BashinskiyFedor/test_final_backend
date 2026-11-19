from app.core.errors import InvalidInputError
from app.services.keitaro import KeitaroClient
from app.services.keitaro_models import RemoteOffer


async def require_offer(keitaro: KeitaroClient, offer_id: int) -> RemoteOffer:
    offer = await keitaro.get_offer(offer_id)
    if offer is None:
        raise InvalidInputError(f"Оффер #{offer_id} не найден в Keitaro")
    return offer


async def search_offers(
    keitaro: KeitaroClient, query: str | None, limit: int, *, refresh: bool = False
) -> list[RemoteOffer]:
    """Поиск по подстроке названия или по точному ID."""
    needle = (query or "").strip().casefold()
    offers = await keitaro.list_offers(refresh=refresh)
    matching = (
        o for o in offers if not needle or needle in o.name.casefold() or needle == str(o.id)
    )
    return list(matching)[:limit]

import time
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import Request

from app.core.config import settings
from app.core.errors import KeitaroError
from app.services.keitaro_models import (
    ActionType,
    CampaignType,
    EntityState,
    RemoteCampaign,
    RemoteOffer,
    RemoteStream,
    StreamSchema,
    StreamType,
)
from app.services.naming import stream_name

OFFERS_CACHE_TTL_SECONDS = 300.0
REQUEST_TIMEOUT_SECONDS = 15
CAMPAIGNS_PAGE_SIZE = 100


class KeitaroClient:
    """Тонкая обёртка над Keitaro Admin API: HTTP, типизация ответов и кэш списка офферов."""

    def __init__(self, http: httpx.AsyncClient, clock: Callable[[], float] = time.monotonic):
        self._http = http
        self._clock = clock
        self._offers: list[RemoteOffer] = []
        self._offers_loaded_at: float | None = None

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise KeitaroError(f"Keitaro недоступен: {exc}") from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text
            raise KeitaroError(f"Keitaro {resp.status_code}: {detail}")
        return resp.json() if resp.content else None

    # ---- офферы ----

    async def list_offers(self, *, refresh: bool = False) -> list[RemoteOffer]:
        """Неудалённые офферы; список кэшируется на OFFERS_CACHE_TTL_SECONDS."""
        if refresh or self._offers_expired():
            raw = await self._request("GET", "/offers") or []
            offers = (RemoteOffer.model_validate(o) for o in raw)
            self._offers = [o for o in offers if o.state != EntityState.DELETED]
            self._offers_loaded_at = self._clock()
        return self._offers

    def _offers_expired(self) -> bool:
        return (
            self._offers_loaded_at is None
            or self._clock() - self._offers_loaded_at > OFFERS_CACHE_TTL_SECONDS
        )

    async def get_offer(self, offer_id: int) -> RemoteOffer | None:
        """Оффер по ID; если в кэше нет — один раз обновляет кэш (оффер мог появиться только что)."""
        for refresh in (False, True):
            for offer in await self.list_offers(refresh=refresh):
                if offer.id == offer_id:
                    return offer
        return None

    # ---- кампании ----

    async def find_campaign_by_alias(self, alias: str) -> RemoteCampaign | None:
        offset = 0
        while True:
            raw = await self._request(
                "GET", "/campaigns", params={"limit": CAMPAIGNS_PAGE_SIZE, "offset": offset}
            )
            for item in raw:
                campaign = RemoteCampaign.model_validate(item)
                if campaign.alias == alias and campaign.state != EntityState.DELETED:
                    return campaign
            if len(raw) < CAMPAIGNS_PAGE_SIZE:
                return None
            offset += CAMPAIGNS_PAGE_SIZE

    async def create_campaign(self, name: str, alias: str) -> RemoteCampaign:
        raw = await self._request(
            "POST",
            "/campaigns",
            json={"name": name, "alias": alias, "type": CampaignType.POSITION},
        )
        return RemoteCampaign.model_validate(raw)

    async def delete_campaign(self, campaign_id: int) -> None:
        await self._request("DELETE", f"/campaigns/{campaign_id}")

    # ---- потоки ----

    async def list_streams(self, campaign_id: int) -> list[RemoteStream]:
        """Неудалённые потоки кампании вместе с их неудалёнными офферами."""
        raw = await self._request("GET", f"/campaigns/{campaign_id}/streams") or []
        streams = []
        for item in raw:
            stream = RemoteStream.model_validate(item)
            if stream.state == EntityState.DELETED:
                continue
            stream.offers = [o for o in stream.offers if o.state != EntityState.DELETED]
            streams.append(stream)
        return streams

    async def create_stream(self, campaign_id: int, country: str, offer_id: int) -> RemoteStream:
        raw = await self._request(
            "POST",
            "/streams",
            json={
                "campaign_id": campaign_id,
                "type": StreamType.REGULAR,
                "name": stream_name(country),
                "schema": StreamSchema.LANDINGS,
                "action_type": ActionType.HTTP,
                "state": EntityState.ACTIVE,
                "collect_clicks": True,
                "filters": [{"name": "country", "mode": "accept", "payload": [country]}],
                "offers": [{"offer_id": offer_id, "share": 100}],
            },
        )
        return RemoteStream.model_validate(raw)

    async def update_stream_offers(self, stream_id: int, shares: dict[int, int]) -> None:
        """Заменяет офферы потока: ``shares`` — {offer_id: доля %}."""
        offers = [
            {"offer_id": offer_id, "share": share, "state": EntityState.ACTIVE}
            for offer_id, share in shares.items()
        ]
        await self._request("PUT", f"/streams/{stream_id}", json={"offers": offers})


def build_keitaro_client() -> KeitaroClient:
    http = httpx.AsyncClient(
        base_url=f"{settings.keitaro_url.rstrip('/')}/admin_api/v1",
        headers={"Api-Key": settings.keitaro_api_key},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return KeitaroClient(http)


def get_keitaro(request: Request) -> KeitaroClient:
    """FastAPI-зависимость: общий клиент, созданный при старте приложения."""
    return request.app.state.keitaro

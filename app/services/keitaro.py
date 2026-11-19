import hashlib
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import settings


class KeitaroError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def make_alias(name: str, country: str, offer_id: int) -> str:
    """Детерминированный alias: один и тот же запрос всегда даёт один и тот же alias."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30]
    digest = hashlib.sha1(f"{name.casefold()}|{country}|{offer_id}".encode()).hexdigest()[:8]
    return f"{slug or 'campaign'}-{digest}"


class KeitaroClient:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise KeitaroError(f"Keitaro недоступен: {exc}") from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text
            raise KeitaroError(f"Keitaro {resp.status_code}: {detail}")
        return resp.json() if resp.content else None

    async def list_offers(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/offers") or []

    async def find_campaign_by_alias(self, alias: str) -> dict[str, Any] | None:
        limit, offset = 100, 0
        while True:
            page = await self._request(
                "GET", "/campaigns", params={"limit": limit, "offset": offset}
            )
            for item in page:
                if item.get("alias") == alias and item.get("state") != "deleted":
                    return item
            if len(page) < limit:
                return None
            offset += limit

    async def list_streams(self, campaign_id: int) -> list[dict[str, Any]]:
        return await self._request("GET", f"/campaigns/{campaign_id}/streams") or []

    async def create_campaign(self, name: str, alias: str) -> dict[str, Any]:
        return await self._request(
            "POST", "/campaigns", json={"name": name, "alias": alias, "type": "position"}
        )

    async def delete_campaign(self, campaign_id: int) -> None:
        await self._request("DELETE", f"/campaigns/{campaign_id}")

    async def create_stream(
        self, campaign_id: int, country: str, offer_id: int
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/streams",
            json={
                "campaign_id": campaign_id,
                "type": "regular",
                "name": stream_name(country),
                "schema": "landings",
                "action_type": "http",
                "state": "active",
                "collect_clicks": True,
                "filters": [{"name": "country", "mode": "accept", "payload": [country]}],
                "offers": [{"offer_id": offer_id, "share": 100}],
            },
        )


def stream_name(country: str) -> str:
    return f"{country} flow"


def build_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=f"{settings.keitaro_url.rstrip('/')}/admin_api/v1",
        headers={"Api-Key": settings.keitaro_api_key},
        timeout=15,
    )


async def get_keitaro() -> AsyncIterator[KeitaroClient]:
    async with build_http_client() as http:
        yield KeitaroClient(http)


async def ensure_campaign_with_stream(
    keitaro: KeitaroClient, name: str, alias: str, country: str, offer_id: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Находит или создаёт кампанию и flow в Keitaro — повторный вызов дублей не создаёт."""
    campaign = await keitaro.find_campaign_by_alias(alias)
    created_now = campaign is None
    if campaign is None:
        campaign = await keitaro.create_campaign(name, alias)
    try:
        streams = await keitaro.list_streams(campaign["id"]) if not created_now else []
        stream = next(
            (s for s in streams if s.get("name") == stream_name(country) and s.get("state") != "deleted"),
            None,
        )
        if stream is None:
            stream = await keitaro.create_stream(campaign["id"], country, offer_id)
    except KeitaroError:
        if created_now:  # не оставляем свежесозданную кампанию без flow
            try:
                await keitaro.delete_campaign(campaign["id"])
            except KeitaroError:
                pass
        raise
    return campaign, stream

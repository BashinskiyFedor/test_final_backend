"""Минимальный in-memory Keitaro Admin API для тестов (через httpx.MockTransport)."""

import json

import httpx


class FakeKeitaro:
    def __init__(self) -> None:
        self.offers = [{"id": i, "name": f"Offer {i}", "state": "active"} for i in range(1, 8)]
        self.offers.append({"id": 99, "name": "Old", "state": "deleted"})
        self.campaigns: list[dict] = []
        self.streams: dict[int, dict] = {}  # stream_id -> stream
        self.fail_stream_creation = False
        self.requests: list[tuple[str, str]] = []
        self._next_id = 100

    def add_stream(self, campaign_id: int, name: str, offers: list[tuple[int, int]]) -> dict:
        stream = {
            "id": self._new_id(), "campaign_id": campaign_id, "name": name, "type": "regular",
            "state": "active", "offers": [{"offer_id": o, "share": s} for o, s in offers],
        }  # fmt: skip
        self.streams[stream["id"]] = stream
        return stream

    def stream_offers(self, stream_id: int) -> dict[int, int]:
        return {o["offer_id"]: o["share"] for o in self.streams[stream_id]["offers"]}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _handle(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path.removeprefix("/admin_api/v1")
        body = json.loads(req.content) if req.content else None
        self.requests.append((req.method, path))

        if (req.method, path) == ("GET", "/offers"):
            return httpx.Response(200, json=self.offers)
        if (req.method, path) == ("GET", "/campaigns"):
            return httpx.Response(200, json=self.campaigns)
        if (req.method, path) == ("POST", "/campaigns"):
            campaign = {"id": self._new_id(), "state": "active", **body}
            self.campaigns.append(campaign)
            return httpx.Response(200, json=campaign)
        if req.method == "DELETE" and path.startswith("/campaigns/"):
            cid = int(path.rsplit("/", 1)[1])
            self.campaigns = [c for c in self.campaigns if c["id"] != cid]
            return httpx.Response(200, json={})
        if req.method == "GET" and path.endswith("/streams"):
            cid = int(path.split("/")[2])
            return httpx.Response(
                200, json=[s for s in self.streams.values() if s["campaign_id"] == cid]
            )
        if (req.method, path) == ("POST", "/streams"):
            if self.fail_stream_creation:
                return httpx.Response(500, json={"error": "boom"})
            stream = self.add_stream(
                body["campaign_id"], body["name"], [(o["offer_id"], o["share"]) for o in body["offers"]]
            )
            return httpx.Response(200, json=stream)
        if req.method == "PUT" and path.startswith("/streams/"):
            stream = self.streams[int(path.rsplit("/", 1)[1])]
            stream["offers"] = body["offers"]
            return httpx.Response(200, json=stream)
        return httpx.Response(404, json={"error": f"unexpected {req.method} {path}"})

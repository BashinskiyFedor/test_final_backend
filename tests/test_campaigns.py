from tests.fake_keitaro import FakeKeitaro

BODY = {"name": "Test A", "country": "us", "offer_id": 5}


def test_create_campaign_makes_campaign_and_stream_in_keitaro_and_db(client, keitaro: FakeKeitaro):
    resp = client.post("/api/campaigns", json=BODY)

    assert resp.status_code == 201
    data = resp.json()
    assert data["country"] == "US" and data["already_exists"] is False
    (stream,) = keitaro.streams.values()
    assert stream["offers"] == [{"offer_id": 5, "share": 100}]
    assert [c["offer_id"] for c in client.get("/api/campaigns").json()] == [5]


def test_repeated_request_does_not_duplicate_anything(client, keitaro: FakeKeitaro):
    client.post("/api/campaigns", json=BODY)
    resp = client.post("/api/campaigns", json=BODY)

    assert resp.status_code == 200 and resp.json()["already_exists"] is True
    assert len(keitaro.campaigns) == 1 and len(keitaro.streams) == 1
    assert len(client.get("/api/campaigns").json()) == 1


def test_retry_after_crash_between_keitaro_and_db_reuses_keitaro_campaign(client, keitaro):
    from sqlalchemy import update

    from app.db.session import SessionLocal
    from app.models import Campaign, CampaignStatus

    client.post("/api/campaigns", json=BODY)

    async def simulate_crash():
        async with SessionLocal() as session:
            await session.execute(
                update(Campaign).values(
                    status=CampaignStatus.PENDING, keitaro_campaign_id=None, keitaro_stream_id=None
                )
            )
            await session.commit()

    client.portal.call(simulate_crash)

    resp = client.post("/api/campaigns", json=BODY)

    assert resp.status_code == 201
    assert len(keitaro.campaigns) == 1 and len(keitaro.streams) == 1
    assert len(client.get("/api/campaigns").json()) == 1


def test_failed_stream_creation_rolls_back_keitaro_and_db(client, keitaro: FakeKeitaro):
    keitaro.fail_stream_creation = True

    resp = client.post("/api/campaigns", json=BODY)

    assert resp.status_code == 502
    assert keitaro.campaigns == []
    assert client.get("/api/campaigns").json() == []
    keitaro.fail_stream_creation = False
    assert client.post("/api/campaigns", json=BODY).status_code == 201


def test_unknown_offer_is_rejected_without_side_effects(client, keitaro: FakeKeitaro):
    resp = client.post("/api/campaigns", json={**BODY, "offer_id": 4242})

    assert resp.status_code == 422
    assert keitaro.campaigns == [] and client.get("/api/campaigns").json() == []


def test_invalid_country_is_rejected(client):
    assert client.post("/api/campaigns", json={**BODY, "country": "USA"}).status_code == 422


def test_offers_search_by_name_and_id_skips_deleted(client):
    assert [o["id"] for o in client.get("/api/offers?q=offer 3").json()] == [3]
    assert [o["id"] for o in client.get("/api/offers?q=5").json()] == [5]
    assert 99 not in [o["id"] for o in client.get("/api/offers").json()]


def test_offers_are_cached_between_requests(client, keitaro: FakeKeitaro):
    client.get("/api/offers")
    client.get("/api/offers?q=1")
    assert keitaro.requests.count(("GET", "/offers")) == 1


def test_unknown_campaign_is_404(client):
    assert client.get("/api/campaigns/777").status_code == 404
    assert client.get("/api/campaigns/777/streams").status_code == 404


def test_new_campaign_does_not_scan_keitaro_campaigns(client, keitaro: FakeKeitaro):
    client.get("/api/offers?refresh=true")  # как при открытии формы: кэш офферов прогрет
    keitaro.requests.clear()

    client.post("/api/campaigns", json=BODY)

    assert keitaro.requests == [("POST", "/campaigns"), ("POST", "/streams")]


def test_offers_refresh_bypasses_cache(client, keitaro: FakeKeitaro):
    client.get("/api/offers")
    client.get("/api/offers?refresh=true")
    assert keitaro.requests.count(("GET", "/offers")) == 2

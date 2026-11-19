from tests.fake_keitaro import FakeKeitaro


def shares(stream: dict) -> dict[int, int]:
    return {o["offer_id"]: o["share"] for o in stream["offers"] if o["active"]}


def offer_pk(stream: dict, offer_id: int) -> int:
    return next(o["id"] for o in stream["offers"] if o["offer_id"] == offer_id)


def test_streams_without_offers_are_listed_but_not_editable(client, keitaro, campaign):
    keitaro.add_stream(campaign["campaign_id"], "plain", [])
    streams = client.post("/api/campaigns/1/streams/sync").json()
    plain = next(s for s in streams if s["name"] == "plain")

    assert plain["has_offers"] is False and plain["offers"] == []
    assert client.post(f"/api/streams/{plain['id']}/offers", json={"offer_id": 1}).status_code == 409


def test_sync_loads_offers_and_stream_is_clean(stream):
    assert shares(stream) == {1: 34, 2: 33, 3: 33} and stream["dirty"] is False


def test_add_offer_recalculates_weights_and_keeps_keitaro_untouched(client, keitaro, stream):
    resp = client.post(f"/api/streams/{stream['id']}/offers", json={"offer_id": 4}).json()

    assert shares(resp) == {1: 25, 2: 25, 3: 25, 4: 25} and resp["dirty"] is True
    assert keitaro.stream_offers(stream["keitaro_stream_id"]) == {1: 34, 2: 33, 3: 33}


def test_cancel_removes_draft_offers_and_restores_weights(client, stream):
    client.post(f"/api/streams/{stream['id']}/offers", json={"offer_id": 4})
    resp = client.post(f"/api/streams/{stream['id']}/cancel").json()

    assert shares(resp) == {1: 34, 2: 33, 3: 33} and resp["dirty"] is False
    assert [o["offer_id"] for o in resp["offers"]] == [1, 2, 3]


def test_push_publishes_offers_and_weights(client, keitaro, stream):
    client.post(f"/api/streams/{stream['id']}/offers", json={"offer_id": 4})
    resp = client.post(f"/api/streams/{stream['id']}/push").json()

    assert resp["dirty"] is False
    assert keitaro.stream_offers(stream["keitaro_stream_id"]) == {1: 25, 2: 25, 3: 25, 4: 25}


def test_remove_push_then_bring_back(client, keitaro, stream):
    sid, ksid = stream["id"], stream["keitaro_stream_id"]
    removed = client.delete(f"/api/streams/{sid}/offers/{offer_pk(stream, 3)}").json()
    assert removed["dirty"] is True and shares(removed) == {1: 50, 2: 50}
    assert next(o for o in removed["offers"] if o["offer_id"] == 3)["share"] == 0

    client.post(f"/api/streams/{sid}/push")
    assert keitaro.stream_offers(ksid) == {1: 50, 2: 50}

    archived = client.post("/api/campaigns/1/streams/sync").json()
    archived = next(s for s in archived if s["id"] == sid)
    assert any(o["offer_id"] == 3 and not o["active"] for o in archived["offers"])  # остался у нас

    back = client.post(f"/api/streams/{sid}/offers/{offer_pk(archived, 3)}/restore").json()
    assert back["dirty"] is True and set(shares(back)) == {1, 2, 3}
    client.post(f"/api/streams/{sid}/push")
    assert set(keitaro.stream_offers(ksid)) == {1, 2, 3}


def test_cancel_after_remove_restores_offer(client, stream):
    sid = stream["id"]
    client.delete(f"/api/streams/{sid}/offers/{offer_pk(stream, 2)}")
    resp = client.post(f"/api/streams/{sid}/cancel").json()

    assert shares(resp) == {1: 34, 2: 33, 3: 33} and resp["dirty"] is False


def test_offer_removed_in_keitaro_becomes_archived_after_sync(client, keitaro, stream):
    keitaro.streams[stream["keitaro_stream_id"]]["offers"] = [{"offer_id": 1, "share": 100}]
    synced = next(s for s in client.post("/api/campaigns/1/streams/sync").json() if s["id"] == stream["id"])

    assert shares(synced) == {1: 100} and synced["dirty"] is False
    assert {o["offer_id"] for o in synced["offers"] if not o["active"]} == {2, 3}


def test_sync_does_not_overwrite_local_draft(client, stream):
    client.post(f"/api/streams/{stream['id']}/offers", json={"offer_id": 4})
    synced = next(s for s in client.post("/api/campaigns/1/streams/sync").json() if s["id"] == stream["id"])

    assert shares(synced) == {1: 25, 2: 25, 3: 25, 4: 25} and synced["dirty"] is True


def test_pinned_weight_survives_add_remove_and_restore(client, keitaro, stream):
    sid = stream["id"]
    client.post(f"/api/streams/{sid}/offers", json={"offer_id": 4})
    pinned = client.patch(f"/api/streams/{sid}/offers/{offer_pk(stream, 1)}", json={"pinned": True}).json()
    assert shares(pinned)[1] == 25

    added = client.post(f"/api/streams/{sid}/offers", json={"offer_id": 5}).json()
    assert shares(added) == {1: 25, 2: 19, 3: 19, 4: 19, 5: 18}

    removed = client.delete(f"/api/streams/{sid}/offers/{offer_pk(added, 2)}").json()
    assert shares(removed) == {1: 25, 3: 25, 4: 25, 5: 25}

    client.post(f"/api/streams/{sid}/push")
    assert keitaro.stream_offers(stream["keitaro_stream_id"]) == {1: 25, 3: 25, 4: 25, 5: 25}


def test_removed_offer_cannot_be_pinned_or_removed_twice(client, stream):
    sid = stream["id"]
    pk = offer_pk(stream, 2)
    client.delete(f"/api/streams/{sid}/offers/{pk}")

    assert client.patch(f"/api/streams/{sid}/offers/{pk}", json={"pinned": True}).status_code == 409
    assert client.delete(f"/api/streams/{sid}/offers/{pk}").status_code == 409


def test_push_is_rejected_when_weights_do_not_sum_to_100(client, keitaro, stream):
    from sqlalchemy import update

    from app.db.session import SessionLocal
    from app.models import StreamOffer

    async def break_weights():
        async with SessionLocal() as session:
            await session.execute(update(StreamOffer).values(share=10))
            await session.commit()

    client.portal.call(break_weights)

    assert client.post(f"/api/streams/{stream['id']}/push").status_code == 422
    assert keitaro.stream_offers(stream["keitaro_stream_id"]) == {1: 34, 2: 33, 3: 33}


def test_duplicate_and_unknown_offers_are_rejected(client, stream):
    sid = stream["id"]
    assert client.post(f"/api/streams/{sid}/offers", json={"offer_id": 1}).status_code == 409
    assert client.post(f"/api/streams/{sid}/offers", json={"offer_id": 4242}).status_code == 422
    assert client.post("/api/streams/9999/push").status_code == 404
    assert client.delete(f"/api/streams/{sid}/offers/9999").status_code == 404

import os

# Должно быть выставлено до импорта приложения: движок БД создаётся при импорте.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.keitaro import KeitaroClient, get_keitaro  # noqa: E402
from tests.fake_keitaro import FakeKeitaro  # noqa: E402


@pytest.fixture
def keitaro() -> FakeKeitaro:
    return FakeKeitaro()


@pytest.fixture
def client(keitaro: FakeKeitaro):
    shared = KeitaroClient(
        httpx.AsyncClient(base_url="http://keitaro/admin_api/v1", transport=keitaro.transport())
    )
    app.dependency_overrides[get_keitaro] = lambda: shared
    # Закрытие lifespan освобождает in-memory SQLite, поэтому каждый тест стартует с чистой БД.
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def campaign(client: TestClient) -> dict:
    resp = client.post("/api/campaigns", json={"name": "Test", "country": "au", "offer_id": 1})
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def stream(client: TestClient, keitaro: FakeKeitaro, campaign: dict) -> dict:
    """Поток с тремя офферами (34/33/33), подтянутый в нашу обёртку."""
    keitaro.streams.clear()
    keitaro.add_stream(campaign["campaign_id"], "no offers", [])
    keitaro.add_stream(campaign["campaign_id"], "Rest", [(1, 34), (2, 33), (3, 33)])
    streams = client.post("/api/campaigns/1/streams/sync").json()  # кампания в чистой БД одна
    return next(s for s in streams if s["has_offers"])

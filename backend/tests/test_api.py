import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.database import Base
from app.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)

    def override():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _make_accounts(client, n):
    for i in range(n):
        r = client.post("/api/accounts", json={"name": f"A{i}", "balance_cents": 0})
        assert r.status_code == 200


def test_duplicate_account_name_is_409(client):
    assert client.post("/api/accounts", json={"name": "Checking"}).status_code == 200
    assert client.post("/api/accounts", json={"name": "Checking"}).status_code == 409


def test_account_name_can_be_updated(client):
    account = client.post("/api/accounts", json={"name": "Checking"}).json()
    response = client.patch(f"/api/accounts/{account['id']}", json={"name": "Main checking"})
    assert response.status_code == 200
    assert response.json()["name"] == "Main checking"
    assert client.patch(f"/api/accounts/{account['id']}", json={"name": " "}).status_code == 422
    other = client.post("/api/accounts", json={"name": "Savings"}).json()
    assert client.patch(f"/api/accounts/{other['id']}", json={"name": "Main checking"}).status_code == 409


def test_accounts_have_explicit_domain(client):
    response = client.post("/api/accounts", json={
        "name": "Robinhood", "type": "brokerage", "domain": "investing",
    })
    assert response.status_code == 200
    assert response.json()["domain"] == "investing"
    account_id = response.json()["id"]
    response = client.patch(f"/api/accounts/{account_id}", json={"domain": "spending"})
    assert response.status_code == 200
    assert response.json()["domain"] == "spending"
    assert client.patch(f"/api/accounts/{account_id}", json={"domain": "invalid"}).status_code == 422


def test_list_envelope_and_paging(client):
    _make_accounts(client, 3)
    body = client.get("/api/accounts").json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    body = client.get("/api/accounts?limit=2").json()
    assert (body["total"], len(body["items"])) == (3, 2)
    body = client.get("/api/accounts?limit=2&offset=2").json()
    assert (body["total"], len(body["items"])) == (3, 1)


def test_limit_clamped_to_max(client):
    _make_accounts(client, 1)
    body = client.get("/api/accounts?limit=9999").json()
    assert (body["total"], len(body["items"])) == (1, 1)


def test_bad_limit_is_422_with_detail_shape(client):
    r = client.get("/api/accounts?limit=abc")
    assert r.status_code == 422
    assert "detail" in r.json()


def test_unknown_route_is_404_with_detail_shape(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


def test_server_error_is_json_detail_shape(client):
    def broken():
        raise RuntimeError("boom")

    app.dependency_overrides[get_db] = broken
    try:
        r = client.get("/api/accounts")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal Server Error"}

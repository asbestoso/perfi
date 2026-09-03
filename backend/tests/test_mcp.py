import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.database import Base
from app.main import app
from conftest import make_txn


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PERFI_MCP_ENABLED", "1")
    monkeypatch.setenv("PERFI_MCP_TOKEN", "tok")
    monkeypatch.delenv("PERFI_MCP_WRITE_ENABLED", raising=False)
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


def _rpc(client, method, params=None, token="tok"):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers=headers)


def test_mcp_gates(client):
    assert client.post("/api/mcp", json={}).status_code == 401
    bad = _rpc(client, "tools/list", token="wrong")
    assert bad.status_code == 401


def test_initialize_and_list_read_only(store, client):
    init = _rpc(client, "initialize").json()
    assert init["result"]["protocolVersion"] == "2024-11-05"
    assert _rpc(client, "notifications/initialized").status_code == 202

    names = [t["name"] for t in _rpc(client, "tools/list").json()["result"]["tools"]]
    assert "list_accounts" in names and "get_dashboard_summary" in names
    assert "update_transaction_category" not in names
    assert _rpc(client, "bogus").json()["error"]["code"] == -32601


def test_read_tools(store, client):
    funded = client.post("/api/accounts", json={"name": "Funded", "balance_cents": 50000}).json()["id"]
    store["txn"] = make_txn(client, funded, store["cats"]["Uncategorized"],
                            -1000, "Whole Foods", "2026-01-05")
    assert _rpc(client, "tools/call", {"name": "list_accounts"}) \
        .json()["result"]["content"][0]["text"].find("Checking") != -1

    txns = json.loads(_rpc(client, "tools/call", {
        "name": "get_transactions", "arguments": {"q": "whole"}})
        .json()["result"]["content"][0]["text"])
    assert len(txns) == 1 and txns[0]["merchant"] == "Whole Foods"

    dash = json.loads(_rpc(client, "tools/call", {"name": "get_dashboard_summary"})
                      .json()["result"]["content"][0]["text"])
    assert dash["net_worth"]["net_worth_cents"] == 50000

    unknown = _rpc(client, "tools/call", {"name": "nope"}).json()
    assert unknown["error"]["code"] == -32601


def test_write_tools_gated_and_working(store, client, monkeypatch):
    funded = client.post("/api/accounts", json={"name": "Funded", "balance_cents": 50000}).json()["id"]
    store["txn"] = make_txn(client, funded, store["cats"]["Uncategorized"],
                            -1000, "Whole Foods", "2026-01-05")
    blocked = _rpc(client, "tools/call", {"name": "update_transaction_category",
                                          "arguments": {"transaction_id": 1, "category_id": 1}})
    assert blocked.json()["error"]["code"] == -32601

    monkeypatch.setenv("PERFI_MCP_WRITE_ENABLED", "1")
    names = [t["name"] for t in _rpc(client, "tools/list").json()["result"]["tools"]]
    assert "update_transaction_category" in names and "set_budget_category" in names

    out = json.loads(_rpc(client, "tools/call", {
        "name": "update_transaction_category",
        "arguments": {"transaction_id": store["txn"]["id"],
                      "category_id": store["cats"]["Groceries"]}})
        .json()["result"]["content"][0]["text"])
    assert out == {"ok": True, "id": store["txn"]["id"]}
    got = client.get(f"/api/transactions/{store['txn']['id']}").json()
    assert got["category_id"] == store["cats"]["Groceries"]
    assert got["category_source"] == "manual"

    out = json.loads(_rpc(client, "tools/call", {
        "name": "set_budget_category",
        "arguments": {"category_id": store["cats"]["Groceries"],
                      "month": "2026-09", "limit_cents": 70000}})
        .json()["result"]["content"][0]["text"])
    assert out["ok"] is True
    assert client.get("/api/budgets/2026-09").json()[0]["limit_cents"] == 70000


def test_mcp_disabled_and_unconfigured(monkeypatch):
    import app.services.mcp_server as mcp
    monkeypatch.delenv("PERFI_MCP_ENABLED", raising=False)
    from fastapi.testclient import TestClient as TC
    with TC(app, raise_server_exceptions=False) as c:
        assert c.post("/api/mcp", json={}).status_code == 404
    monkeypatch.setenv("PERFI_MCP_ENABLED", "1")
    monkeypatch.delenv("PERFI_MCP_TOKEN", raising=False)
    with TC(app, raise_server_exceptions=False) as c:
        r = c.post("/api/mcp", json={}, headers={"Authorization": "Bearer x"})
        assert r.status_code == 503

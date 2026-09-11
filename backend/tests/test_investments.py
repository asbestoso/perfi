def test_lots_crud(client):
    r = client.post("/api/lots", json={
        "symbol": "VTI", "quantity_milli": 10000, "cost_cents": 200000,
        "acquired": "2025-06-01"})
    assert r.status_code == 200
    lot = r.json()
    assert lot["acquired"] == "2025-06-01"

    r = client.patch(f"/api/lots/{lot['id']}", json={"cost_cents": 210000})
    assert r.json()["cost_cents"] == 210000
    assert client.patch("/api/lots/9999", json={"cost_cents": 1}).status_code == 404

    assert client.get("/api/lots").json()["total"] == 1
    assert client.delete(f"/api/lots/{lot['id']}").json() == {"ok": True}
    assert client.get("/api/lots").json()["total"] == 0


def test_summary_math(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.api.get_live_price",
        lambda symbol: {"VTI": 25000, "BND": 8000}[symbol],
    )
    client.post("/api/investments", json={
        "symbol": "VTI", "quantity_milli": 10000, "price_cents": 25000})
    client.post("/api/lots", json={
        "symbol": "vti", "quantity_milli": 6000, "cost_cents": 120000})
    client.post("/api/lots", json={
        "symbol": "VTI", "quantity_milli": 4000, "cost_cents": 80000})
    # holding without lots: cost unknown
    client.post("/api/investments", json={
        "symbol": "BND", "quantity_milli": 5000, "price_cents": 8000})

    s = client.get("/api/investments/summary").json()
    by_sym = {p["symbol"]: p for p in s["positions"]}
    assert by_sym["VTI"]["market_cents"] == 250000
    assert by_sym["VTI"]["cost_cents"] == 200000
    assert by_sym["VTI"]["gain_cents"] == 50000
    assert by_sym["BND"]["cost_cents"] is None and by_sym["BND"]["gain_cents"] is None
    assert s["market_cents"] == 250000 + 40000
    assert s["cost_cents"] == 200000
    assert s["gain_cents"] == 50000


def test_summary_aggregates_same_symbol_across_accounts(store, client, monkeypatch):
    monkeypatch.setattr("app.api.routes.api.get_live_price", lambda symbol: 25000)
    for account_id, quantity in zip(store["accts"], (10000, 5000)):
        response = client.post("/api/investments", json={
            "symbol": "VTI", "account_id": account_id,
            "quantity_milli": quantity})
        assert response.status_code == 200

    summary = client.get("/api/investments/summary").json()

    assert len(summary["positions"]) == 1
    position = summary["positions"][0]
    assert position["symbol"] == "VTI"
    assert position["quantity_milli"] == 15000
    assert position["price_cents"] == 25000
    assert position["market_cents"] == 375000
    assert [(a["name"], a["quantity_milli"]) for a in position["accounts"]] == [
        ("Checking", 10000), ("Card", 5000)]
    assert summary["market_cents"] == 375000


def test_summary_fetches_one_quote_per_symbol(store, client, monkeypatch):
    calls = []

    def quote(symbol):
        calls.append(symbol)
        return 25000

    monkeypatch.setattr("app.api.routes.api.get_live_price", quote)
    for account_id in store["accts"]:
        client.post("/api/investments", json={
            "symbol": "VTI", "account_id": account_id, "quantity_milli": 1000})

    calls.clear()
    assert client.get("/api/investments/summary").status_code == 200
    assert calls == ["VTI"]


def test_holding_can_be_linked_to_account(store, client, monkeypatch):
    monkeypatch.setattr("app.api.routes.api.get_live_price", lambda symbol: 20000)
    account_id = store["acct"]
    response = client.post("/api/investments", json={
        "symbol": "AAPL", "account_id": account_id,
        "quantity_milli": 1000, "price_cents": 20000})
    assert response.status_code == 200
    assert response.json()["account_id"] == account_id

    holdings = client.get("/api/investments").json()["holdings"]
    assert holdings[0]["account_id"] == account_id
    assert client.post("/api/investments", json={
        "symbol": "MSFT", "account_id": 9999}).status_code == 404


def test_lots_csv_import(client):
    body = ("symbol,quantity,cost,acquired\n"
            'VTI,10.5,"$2,100.00",2025-01-15\n'
            "BND,,500,2025-02-01\n"
            "XXX,abc,10,\n")
    r = client.post("/api/investments/import",
                    files={"file": ("lots.csv", body, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json() == {"created": 1, "skipped": 2}
    lots = client.get("/api/lots").json()["items"]
    assert lots[0]["symbol"] == "VTI" and lots[0]["quantity_milli"] == 10500
    assert lots[0]["cost_cents"] == 210000


def test_lots_import_is_idempotent_and_rejects_missing_cost(client):
    body = ("symbol,quantity,cost,acquired\n"
            "VTI,10,2100.00,2025-01-15\n"
            "BND,5,,2025-02-01\n")
    r = client.post("/api/investments/import",
                    files={"file": ("lots.csv", body, "text/csv")})
    assert r.json() == {"created": 1, "skipped": 1}
    r = client.post("/api/investments/import",
                    files={"file": ("lots.csv", body, "text/csv")})
    assert r.json() == {"created": 0, "skipped": 2}
    assert client.get("/api/lots").json()["total"] == 1

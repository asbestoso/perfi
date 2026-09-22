def test_summary_math(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.api.get_live_price",
        lambda symbol: {"VTI": 25000, "BND": 8000}[symbol],
    )
    client.post("/api/investments", json={
        "symbol": "VTI", "quantity_milli": 10000, "price_cents": 25000})
    client.post("/api/investments", json={
        "symbol": "BND", "quantity_milli": 5000, "price_cents": 8000})

    s = client.get("/api/investments/summary").json()
    by_sym = {p["symbol"]: p for p in s["positions"]}
    assert by_sym["VTI"]["market_cents"] == 250000
    # holdings-only summary: no cost or gain keys at all
    assert "cost_cents" not in by_sym["VTI"] and "gain_cents" not in by_sym["VTI"]
    assert by_sym["BND"]["market_cents"] == 40000
    assert s["market_cents"] == 250000 + 40000
    assert "cost_cents" not in s and "gain_cents" not in s


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
    assert position["accounts"][0]["price_cents"] == 25000
    assert position["accounts"][0]["market_cents"] == 250000
    assert summary["market_cents"] == 375000


def test_accounts_balance_is_derived_from_holdings(store, client, monkeypatch):
    monkeypatch.setattr("app.api.routes.api.get_live_price", lambda symbol: 25000)
    client.post("/api/accounts", json={"name": "Cash", "balance_cents": 12500})
    client.post("/api/investments", json={
        "symbol": "VTI", "account_id": store["acct"], "quantity_milli": 2000})

    accounts = {
        account["name"]: account["balance_cents"]
        for account in client.get("/api/accounts?limit=500").json()["items"]
    }
    assert accounts["Checking"] == 50000
    assert accounts["Cash"] == 12500


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


def test_holding_quantity_patch_and_zero_removes(store, client, monkeypatch):
    monkeypatch.setattr("app.api.routes.api.get_live_price", lambda symbol: 20000)
    account_id = store["acct"]
    created = client.post("/api/investments", json={
        "symbol": "VTI", "account_id": account_id, "quantity_milli": 1000})
    assert created.status_code == 200
    holding_id = created.json()["id"]

    patched = client.patch(f"/api/investments/{holding_id}",
                           json={"quantity_milli": 2500})
    assert patched.status_code == 200
    assert patched.json()["deleted"] is False
    assert client.get("/api/investments").json()["holdings"][0]["quantity_milli"] == 2500

    assert client.patch(f"/api/investments/{holding_id}",
                        json={"quantity_milli": -1}).status_code == 422
    assert client.patch("/api/investments/9999",
                        json={"quantity_milli": 5}).status_code == 404

    removed = client.patch(f"/api/investments/{holding_id}", json={"quantity_milli": 0})
    assert removed.status_code == 200
    assert removed.json()["deleted"] is True
    assert client.get("/api/investments").json()["holdings"] == []


def test_adding_existing_account_holding_overwrites_quantity(store, client, monkeypatch):
    monkeypatch.setattr("app.api.routes.api.get_live_price", lambda symbol: 20000)
    account_id = store["acct"]
    client.post("/api/investments", json={
        "symbol": "VTI", "account_id": account_id, "quantity_milli": 1000})
    response = client.post("/api/investments", json={
        "symbol": "vti", "account_id": account_id, "quantity_milli": 2500})

    assert response.status_code == 200
    holdings = client.get("/api/investments").json()["holdings"]
    matching = [h for h in holdings if h["symbol"] == "VTI" and h["account_id"] == account_id]
    assert len(matching) == 1
    assert matching[0]["quantity_milli"] == 2500


def test_symbol_classification_applies_to_all_accounts(store, client, monkeypatch):
    monkeypatch.setattr("app.api.routes.api.get_live_price", lambda symbol: 20000)
    for account_id in store["accts"]:
        client.post("/api/investments", json={
            "symbol": "VXUS", "account_id": account_id, "quantity_milli": 1000
        })

    response = client.patch("/api/investments/classification/vxus",
                            json={"category": "Intl"})
    assert response.status_code == 200
    assert response.json()["category"] == "Intl"
    assert {h["category"] for h in client.get("/api/investments").json()["holdings"]} == {"Intl"}
    position = client.get("/api/investments/summary").json()["positions"][0]
    assert position["category"] == "Intl"
    assert client.patch("/api/investments/classification/VXUS",
                        json={"category": "Cash"}).status_code == 200
    assert client.patch("/api/investments/classification/VXUS",
                        json={"category": "Crypto"}).status_code == 200
    assert client.patch("/api/investments/classification/VXUS",
                        json={"category": ""}).status_code == 422


def test_symbol_mixed_allocations_total_one_hundred(client):
    client.post("/api/investments", json={"symbol": "VTI", "quantity_milli": 1000})
    response = client.put("/api/investments/allocation/VTI", json={
        "allocations": {"US": 70, "Intl": 30, "Bonds": ""}})
    assert response.status_code == 200
    assert response.json()["allocations"] == {"US": 70, "Intl": 30}
    position = client.get("/api/investments/summary").json()["positions"][0]
    assert position["allocations"] == {"US": 70, "Intl": 30}
    assert client.put("/api/investments/allocation/VTI", json={
        "allocations": {"US": 70, "Intl": 20}}).status_code == 422
    assert client.put("/api/investments/allocation/VTI", json={
        "allocations": {"US": 70, "Intl": 30, "Bonds": "nan"}}).status_code == 422


def test_missing_holding_name_is_loaded_on_demand(store, client, monkeypatch):
    monkeypatch.setattr("app.api.routes.api.get_live_price", lambda symbol: 20000)
    monkeypatch.setattr("app.api.routes.api.get_live_name", lambda symbol: None)
    client.post("/api/investments", json={
        "symbol": "AMZN", "account_id": store["acct"], "quantity_milli": 1000})

    assert client.get("/api/investments").json()["holdings"][0]["name"] is None
    monkeypatch.setattr("app.api.routes.api.get_live_name", lambda symbol: "Amazon.com, Inc.")
    response = client.get("/api/investments/name/AMZN")
    assert response.json()["name"] == "Amazon.com, Inc."
    assert client.get("/api/investments").json()["holdings"][0]["name"] == "Amazon.com, Inc."


def test_btc_uses_bitcoin_usd_yahoo_symbol(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.api.get_live_price", lambda symbol: 20000)
    client.post("/api/investments", json={"symbol": "BTC", "quantity_milli": 1000})
    from app.services.market_data import yahoo_symbol
    assert yahoo_symbol("BTC") == "BTC-USD"
    assert yahoo_symbol("AAPL") == "AAPL"


def test_summary_records_one_snapshot_per_day(client, monkeypatch):
    import datetime as dt
    monkeypatch.setattr("app.api.routes.api.get_live_price", lambda symbol: 10000)
    client.post("/api/investments", json={"symbol": "VTI", "quantity_milli": 10000})
    client.post("/api/investments", json={"symbol": "BND", "quantity_milli": 5000})

    client.get("/api/investments/summary")
    client.get("/api/investments/summary")
    history = client.get("/api/investments/history").json()["points"]
    assert len(history) == 2
    by_sym = {point["symbol"]: point for point in history}
    assert by_sym["VTI"]["date"] == dt.date.today().isoformat()
    assert by_sym["VTI"]["market_cents"] == 100000
    assert by_sym["BND"]["market_cents"] == 50000

    monkeypatch.setattr("app.api.routes.api.get_live_price", lambda symbol: 20000)
    client.get("/api/investments/summary")
    history = client.get("/api/investments/history").json()["points"]
    assert len(history) == 2
    by_sym = {point["symbol"]: point for point in history}
    assert by_sym["VTI"]["market_cents"] == 200000
    assert by_sym["BND"]["market_cents"] == 100000


def test_quote_cache_serves_repeat_summaries(client, monkeypatch):
    from app.services import market_data
    market_data.clear_quote_cache()
    calls = []

    def quote(symbol):
        calls.append(symbol)
        return 25000

    monkeypatch.setattr("app.services.market_data._fetch_price", quote)
    client.post("/api/investments", json={"symbol": "VTI", "quantity_milli": 1000})

    assert client.get("/api/investments/summary").status_code == 200
    assert calls == ["VTI"]
    assert client.get("/api/investments/summary").status_code == 200
    assert calls == ["VTI"]
    market_data.clear_quote_cache()

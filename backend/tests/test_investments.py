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


def test_orders_create_fifo_buy_and_sell(store, client, monkeypatch):
    monkeypatch.setattr("app.api.routes.api.get_live_price", lambda symbol: 12000)
    buy = client.post("/api/investment-orders", json={
        "account_id": store["acct"], "symbol": "VTI", "side": "buy",
        "quantity_milli": 10000, "price_cents": 10000,
        "executed_at": "2026-01-01"})
    assert buy.status_code == 200
    sell = client.post("/api/investment-orders", json={
        "account_id": store["acct"], "symbol": "VTI", "side": "sell",
        "quantity_milli": 4000, "price_cents": 12000,
        "executed_at": "2026-02-01"})
    assert sell.status_code == 200
    assert sell.json()["cost_basis_cents"] == 40000
    assert sell.json()["gain_cents"] == 8000
    assert client.post("/api/investment-orders", json={
        "account_id": store["acct"], "symbol": "VTI", "side": "sell",
        "quantity_milli": 7000, "price_cents": 12000,
        "executed_at": "2026-02-01"}).status_code == 422
    response = client.get("/api/investment-orders/analysis")
    assert response.status_code == 200
    sell_row = next(row for row in response.json()["items"] if row["side"] == "sell")
    assert sell_row["cost_basis_cents"] == 40000
    assert sell_row["gain_cents"] == 8000
    assert sell_row["percent"] == 20
    buy_row = next(row for row in response.json()["items"] if row["side"] == "buy")
    assert buy_row["annualized_percent"] is not None


def test_trade_analysis_hides_recent_annualized_return(store, client):
    response = client.post("/api/investment-orders", json={
        "account_id": store["acct"], "symbol": "VTI", "side": "buy",
        "quantity_milli": 1000, "price_cents": 10000,
        "executed_at": "2026-09-01"})
    assert response.status_code == 200
    analysis = client.get("/api/investment-orders/analysis").json()
    assert analysis["items"][0]["annualized_percent"] is None


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
    assert client.patch("/api/investments/classification/VXUS",
                        json={"category": "Cash"}).status_code == 200
    assert client.patch("/api/investments/classification/VXUS",
                        json={"category": "Crypto"}).status_code == 200
    assert client.patch("/api/investments/classification/VXUS",
                        json={"category": ""}).status_code == 422


def test_symbol_mixed_allocations_total_one_hundred(client):
    response = client.put("/api/investments/allocation/VTI", json={
        "allocations": {"US": 70, "Intl": 30, "Bonds": ""}})
    assert response.status_code == 200
    assert response.json()["allocations"] == {"US": 70, "Intl": 30}
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

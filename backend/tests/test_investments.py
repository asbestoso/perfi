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


def test_summary_math(client):
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

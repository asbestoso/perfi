from conftest import make_txn


def _seed_two_months(store, client):
    acct = store["acct"]
    g, i = store["cats"]["Groceries"], store["cats"]["Income"]
    make_txn(client, acct, g, -1000, "Whole Foods", "2026-07-05")
    make_txn(client, acct, i, 300000, "Payroll", "2026-07-01")
    make_txn(client, acct, g, -2000, "Kroger", "2026-08-05")
    make_txn(client, acct, i, 300000, "Payroll", "2026-08-01")


def test_snapshot_upsert_and_history(store, client):
    client.post("/api/accounts", json={"name": "Savings", "balance_cents": 100000})
    r = client.post("/api/snapshots/run").json()
    assert r["cash_cents"] == 100000 and r["net_worth_cents"] == 100000
    r2 = client.post("/api/snapshots/run").json()
    assert r2 == r  # same day: upsert, no duplicate
    hist = client.get("/api/net-worth-history").json()
    assert len(hist) == 1 and hist[0]["cash_cents"] == 100000


def test_monthly_trends_math(store, client):
    _seed_two_months(store, client)
    body = client.get("/api/reports-trends?months=60").json()
    by_month = {m["month"]: m for m in body}
    assert by_month["2026-07"] == {"month": "2026-07", "income_cents": 300000,
                                   "expense_cents": 1000, "net_cents": 299000}
    assert by_month["2026-08"]["net_cents"] == 298000
    assert client.get("/api/reports-trends?months=abc").status_code == 422


def test_category_trends_shape(store, client):
    _seed_two_months(store, client)
    body = client.get("/api/reports-category-trends?months=60").json()
    i7, i8 = body["months"].index("2026-07"), body["months"].index("2026-08")
    series = {s["category"]: (s["totals"][i7], s["totals"][i8]) for s in body["series"]}
    assert series["Groceries"] == (-1000, -2000)
    assert series["Income"] == (300000, 300000)
    assert "Uncategorized" not in series  # empty categories omitted


def test_saved_reports_crud_and_run(store, client):
    _seed_two_months(store, client)
    assert client.post("/api/saved-reports", json={
        "name": "X", "type": "nope"}).status_code == 422

    r = client.post("/api/saved-reports", json={
        "name": "Q3 spend", "type": "spending", "params": {"month": "2026-07"}}).json()
    assert r["params"] == {"month": "2026-07"}
    rid = r["id"]
    assert len(client.get("/api/saved-reports").json()) == 1

    out = client.post(f"/api/saved-reports/{rid}/run").json()
    assert out["month"] == "2026-07" and "spend_by_category" in out

    r = client.post("/api/saved-reports", json={"name": "NW", "type": "net_worth"}).json()
    assert client.post(f"/api/saved-reports/{r['id']}/run").json() == []

    assert client.post("/api/saved-reports/9999/run").status_code == 404
    assert client.delete(f"/api/saved-reports/{rid}").json() == {"ok": True}
    assert client.delete(f"/api/saved-reports/{r['id']}").json() == {"ok": True}
    assert client.get("/api/saved-reports").json() == []

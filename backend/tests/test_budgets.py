import datetime as dt

from conftest import make_txn


def test_budget_update_delete(store, client):
    g = store["cats"]["Groceries"]
    b = client.post("/api/budgets", json={
        "category_id": g, "month": "2026-09", "limit_cents": 50000}).json()
    assert b["rollover"] is False

    r = client.put(f"/api/budgets/{b['id']}", json={"limit_cents": 60000, "rollover": True})
    assert r.status_code == 200
    assert r.json()["limit_cents"] == 60000 and r.json()["rollover"] is True

    assert client.put("/api/budgets/9999", json={"limit_cents": 1}).status_code == 404
    assert client.delete(f"/api/budgets/{b['id']}").json() == {"ok": True}
    assert client.delete(f"/api/budgets/{b['id']}").status_code == 404


def test_rollover_carry_and_chain(store, client):
    acct = store["acct"]
    g, d = store["cats"]["Groceries"], store["cats"]["Dining"]
    client.post("/api/budgets", json={
        "category_id": g, "month": "2026-07", "limit_cents": 10000, "rollover": True})
    client.post("/api/budgets", json={
        "category_id": g, "month": "2026-08", "limit_cents": 10000, "rollover": True})
    client.post("/api/budgets", json={
        "category_id": g, "month": "2026-09", "limit_cents": 10000})
    client.post("/api/budgets", json={
        "category_id": d, "month": "2026-08", "limit_cents": 50000})
    client.post("/api/budgets", json={
        "category_id": d, "month": "2026-09", "limit_cents": 50000})
    make_txn(client, acct, g, -1250, "Whole Foods", "2026-08-05")

    sept = {b["category_id"]: b for b in client.get("/api/budgets/2026-09").json()}
    assert sept[g]["rolled_cents"] == 10000 + (10000 - 1250)
    assert sept[g]["effective_cents"] == 10000 + 18750
    assert sept[g]["remaining_cents"] == 28750
    assert sept[d]["rolled_cents"] == 0  # Aug Dining has rollover off


def test_rollover_stops_at_gap(store, client):
    acct = store["acct"]
    g = store["cats"]["Groceries"]
    client.post("/api/budgets", json={
        "category_id": g, "month": "2026-07", "limit_cents": 10000, "rollover": True})
    client.post("/api/budgets", json={
        "category_id": g, "month": "2026-09", "limit_cents": 10000})
    sept = client.get("/api/budgets/2026-09").json()[0]
    assert sept["rolled_cents"] == 0  # no Aug budget breaks the chain


def test_pace_fields_and_over(store, client):
    acct = store["acct"]
    g = store["cats"]["Groceries"]
    client.post("/api/budgets", json={
        "category_id": g, "month": "2026-01", "limit_cents": 50000})
    make_txn(client, acct, g, -60000, "Splurge", "2026-01-10")
    b = client.get("/api/budgets/2026-01").json()[0]
    assert b["pace"] == "over"
    assert b["expected_cents"] == b["effective_cents"]  # past month fully elapsed
    assert b["remaining_cents"] == -10000


def test_detect_monthly_and_idempotent(store, client):
    acct = store["acct"]
    unc = store["cats"]["Uncategorized"]
    for d in ("2026-06-01", "2026-07-01", "2026-08-01"):
        make_txn(client, acct, unc, -1599, "Netflix", d)
    r = client.post("/api/recurring/detect").json()
    assert len(r["created"]) == 1 and r["updated"] == []

    items = client.get("/api/recurring").json()["items"]
    assert len(items) == 1
    assert items[0]["cadence"] == "monthly" and items[0]["amount_cents"] == -1599
    assert items[0]["next_due"] == "2026-09-01"  # last date + median gap (31d)

    r = client.post("/api/recurring/detect").json()
    assert r["created"] == [] and len(r["updated"]) == 1
    assert client.get("/api/recurring").json()["total"] == 1


def test_detect_ignores_irregular_and_transfers(store, client):
    acct = store["acct"]
    unc = store["cats"]["Uncategorized"]
    for d in ("2026-06-01", "2026-06-05", "2026-09-01"):
        make_txn(client, acct, unc, -999, "Random Shop", d)
    r = client.post("/api/transactions", json={
        "account_id": acct, "category_id": unc, "amount_cents": -5000,
        "merchant": "CC pay", "date": "2026-06-01", "transfer_id": "x"})
    assert r.status_code == 200
    r = client.post("/api/transactions", json={
        "account_id": acct, "category_id": unc, "amount_cents": 5000,
        "merchant": "CC pay", "date": "2026-07-01", "transfer_id": "x"})
    assert r.status_code == 200
    r = client.post("/api/transactions", json={
        "account_id": acct, "category_id": unc, "amount_cents": -5000,
        "merchant": "CC pay", "date": "2026-08-01", "transfer_id": "x"})
    assert r.status_code == 200
    assert client.post("/api/recurring/detect").json() == {"created": [], "updated": []}


def test_recurring_list_ordered_by_next_due(store, client):
    client.post("/api/recurring", json={
        "name": "Later", "amount_cents": -100,
        "cadence": "monthly", "next_due": "2026-12-01"})
    client.post("/api/recurring", json={
        "name": "Sooner", "amount_cents": -200,
        "cadence": "monthly", "next_due": "2026-10-01"})
    names = [r["name"] for r in client.get("/api/recurring").json()["items"]]
    assert names == ["Sooner", "Later"]

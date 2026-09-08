from conftest import make_txn


def test_transaction_filters(store, client):
    a0, a1 = store["accts"]
    g, d = store["cats"]["Groceries"], store["cats"]["Dining"]
    make_txn(client, a0, g, -1000, "Whole Foods", "2026-01-05")
    make_txn(client, a0, d, -550, "Starbucks", "2026-02-10")
    make_txn(client, a1, g, -2000, "Kroger", "2026-03-15")

    assert client.get("/api/transactions").json()["total"] == 3
    assert client.get(f"/api/transactions?account_id={a1}").json()["total"] == 1
    assert client.get(f"/api/transactions?category_id={d}").json()["total"] == 1
    body = client.get("/api/transactions?date_from=2026-02-01&date_to=2026-02-28").json()
    assert body["total"] == 1 and body["items"][0]["merchant"] == "Starbucks"
    body = client.get("/api/transactions?q=krog").json()
    assert body["total"] == 1 and body["items"][0]["merchant"] == "Kroger"
    assert client.get("/api/transactions?account_id=abc").status_code == 422
    assert client.get("/api/transactions?date_from=not-a-date").status_code == 422


def test_get_update_delete_transaction(store, client):
    a0 = store["accts"][0]
    g, d = store["cats"]["Groceries"], store["cats"]["Dining"]
    t = make_txn(client, a0, g, -1000, "Whole Foods", "2026-01-05")

    r = client.get(f"/api/transactions/{t['id']}")
    assert r.status_code == 200 and r.json()["merchant"] == "Whole Foods"
    assert client.get("/api/transactions/9999").status_code == 404

    r = client.patch(f"/api/transactions/{t['id']}", json={"note": "weekly shop"})
    assert r.status_code == 200 and r.json()["note"] == "weekly shop"
    assert r.json()["category_source"] is None

    r = client.patch(f"/api/transactions/{t['id']}", json={"category_id": d})
    assert r.status_code == 200
    assert r.json()["category_id"] == d and r.json()["category_source"] == "manual"

    assert client.patch("/api/transactions/9999", json={"note": "x"}).status_code == 404
    assert client.delete(f"/api/transactions/{t['id']}").json() == {"ok": True}
    assert client.get(f"/api/transactions/{t['id']}").status_code == 404


def test_transaction_rejects_unknown_account_and_category(store, client):
    a0 = store["accts"][0]
    g = store["cats"]["Groceries"]
    base = {"account_id": a0, "category_id": g, "amount_cents": -100,
            "merchant": "X", "date": "2026-01-05"}
    assert client.post("/api/transactions",
                       json={**base, "account_id": 9999}).status_code == 404
    assert client.post("/api/transactions",
                       json={**base, "category_id": 9999}).status_code == 404
    body = {**base, "category_id": None}
    assert client.post("/api/transactions", json=body).status_code == 200

    t = make_txn(client, a0, g, -100, "X", "2026-01-05")
    assert client.patch(f"/api/transactions/{t['id']}",
                        json={"account_id": 9999}).status_code == 404
    assert client.patch(f"/api/transactions/{t['id']}",
                        json={"category_id": 9999}).status_code == 404


def test_category_update_delete_moves_children(store, client):
    a0 = store["accts"][0]
    g = store["cats"]["Groceries"]
    unc = store["cats"]["Uncategorized"]
    t = make_txn(client, a0, g, -1000, "Whole Foods", "2026-01-05")

    r = client.put(f"/api/categories/{g}", json={"name": "Food"})
    assert r.status_code == 200 and r.json()["name"] == "Food"

    r = client.delete(f"/api/categories/{g}").json()
    assert r == {"ok": True, "moved_transactions": 1, "moved_rules": 0}
    body = client.get(f"/api/transactions/{t['id']}").json()
    assert body["category_id"] == unc and body["category_source"] is None

    assert client.delete(f"/api/categories/{unc}").status_code == 400
    assert client.delete("/api/categories/9999").status_code == 404


def test_rules_crud_and_import_application(store, client):
    g = store["cats"]["Groceries"]
    a0 = store["accts"][0]

    assert client.post("/api/rules", json={
        "pattern": "(unclosed", "category_id": g}).status_code == 422
    assert client.post("/api/rules", json={
        "pattern": "x", "category_id": 9999}).status_code == 404

    r = client.post("/api/rules", json={"pattern": "farmers market", "category_id": g, "priority": 5})
    assert r.status_code == 200
    rid = r.json()["id"]

    r = client.patch(f"/api/rules/{rid}", json={"priority": 1})
    assert r.status_code == 200 and r.json()["priority"] == 1
    assert client.patch("/api/rules/9999", json={"priority": 2}).status_code == 404

    raw = b"date,merchant,amount\n2026-04-01,Sunday Farmers Market,-2200\n"
    assert client.post(f"/api/import/csv?account_id={a0}",
                       files={"file": ("m.csv", raw, "text/csv")}).json() == {
                           "batch_id": 1, "staged": 1, "skipped": 0,
                           "accounts": ["Checking"], "new_categories": []}
    assert client.post("/api/import/batches/1/merge-all").json() == {"ok": True, "merged": 1}
    body = client.get("/api/transactions?q=farmers").json()
    assert body["total"] == 1
    assert body["items"][0]["category_id"] == g
    assert body["items"][0]["category_source"] == "rule"

    assert client.delete(f"/api/rules/{rid}").json() == {"ok": True}
    assert client.get("/api/rules").json() == []


def test_transfer_suggestions_and_link(store, client):
    a0, a1 = store["accts"]
    g = store["cats"]["Groceries"]
    out = make_txn(client, a0, g, -5000, "CC payment", "2026-05-01")
    inn = make_txn(client, a1, g, 5000, "CC payment", "2026-05-02")
    make_txn(client, a0, g, -700, "Starbucks", "2026-05-03")

    sugg = client.get("/api/transfers/suggestions").json()
    assert len(sugg) == 1
    assert sugg[0]["out_id"] == out["id"] and sugg[0]["in_id"] == inn["id"]

    client.post(f"/api/transfers/link?out_id={out['id']}&in_id={inn['id']}&transfer_id=x1")
    assert client.get("/api/transfers/suggestions").json() == []


def test_transfer_suggestions_ignores_same_account_and_window(store, client):
    a0, a1 = store["accts"]
    g = store["cats"]["Groceries"]
    make_txn(client, a0, g, -5000, "A", "2026-05-01")
    make_txn(client, a0, g, 5000, "B", "2026-05-02")  # same account: no match
    make_txn(client, a1, g, 900, "C", "2026-01-01")
    make_txn(client, a0, g, -900, "D", "2026-06-01")  # outside window: no match
    assert client.get("/api/transfers/suggestions").json() == []

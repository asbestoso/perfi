"""Spending vs investing separation: domain-scoped spend, cash-side net worth."""
from conftest import make_txn


def _investing_account(client):
    r = client.post("/api/accounts", json={
        "name": "Brokerage", "type": "brokerage", "domain": "investing",
        "balance_cents": 500000})
    assert r.status_code == 200
    return r.json()["id"]


def test_investment_txns_excluded_from_spend(store, client):
    g = store["cats"]["Groceries"]
    inv = _investing_account(client)
    make_txn(client, store["acct"], g, -1000, "Whole Foods", "2026-08-05")
    r = client.post("/api/transactions", json={
        "account_id": inv, "category_id": g, "amount_cents": -50000,
        "merchant": "VTI buy", "date": "2026-08-06",
        "transaction_kind": "investment_contribution"})
    assert r.status_code == 200

    spend = client.get(
        "/api/transactions?date_from=2026-08-01&date_to=2026-08-31").json()["items"]
    assert [(s["merchant"], s["amount_cents"]) for s in spend
            if s["transaction_kind"] in ("expense", "income")] == [
        ("Whole Foods", -1000)]

    default = client.get(
        "/api/transactions?date_from=2026-08-01&date_to=2026-08-31").json()["items"]
    assert {s["merchant"] for s in default} == {"Whole Foods", "VTI buy"}


def test_investment_txns_excluded_from_spending_view(store, client):
    g = store["cats"]["Groceries"]
    inv = _investing_account(client)
    make_txn(client, store["acct"], g, -1000, "Whole Foods", "2026-08-05")
    r = client.post("/api/transactions", json={
        "account_id": inv, "category_id": g, "amount_cents": -40000,
        "merchant": "VTI buy", "date": "2026-08-06",
        "transaction_kind": "investment_contribution"})
    assert r.status_code == 200

    spend = client.get(
        "/api/transactions?date_from=2026-08-01&date_to=2026-08-31"
        "&domain=spending").json()["items"]
    assert [(s["merchant"], s["amount_cents"]) for s in spend] == [
        ("Whole Foods", -1000)]

    kind = client.get(
        "/api/transactions?date_from=2026-08-01&date_to=2026-08-31"
        "&transaction_kind=expense").json()["items"]
    assert [(s["merchant"], s["amount_cents"]) for s in kind] == [
        ("Whole Foods", -1000)]


def test_net_worth_cash_excludes_investing_balances(store, client):
    inv = _investing_account(client)
    assert client.post("/api/investments", json={
        "symbol": "VTI", "account_id": inv, "quantity_milli": 10000,
        "price_cents": 10000,
    }).status_code == 200
    accts = {a["name"]: a for a in client.get("/api/accounts").json()["items"]}
    assert accts["Brokerage"]["domain"] == "investing"
    # balance is derived from holdings (live-priced), not the raw cash balance
    assert accts["Brokerage"]["balance_cents"] != 500000


def test_report_domain_param(store, client):
    g = store["cats"]["Groceries"]
    inv = _investing_account(client)
    make_txn(client, store["acct"], g, -1000, "Whole Foods", "2026-08-05")
    for merchant, cents, kind in (("VTI buy", -50000, "investment_contribution"),
                                  ("Advisory fee", -2000, "expense")):
        r = client.post("/api/transactions", json={
            "account_id": inv, "category_id": g, "amount_cents": cents,
            "merchant": merchant, "date": "2026-08-06",
            "transaction_kind": kind})
        assert r.status_code == 200

    base = "/api/transactions?date_from=2026-08-01&date_to=2026-08-31"
    default = client.get(base).json()["items"]
    assert {(s["merchant"], s["amount_cents"]) for s in default} == {
        ("Whole Foods", -1000), ("VTI buy", -50000), ("Advisory fee", -2000)}
    only_inv = client.get(base + "&domain=investing").json()["items"]
    assert {(s["merchant"], s["amount_cents"]) for s in only_inv} == {
        ("VTI buy", -50000), ("Advisory fee", -2000)}
    kinds = client.get(base + "&transaction_kind=expense").json()["items"]
    assert {(s["merchant"], s["amount_cents"]) for s in kinds} == {
        ("Whole Foods", -1000), ("Advisory fee", -2000)}
    assert client.get(base + "&domain=nope").status_code == 422


def test_order_cash_link_excludes_leg_from_spend(store, client):
    g = store["cats"]["Groceries"]
    inv = client.post("/api/accounts", json={
        "name": "Brokerage", "type": "brokerage", "domain": "investing",
    }).json()["id"]
    cash_leg = make_txn(client, store["acct"], g, -100000,
                        "Schwab transfer", "2026-08-04")
    order = client.post("/api/investment-orders", json={
        "account_id": inv, "symbol": "VTI", "side": "buy",
        "quantity_milli": 1000, "price_cents": 90000, "fees_cents": 0,
        "executed_at": "2026-08-04", "linked_transaction_id": cash_leg["id"],
    })
    assert order.status_code == 200
    assert order.json()["linked_transaction_id"] == cash_leg["id"]
    leg = client.get(f"/api/transactions/{cash_leg['id']}").json()
    assert leg["transfer_id"] == f"order:{order.json()['id']}"

    again = client.post("/api/investment-orders", json={
        "account_id": inv, "symbol": "VTI", "side": "buy",
        "quantity_milli": 1000, "price_cents": 90000, "fees_cents": 0,
        "executed_at": "2026-08-05", "linked_transaction_id": cash_leg["id"],
    })
    assert again.status_code == 422
    missing = client.post("/api/investment-orders", json={
        "account_id": inv, "symbol": "VTI", "side": "buy",
        "quantity_milli": 1000, "price_cents": 90000, "fees_cents": 0,
        "executed_at": "2026-08-05", "linked_transaction_id": 9999,
    })
    assert missing.status_code == 404


def test_account_type_can_be_updated(store, client):
    aid = store["acct"]
    r = client.patch(f"/api/accounts/{aid}", json={"type": "brokerage"})
    assert r.status_code == 200
    assert r.json()["type"] == "brokerage"
    assert r.json()["domain"] == "spending"  # type change does not move groups


def test_domain_and_kind_validation(store, client):
    assert client.post("/api/accounts", json={
        "name": "Bad", "domain": "nope"}).status_code == 422
    assert client.post("/api/transactions", json={
        "account_id": store["acct"], "amount_cents": 1,
        "merchant": "x", "date": "2026-08-01",
        "transaction_kind": "nope"}).status_code == 422
    good = make_txn(client, store["acct"], store["cats"]["Groceries"],
                    -100, "x", "2026-08-01")
    assert client.patch(f"/api/transactions/{good['id']}", json={
        "transaction_kind": "nope"}).status_code == 422

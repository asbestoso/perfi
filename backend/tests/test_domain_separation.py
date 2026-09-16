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

    spend = client.get("/api/reports/2026-08").json()["spend_by_category"]
    assert spend == [{"category_id": g, "total_cents": -1000}]

    body = client.get("/api/reports-trends?months=60").json()
    by_month = {m["month"]: m for m in body}
    assert by_month["2026-08"]["expense_cents"] == 1000

    cat = client.get("/api/reports-category-trends?months=60").json()
    i8 = cat["months"].index("2026-08")
    series = {s["category"]: s["totals"][i8] for s in cat["series"]}
    assert series["Groceries"] == -1000


def test_investment_txns_excluded_from_budgets_and_recurring(store, client):
    g = store["cats"]["Groceries"]
    unc = store["cats"]["Uncategorized"]
    inv = _investing_account(client)
    client.post("/api/budgets", json={
        "category_id": g, "month": "2026-08", "limit_cents": 50000})
    make_txn(client, store["acct"], g, -1000, "Whole Foods", "2026-08-05")
    r = client.post("/api/transactions", json={
        "account_id": inv, "category_id": g, "amount_cents": -40000,
        "merchant": "VTI buy", "date": "2026-08-06",
        "transaction_kind": "investment_contribution"})
    assert r.status_code == 200
    b = client.get("/api/budgets/2026-08").json()[0]
    assert b["spent_cents"] == 1000

    for d in ("2026-06-01", "2026-07-01", "2026-08-01"):
        r = client.post("/api/transactions", json={
            "account_id": inv, "category_id": unc, "amount_cents": -999,
            "merchant": "Auto Invest", "date": d,
            "transaction_kind": "investment_contribution"})
        assert r.status_code == 200
    assert client.post("/api/recurring/detect").json() == {"created": [], "updated": []}


def test_net_worth_cash_excludes_investing_balances(store, client):
    inv = _investing_account(client)
    assert client.post("/api/investments", json={
        "symbol": "VTI", "account_id": inv, "quantity_milli": 10000,
        "price_cents": 10000,
    }).status_code == 200
    net = client.get("/api/reports/2026-08").json()["net_worth"]
    assert net["cash_cents"] == 0  # brokerage balance is not cash
    assert net["net_worth_cents"] == net["cash_cents"] + net["investments_cents"]
    snap = client.post("/api/snapshots/run").json()
    assert snap["cash_cents"] == 0
    assert snap["net_worth_cents"] == snap["investments_cents"]


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

    default = client.get("/api/reports/2026-08").json()["spend_by_category"]
    assert default == [{"category_id": g, "total_cents": -1000}]
    everything = client.get("/api/reports/2026-08?domain=all").json()["spend_by_category"]
    # domain=all widens the account axis; capital-flow kinds stay out of spend.
    assert {s["category_id"]: s["total_cents"] for s in everything}[g] == -3000
    only_inv = client.get("/api/reports/2026-08?domain=investing").json()["spend_by_category"]
    assert only_inv == [{"category_id": g, "total_cents": -2000}]
    assert client.get("/api/reports/2026-08?domain=nope").status_code == 422
    assert client.get("/api/reports-trends?domain=nope").status_code == 422

    r = client.post("/api/saved-reports", json={
        "name": "All", "type": "spending",
        "params": {"month": "2026-08", "domain": "all"}}).json()
    out = client.post(f"/api/saved-reports/{r['id']}/run").json()
    assert {s["category_id"]: s["total_cents"]
            for s in out["spend_by_category"]}[g] == -3000


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
    spend = client.get("/api/reports/2026-08").json()["spend_by_category"]
    assert spend == []  # linked leg rides as a transfer, not spend

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

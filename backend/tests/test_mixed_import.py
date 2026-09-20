"""Mixed-file import: header scan, mapping, kinds, trades, funded buys."""
from conftest import ROBINHOOD_ACTIVITY_CSV as ROBINHOOD_CSV


def _scan(client, body, name="activity.csv"):
    return client.post("/api/import/scan",
                       files={"file": (name, body, "text/csv")})


def test_scan_detects_robinhood_layout(store, client):
    r = _scan(client, ROBINHOOD_CSV)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["detected_source"] == "robinhood"
    assert body["detection_confidence"] == "high"
    assert body["suggested_file_kind"] == "brokerage"
    mapping = body["mapping"]
    assert mapping["date"] == "Activity Date"
    assert mapping["symbol"] == "Instrument"
    assert mapping["type"] == "Trans Code"
    assert mapping["amount"] == "Amount"
    assert body["has_date"] and body["has_money"]
    assert len(body["signature"]) == 16
    assert len(body["samples"]) == 3
    assert body["samples"][0]["rendered"]["amount"] == "$0.83"


CASH_CODES_CSV = ("Activity Date,Description,Amount,Trans Code,Instrument,Quantity,Price\n"
                  "01/05/2026,Deposit,5000.00,ACH,,\n"
                  "01/06/2026,Withdrawal,-100.00,ACH,,\n"
                  "01/07/2026,Dividend fee,-2.00,DFEE,VTI,,\n")


def _upload_codes(client, file_kind, name="codes.csv"):
    return _upload_mapped(client, CASH_CODES_CSV, {
        "date": "Activity Date", "merchant": "Description", "amount": "Amount",
        "type": "Trans Code", "symbol": "Instrument", "quantity": "Quantity",
        "price": "Price", "account": None, "category": None, "note": None,
    }, file_kind=file_kind, name=name)


def test_transfer_and_fee_codes_stage_as_brokerage_cash(store, client):
    for kind, expected in (("brokerage", {"brokerage_cash": 3}),
                           ("mixed", {"brokerage_cash": 3})):
        r = _upload_codes(client, kind, name=f"{kind}.csv")
        assert r.status_code == 200, r.text
        assert r.json()["by_kind"] == expected
    rows = client.get("/api/import/batches/1/rows?kind=brokerage_cash").json()["items"]
    kinds = {t["merchant"]: t["transaction_kind"] for t in rows}
    assert kinds == {"Deposit": "income", "Withdrawal": "expense",
                     "Dividend fee": "expense"}


def test_transfer_codes_stay_spend_in_spending_files(store, client):
    r = _upload_codes(client, "spending", name="spend.csv")
    assert r.status_code == 200, r.text
    assert r.json()["by_kind"] == {"spend": 3}


def test_scan_defaults_to_suggested_kind(store, client):
    r = _scan(client, ROBINHOOD_CSV)
    assert r.status_code == 200, r.text
    assert r.json()["file_kind"] == "brokerage"
    assert r.json()["counts"] == {"brokerage_cash": 3}


def test_scan_counts_preview_by_kind(store, client):
    import json
    r = client.post("/api/import/scan?file_kind=brokerage",
                    files={"file": ("a.csv", ROBINHOOD_CSV, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["counts"] == {"brokerage_cash": 3}
    assert r.json()["skipped"] == 0
    custom = dict(ROBINHOOD_MAPPING)
    custom["amount"] = None
    custom["price"] = None
    custom["quantity"] = None
    r = client.post("/api/import/scan?file_kind=brokerage",
                    params={"mapping": json.dumps(custom)},
                    files={"file": ("a.csv", ROBINHOOD_CSV, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["has_money"] is False


def test_scan_rejects_unknown_layout(store, client):
    r = _scan(client, "foo,bar,baz\n1,2,3\n")
    assert r.status_code == 422


def test_scan_bank_layout_suggests_mixed(store, client):
    body = ("Date,Description,Amount,Category,Account\n"
            "01/05/2026,Whole Foods,-12.34,Groceries,Checking\n")
    r = _scan(client, body)
    assert r.status_code == 200, r.text
    assert r.json()["suggested_file_kind"] == "mixed"
    assert r.json()["mapping"]["merchant"] == "Description"


ROBINHOOD_MAPPING = {
    "date": "Activity Date", "merchant": "Description", "amount": "Amount",
    "type": "Trans Code", "symbol": "Instrument", "quantity": "Quantity",
    "price": "Price", "account": None, "category": None, "note": None,
}


def _upload_mapped(client, body, mapping, file_kind="brokerage", name="a.csv"):
    import json
    return client.post(
        "/api/import/csv",
        params={"profile": "empower", "file_kind": file_kind,
                "mapping": json.dumps(mapping)},
        files={"file": (name, body, "text/csv")})


def test_robinhood_cash_rows_stage_outside_spend(store, client):
    mapping = dict(ROBINHOOD_MAPPING, account=None)
    r = _upload_mapped(client, ROBINHOOD_CSV, mapping)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file_kind"] == "brokerage"
    assert body["by_kind"] == {"brokerage_cash": 3}
    rows = client.get(
        f"/api/import/batches/{body['batch_id']}/rows?kind=brokerage_cash").json()
    assert rows["total"] == 3
    assert {t["transaction_kind"] for t in rows["items"]} == {"investment_distribution"}

    merged = client.post(f"/api/import/batches/{body['batch_id']}/merge-all").json()
    assert merged == {"ok": True, "merged": 3}
    spend = client.get("/api/reports/2023-12").json()["spend_by_category"]
    assert spend == []
    assert client.post("/api/import/batches/1/merge-all").json() == {
        "ok": True, "merged": 0}


def test_new_brokerage_accounts_join_investing_group(store, client):
    r = _upload_mapped(client, ROBINHOOD_CSV, ROBINHOOD_MAPPING,
                       name="fresh.csv")
    assert r.status_code == 200, r.text
    names = {a["name"]: a for a in client.get("/api/accounts?limit=500").json()["items"]}
    assert names["Default"]["domain"] == "investing"
    assert names["Default"]["type"] == "brokerage"


def test_mixed_file_routes_each_row(store, client):
    body = ("Activity Date,Description,Amount,Trans Code,Instrument,Quantity,Price\n"
            "01/05/2026,Whole Foods,-12.34,,,\n"
            "12/27/2023,Cash Div,$47.08,CDIV,VTI,,\n")
    scan = _scan(client, body).json()
    r = _upload_mapped(client, body, {
        "date": "Activity Date", "merchant": "Description", "amount": "Amount",
        "type": "Trans Code", "symbol": "Instrument", "quantity": "Quantity",
        "price": "Price", "account": None, "category": None, "note": None,
    }, file_kind="mixed")
    assert r.status_code == 200, r.text
    assert r.json()["by_kind"] == {"spend": 1, "brokerage_cash": 1}
    assert scan["mapping"]["type"] == "Trans Code"


def test_trade_rows_never_merge_as_transactions(store, client):
    body = ("Activity Date,Description,Amount,Trans Code,Instrument,Quantity,Price\n"
            "01/05/2026,Buy VTI,-100.00,BUY,VTI,1,100.00\n")
    r = _upload_mapped(client, body, {
        "date": "Activity Date", "merchant": "Description", "amount": "Amount",
        "type": "Trans Code", "symbol": "Instrument", "quantity": "Quantity",
        "price": "Price", "account": None, "category": None, "note": None,
    }, file_kind="brokerage")
    assert r.status_code == 200, r.text
    assert r.json()["by_kind"] == {"trade": 1}
    bid = r.json()["batch_id"]
    rows = client.get(f"/api/import/batches/{bid}/rows?kind=trade").json()
    assert rows["total"] == 1
    assert rows["items"][0]["row_detail"] == "suggested buy"
    assert client.post(f"/api/import/batches/{bid}/merge-all").json() == {
        "ok": True, "merged": 0}
    sid = rows["items"][0]["id"]
    assert client.post(
        f"/api/import/batches/{bid}/resolve?staging_id={sid}&action=merge").status_code == 409
    assert client.get("/api/transactions?limit=1").json()["total"] == 0


TRADE_CSV = ("Activity Date,Description,Amount,Trans Code,Instrument,Quantity,Price\n"
             "01/05/2026,Buy 10 VTI,-1000.00,BUY,VTI,10,100.00\n")

TRADE_MAPPING = {
    "date": "Activity Date", "merchant": "Description", "amount": "Amount",
    "type": "Trans Code", "symbol": "Instrument", "quantity": "Quantity",
    "price": "Price", "account": None, "category": None, "note": None,
}


def test_approve_trade_creates_order_once(store, client):
    r = _upload_mapped(client, TRADE_CSV, TRADE_MAPPING, name="trades.csv")
    assert r.status_code == 200, r.text
    bid = r.json()["batch_id"]
    rows = client.get(f"/api/import/batches/{bid}/rows?kind=trade").json()
    assert rows["total"] == 1
    trade = rows["items"][0]["trade_json"]
    assert trade == {"symbol": "VTI", "quantity_milli": 10000,
                     "price_cents": 10000, "side": "buy"}
    sid = rows["items"][0]["id"]

    first = client.post(
        f"/api/import/batches/{bid}/approve-trade?staging_id={sid}").json()
    assert first["ok"] and first["created"] is True
    assert first["funded_transaction_id"] is None
    assert client.get("/api/transactions?limit=1").json()["total"] == 0
    orders = client.get("/api/investment-orders").json()
    assert orders["total"] == 1
    assert orders["items"][0]["price_cents"] == 10000
    holdings = client.get("/api/investments").json()["holdings"]
    assert len(holdings) == 1 and holdings[0]["quantity_milli"] == 10000

    again = client.post(
        f"/api/import/batches/{bid}/approve-trade?staging_id={sid}")
    assert again.status_code == 409  # row already merged

    # Re-uploading the same file must not double-create the order.
    r2 = _upload_mapped(client, TRADE_CSV, TRADE_MAPPING, name="trades.csv")
    assert r2.status_code == 200, r2.text
    bid2 = r2.json()["batch_id"]
    dupe = client.get(f"/api/import/batches/{bid2}/rows").json()["items"][0]
    assert dupe["status"] == "duplicate" and dupe["row_kind"] == "trade"
    second = client.post(
        f"/api/import/batches/{bid2}/approve-trade?staging_id={dupe['id']}").json()
    assert second["order_id"] == first["order_id"] and second["created"] is False
    orders = client.get("/api/investment-orders").json()
    assert orders["total"] == 1


def test_rollback_trade_batch_reverses_order_and_holding(store, client):
    r = _upload_mapped(client, TRADE_CSV, TRADE_MAPPING, name="rollback-trades.csv")
    bid = r.json()["batch_id"]
    sid = client.get(f"/api/import/batches/{bid}/rows?kind=trade").json()["items"][0]["id"]
    approved = client.post(
        f"/api/import/batches/{bid}/approve-trade?staging_id={sid}").json()
    assert approved["created"] is True
    assert client.get("/api/investment-orders").json()["total"] == 1
    assert client.post(f"/api/import/batches/{bid}/rollback").json() == {
        "ok": True, "batch_id": bid, "transactions": 0,
        "investment_orders": 1,
    }
    assert client.get("/api/investment-orders").json()["total"] == 0
    assert client.get("/api/investments").json()["holdings"] == []


def test_approve_trade_guards(store, client):
    r = _upload_mapped(client, TRADE_CSV, TRADE_MAPPING, name="guards.csv")
    bid, sid = r.json()["batch_id"], client.get(
        f"/api/import/batches/{r.json()['batch_id']}/rows?kind=trade").json()["items"][0]["id"]
    assert client.post(
        f"/api/import/batches/{bid}/approve-trade?staging_id={sid}&side=hold").status_code == 422
    spend_bid = client.post(
        "/api/import/csv?profile=generic",
        files={"file": ("s.csv", b"date,merchant,amount\n2026-01-05,A,-100\n",
                        "text/csv")}).json()["batch_id"]
    spend_sid = client.get(f"/api/import/batches/{spend_bid}/rows").json()["items"][0]["id"]
    assert client.post(
        f"/api/import/batches/{spend_bid}/approve-trade?staging_id={spend_sid}").status_code == 422
    assert client.post(
        f"/api/import/batches/{bid}/approve-trade?staging_id=9999").status_code == 404


def _deposit(client, acct, cents, date, merchant="Schwab deposit"):
    r = client.post("/api/transactions", json={
        "account_id": acct, "amount_cents": cents,
        "merchant": merchant, "date": date})
    assert r.status_code == 200
    return r.json()


def test_funded_buy_auto_links_exact_match(store, client):
    inv = client.post("/api/accounts", json={
        "name": "Schwab", "type": "brokerage", "domain": "investing",
    }).json()["id"]
    funding = _deposit(client, inv, 100000, "2026-01-03")
    body = ("Activity Date,Description,Amount,Trans Code,Instrument,Quantity,Price,Account\n"
            "01/05/2026,Buy 10 VTI,-1000.00,BUY,VTI,10,100.00,Schwab\n")
    r = _upload_mapped(client, body, dict(TRADE_MAPPING, account="Account"),
                       name="funded.csv")
    assert r.status_code == 200, r.text
    bid = r.json()["batch_id"]
    sid = client.get(f"/api/import/batches/{bid}/rows?kind=trade").json()["items"][0]["id"]
    out = client.post(
        f"/api/import/batches/{bid}/approve-trade?staging_id={sid}").json()
    assert out["funded_transaction_id"] == funding["id"]
    leg = client.get(f"/api/transactions/{funding['id']}").json()
    assert leg["transfer_id"] == f"order:{out['order_id']}:funding"
    assert client.get("/api/funded-buys/suggestions").json() == []

    assert client.delete(
        f"/api/investment-orders/{out['order_id']}/link").json() == {
        "ok": True, "cleared": 1}
    assert client.get(f"/api/transactions/{funding['id']}").json()["transfer_id"] is None


def test_funded_buy_ambiguous_stays_suggestion(store, client):
    inv = client.post("/api/accounts", json={
        "name": "Schwab", "type": "brokerage", "domain": "investing",
    }).json()["id"]
    first = _deposit(client, inv, 100000, "2026-01-02", "Deposit A")
    second = _deposit(client, inv, 100000, "2026-01-03", "Deposit B")
    order = client.post("/api/investment-orders", json={
        "account_id": inv, "symbol": "VTI", "side": "buy",
        "quantity_milli": 10000, "price_cents": 10000,
        "executed_at": "2026-01-05"}).json()
    assert client.post(
        f"/api/investment-orders/{order['id']}/link-funding").status_code == 409
    sugg = client.get("/api/funded-buys/suggestions").json()
    assert len(sugg) == 1 and sugg[0]["order_id"] == order["id"]
    assert {c["id"] for c in sugg[0]["candidates"]} == {first["id"], second["id"]}
    linked = client.post(
        f"/api/investment-orders/{order['id']}/link-funding?transaction_id={first['id']}").json()
    assert linked == {"ok": True, "transaction_id": first["id"]}
    assert client.get("/api/funded-buys/suggestions").json() == []


def test_approve_sell_without_shares_fails_cleanly(store, client):
    body = ("Activity Date,Description,Amount,Trans Code,Instrument,Quantity,Price\n"
            "01/05/2026,Sell 10 VTI,1000.00,SELL,VTI,10,100.00\n")
    r = _upload_mapped(client, body, TRADE_MAPPING, name="sell.csv")
    assert r.status_code == 200, r.text
    bid = r.json()["batch_id"]
    sid = client.get(f"/api/import/batches/{bid}/rows?kind=trade").json()["items"][0]["id"]
    assert client.post(
        f"/api/import/batches/{bid}/approve-trade?staging_id={sid}").status_code == 422
    assert client.get("/api/investment-orders").json()["total"] == 0


def test_unknown_code_held_for_review(store, client):
    body = ("Activity Date,Description,Amount,Trans Code,Instrument,Quantity,Price\n"
            "01/05/2026,Weird corporate action,10.00,SPLIT,VTI,,\n")
    r = _upload_mapped(client, body, {
        "date": "Activity Date", "merchant": "Description", "amount": "Amount",
        "type": "Trans Code", "symbol": "Instrument", "quantity": "Quantity",
        "price": "Price", "account": None, "category": None, "note": None,
    }, file_kind="brokerage")
    assert r.status_code == 200, r.text
    assert r.json()["by_kind"] == {"unknown": 1}
    bid = r.json()["batch_id"]
    rows = client.get(f"/api/import/batches/{bid}/rows?kind=unknown").json()
    assert rows["items"][0]["row_detail"] == "unsupported activity code SPLIT"
    assert client.post(f"/api/import/batches/{bid}/merge-all").json() == {
        "ok": True, "merged": 0}

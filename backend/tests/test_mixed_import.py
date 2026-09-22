"""Mixed-file import: header scan, mapping, kinds, review holds."""
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
    spend = client.get(
        "/api/transactions?date_from=2023-12-01&date_to=2023-12-31"
        "&transaction_kind=expense").json()["items"]
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


def test_unsupported_code_rows_never_merge_as_transactions(store, client):
    body = ("Activity Date,Description,Amount,Trans Code,Instrument,Quantity,Price\n"
            "01/05/2026,Buy VTI,-100.00,BUY,VTI,1,100.00\n")
    r = _upload_mapped(client, body, {
        "date": "Activity Date", "merchant": "Description", "amount": "Amount",
        "type": "Trans Code", "symbol": "Instrument", "quantity": "Quantity",
        "price": "Price", "account": None, "category": None, "note": None,
    }, file_kind="brokerage")
    assert r.status_code == 200, r.text
    assert r.json()["by_kind"] == {"unknown": 1}
    bid = r.json()["batch_id"]
    rows = client.get(f"/api/import/batches/{bid}/rows?kind=unknown").json()
    assert rows["total"] == 1
    assert rows["items"][0]["row_detail"] == "unsupported activity code BUY"
    assert client.post(f"/api/import/batches/{bid}/merge-all").json() == {
        "ok": True, "merged": 0}
    sid = rows["items"][0]["id"]
    assert client.post(
        f"/api/import/batches/{bid}/resolve?staging_id={sid}&action=merge").status_code == 409
    assert client.get("/api/transactions?limit=1").json()["total"] == 0


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

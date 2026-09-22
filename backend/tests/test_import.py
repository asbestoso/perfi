import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.services.csv_import import import_csv
from app.services.import_rollback import rollback_batch


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(models.Account(name="Checking", type="checking", balance_cents=0))
    for name in ("Groceries", "Dining", "Uncategorized"):
        session.add(models.Category(name=name))
    session.commit()
    yield session
    session.close()


def test_import_stages_categorized_rows(db):
    raw = b"date,merchant,amount\n2026-01-05,Whole Foods,-12.34\n2026-01-06,Starbucks,-5.50\n"
    result = import_csv(db, 1, raw)
    assert result == {"batch_id": 1, "staged": 2, "skipped": 0,
                      "accounts": ["Checking"], "new_categories": [],
                      "file_kind": "mixed", "by_kind": {"spend": 2}}
    assert db.query(models.Transaction).count() == 0  # nothing merged yet
    rows = db.query(models.StagingRow).order_by(models.StagingRow.id).all()
    names = {c.id: c.name for c in db.query(models.Category).all()}
    assert rows[0].amount_cents == -1234
    assert names[rows[0].category_id] == "Groceries"
    assert rows[0].category_source == "rule"
    assert names[rows[1].category_id] == "Dining"


def test_holding_profile_requires_and_persists_account_mapping(db):
    raw = b"Account,Holding,Quantity\nBrokerage Alpha,VTI,12.5\n"
    with pytest.raises(Exception) as exc:
        import_csv(db, None, raw, profile="Holding")
    assert "account mapping required" in str(exc.value)
    result = import_csv(db, None, raw, profile="Holding",
                        mapping={"accounts": {"Brokerage Alpha": 1}})
    assert result["updated"] == 1
    holding = db.query(models.Holding).one()
    assert holding.account_id == 1 and holding.quantity_milli == 12500
    again = import_csv(db, None, raw, profile="Holding")
    assert again["updated"] == 1
    assert db.query(models.Holding).count() == 1


def test_holding_import_saves_mapping_once_per_label(db):
    raw = (b"Account,Holding,Quantity\n"
           b"Brokerage Alpha,VTI,12.5\n"
           b"Brokerage Alpha,VOO,3\n")
    result = import_csv(db, None, raw, profile="Holding",
                        mapping={"accounts": {"Brokerage Alpha": 1}})
    assert result["updated"] == 2
    assert db.query(models.ImportAccountMapping).count() == 1


def test_holding_scan_returns_external_accounts_and_saved_mapping(store, client):
    client.post("/api/import/csv?profile=Holding&mapping=%7B%22accounts%22%3A%7B%22Brokerage%20Alpha%22%3A1%7D%7D",
                files={"file": ("holdings.csv", b"Account,Holding,Quantity\nBrokerage Alpha,VTI,1\n",
                                "text/csv")})
    response = client.post(
        "/api/import/holdings/scan",
        files={"file": ("holdings.csv",
                         b"Account,Holding,Quantity\nBrokerage Alpha,VTI,1\nBrokerage Beta,VOO,2\n",
                         "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert [item["label"] for item in body["external_accounts"]] == [
        "Brokerage Alpha", "Brokerage Beta"
    ]
    assert body["external_accounts"][0]["saved_account_id"] == 1
    assert body["external_accounts"][1]["saved_account_id"] is None
    assert body["rows"][0]["known"] is True
    assert body["rows"][1]["known"] is False


def test_holding_import_can_skip_accounts_and_rows(db):
    raw = (
        b"Account,Holding,Quantity\n"
        b"Keep,VTI,12.5\n"
        b"Keep,NOTREAL,2\n"
        b"Skip,VOO,4\n"
    )
    db.add(models.Account(name="Skip", type="brokerage", balance_cents=0))
    db.commit()
    result = import_csv(
        db, None, raw, profile="Holding",
        mapping={
            "accounts": {"Keep": 1},
            "excluded_accounts": ["Skip"],
            "excluded_rows": [1],
        },
    )
    assert result["updated"] == 1
    assert result["skipped"] == 2
    assert [(h.symbol, h.quantity_milli) for h in db.query(models.Holding).all()] == [
        ("VTI", 12500)
    ]


def test_holding_batch_reports_committed_changes(store, client):
    response = client.post(
        "/api/import/csv?profile=Holding&mapping=%7B%22accounts%22%3A%7B%22Brokerage%20Alpha%22%3A1%7D%7D",
        files={"file": (
            "holdings.csv",
            b"Account,Holding,Quantity\nBrokerage Alpha,VTI,12.5\n",
            "text/csv",
        )},
    )
    assert response.status_code == 200
    batch_id = response.json()["batch_id"]
    batches = client.get("/api/import/batches").json()["items"]
    batch = next(item for item in batches if item["id"] == batch_id)
    assert batch["committed"] == 1
    detail = client.get(f"/api/import/batches/{batch_id}").json()
    assert detail["committed"] == 1


def test_holding_import_rollback_restores_previous_quantity(db):
    db.add(models.Holding(account_id=1, symbol="VTI", quantity_milli=10000,
                          name="Vanguard Total Stock", price_cents=25000))
    db.commit()
    result = import_csv(
        db, None, b"Account,Holding,Quantity\nBrokerage Alpha,VTI,12.5\n",
        profile="Holding", mapping={"accounts": {"Brokerage Alpha": 1}},
    )
    assert db.query(models.Holding).one().quantity_milli == 12500
    rollback = rollback_batch(db, result["batch_id"])
    assert rollback["holdings"] == 1
    restored = db.query(models.Holding).one()
    assert restored.quantity_milli == 10000
    assert restored.name == "Vanguard Total Stock"
    assert restored.price_cents == 25000


def test_import_holds_duplicates_and_skips_bad_rows(db):
    raw = b"date,merchant,amount\n2026-01-05,Whole Foods,-12.34\n2026-01-05,Whole Foods,-12.34\n,,\n"
    assert import_csv(db, 1, raw) == {"batch_id": 1, "staged": 2, "skipped": 1,
                                      "accounts": ["Checking"], "new_categories": [],
                                      "file_kind": "mixed", "by_kind": {"spend": 2}}
    rows = db.query(models.StagingRow).order_by(models.StagingRow.id).all()
    assert [r.status for r in rows] == ["pending", "duplicate"]
    again = import_csv(db, 1, raw)
    assert again["staged"] == 2 and again["skipped"] == 1
    assert db.query(models.StagingRow).filter_by(status="duplicate").count() == 3


def test_import_accepts_description_column(db):
    raw = b"date,description,amount\n2026-02-01,NETFLIX,-15.99\n"
    assert import_csv(db, 1, raw)["staged"] == 1


def test_generic_profile_imports_category_column(db):
    raw = b"date,merchant,amount,category\n2026-02-01,Local Market,-15.99,Groceries\n"
    assert import_csv(db, 1, raw)["staged"] == 1
    row = db.query(models.StagingRow).one()
    category = db.get(models.Category, row.category_id)
    assert category.name == "Groceries"
    assert row.category_source == "import"


def test_import_creates_missing_categories(db):
    raw = b"date,merchant,amount,category\n2026-02-01,Train,-15.99,Travel\n2026-02-02,Hotel,-80.00,Travel\n"
    result = import_csv(db, 1, raw)
    assert result["new_categories"] == ["Travel"]
    category = db.query(models.Category).filter_by(name="Travel").one()
    rows = db.query(models.StagingRow).order_by(models.StagingRow.id).all()
    assert [row.category_id for row in rows] == [category.id, category.id]
    assert all(row.category_source == "import" for row in rows)


def _upload(client, acct, body, profile="generic", name="s.csv"):
    return client.post(f"/api/import/csv?account_id={acct}&profile={profile}",
                       files={"file": (name, body, "text/csv")})


MINT_CSV = (
    "Date,Description,Original Description,Amount,Transaction Type,Category,Account Name,Labels,Notes\n"
    "01/05/2026,Whole Foods,WHOLEFDS MKT,42.10,debit,Groceries,Checking,,weekly\n"
    "01/06/2026,Payroll,ACME PAY,2000.00,credit,Income,Checking,,\n"
)


def test_mint_profile(store, client):
    acct = store["acct"]
    r = _upload(client, acct, MINT_CSV, profile="mint", name="mint.csv")
    assert r.status_code == 200, r.text
    assert r.json() == {"batch_id": 1, "staged": 2, "skipped": 0,
                        "accounts": ["Checking"], "new_categories": [],
                        "file_kind": "mixed", "by_kind": {"spend": 2}}
    rows = client.get("/api/import/batches/1/rows").json()
    assert rows["total"] == 2
    by_merchant = {t["merchant"]: t for t in rows["items"]}
    assert by_merchant["Whole Foods"]["amount_cents"] == -4210
    assert by_merchant["Whole Foods"]["category_source"] == "import"
    assert by_merchant["Whole Foods"]["category_id"] == store["cats"]["Groceries"]
    assert by_merchant["Whole Foods"]["note"] == "weekly"
    assert by_merchant["Payroll"]["amount_cents"] == 200000


EMPOWER_CSV = (
    "Date,Description,Amount,Type,Category\n"
    "01/05/2026,Shell,45.00,Debit,Transport\n"
    "01/06/2026,Dividend,12.50,Credit,Income\n"
)


def test_empower_positive_only_amounts(store, client):
    acct = store["acct"]
    r = _upload(client, acct, EMPOWER_CSV, profile="empower")
    assert r.json()["staged"] == 2
    rows = client.get("/api/import/batches/1/rows").json()["items"]
    by_merchant = {t["merchant"]: t for t in rows}
    assert by_merchant["Shell"]["amount_cents"] == -4500
    assert by_merchant["Dividend"]["amount_cents"] == 1250


def test_import_guards(store, client):
    acct = store["acct"]
    assert _upload(client, acct, MINT_CSV, profile="nope").status_code == 422
    assert _upload(client, 9999, MINT_CSV, profile="mint").status_code == 404


def test_resolve_merge_discard_merge_all(store, client):
    acct = store["acct"]
    _upload(client, acct, b"date,merchant,amount\n2026-01-05,A,-100\n2026-01-06,B,-200\n")
    rows = client.get("/api/import/batches/1/rows").json()["items"]

    r = client.post(f"/api/import/batches/1/resolve?staging_id={rows[0]['id']}&action=merge")
    assert r.status_code == 200 and "transaction_id" in r.json()
    assert client.get("/api/transactions").json()["total"] == 1

    r = client.post(f"/api/import/batches/1/resolve?staging_id={rows[0]['id']}&action=merge")
    assert r.status_code == 409
    r = client.post(f"/api/import/batches/1/resolve?staging_id={rows[1]['id']}&action=bogus")
    assert r.status_code == 422

    assert client.post(f"/api/import/batches/1/resolve?staging_id={rows[1]['id']}&action=discard").json() == {"ok": True}
    assert client.post("/api/import/batches/1/merge-all").json() == {"ok": True, "merged": 0}
    assert client.get("/api/transactions").json()["total"] == 1

    detail = client.get("/api/import/batches/1").json()
    assert detail["by_status"] == {"merged": 1, "discarded": 1}


def test_reimport_after_merge_holds_duplicate(store, client):
    acct = store["acct"]
    body = b"date,merchant,amount\n2026-01-05,A,-100\n"
    _upload(client, acct, body)
    client.post("/api/import/batches/1/merge-all")
    r = _upload(client, acct, body)
    assert r.json() == {"batch_id": 2, "staged": 1, "skipped": 0,
                        "accounts": ["Checking"], "new_categories": [],
                        "file_kind": "mixed", "by_kind": {"spend": 1}}
    rows = client.get("/api/import/batches/2/rows").json()
    assert rows["total"] == 1 and rows["items"][0]["status"] == "duplicate"
    # merge-all leaves held duplicates alone; nothing double-posts
    assert client.post("/api/import/batches/2/merge-all").json() == {"ok": True, "merged": 0}
    assert client.get("/api/transactions").json()["total"] == 1


def test_import_batch_can_be_rolled_back(store, client):
    acct = store["acct"]
    body = b"date,merchant,amount\n2026-01-05,A,-100\n"
    result = _upload(client, acct, body)
    batch_id = result.json()["batch_id"]
    assert client.post(f"/api/import/batches/{batch_id}/merge-all").json()["merged"] == 1
    assert client.get("/api/transactions").json()["total"] == 1

    rollback = client.post(f"/api/import/batches/{batch_id}/rollback")
    assert rollback.status_code == 200
    assert rollback.json() == {
        "ok": True, "batch_id": batch_id, "transactions": 1,
    }
    assert client.get("/api/transactions").json()["total"] == 0
    assert client.get(f"/api/import/batches/{batch_id}").json()["status"] == "rolled_back"
    assert client.post(f"/api/import/batches/{batch_id}/rollback").status_code == 409


def test_merge_refuses_preexisting_duplicate(store, client):
    acct = store["acct"]
    _upload(client, acct, b"date,merchant,amount\n2026-01-05,A,-100\n")
    rows = client.get("/api/import/batches/1/rows").json()["items"]
    # same charge posted outside the import flow (manual entry)
    # NOTE: CSV "-100" means -$100, i.e. -10000 cents
    r = client.post("/api/transactions", json={
        "account_id": acct, "category_id": None, "amount_cents": -10000,
        "merchant": "A", "date": "2026-01-05"})
    assert r.status_code == 200
    r = client.post(f"/api/import/batches/1/resolve?staging_id={rows[0]['id']}&action=merge")
    assert r.status_code == 409
    assert client.post("/api/import/batches/1/merge-all").json() == {"ok": True, "merged": 0}
    assert client.get("/api/transactions").json()["total"] == 1


def test_same_charge_on_two_accounts_stages_twice(store, client):
    body = ("date,merchant,amount,account\n"
            "2026-01-05,A,-100,Checking\n"
            "2026-01-05,A,-100,Card\n")
    r = client.post("/api/import/csv?profile=generic",
                    files={"file": ("s.csv", body, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["staged"] == 2 and r.json()["skipped"] == 0


def test_accounts_mapped_by_name_and_created(store, client):
    body = ("Date,Account,Description,Category,Tags,Amount\n"
            "2026-01-05,Savings,Whole Foods,Groceries,,-12.34\n"
            "2026-01-06,Brokerage,Dividend,,,15.00\n")
    r = client.post("/api/import/csv?profile=empower",
                    files={"file": ("m.csv", body, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["accounts"] == ["Brokerage", "Savings"]
    names = sorted(a["name"] for a in client.get("/api/accounts").json()["items"])
    assert "Savings" in names and "Brokerage" in names

    bid = r.json()["batch_id"]
    assert client.post(f"/api/import/batches/{bid}/merge-all").json()["merged"] == 2
    by_acct = {}
    for t in client.get("/api/transactions?limit=100").json()["items"]:
        by_acct.setdefault(t["account_id"], []).append(t["merchant"])
    assert len(by_acct) == 2  # rows landed on two different accounts


def test_account_override_forces_single_account(store, client):
    acct = store["acct"]
    body = ("Date,Account,Description,Category,Tags,Amount\n"
            "2026-01-05,Savings,Whole Foods,Groceries,,-12.34\n")
    r = client.post(f"/api/import/csv?account_id={acct}&profile=empower",
                    files={"file": ("m.csv", body, "text/csv")}).json()
    assert r["accounts"] == ["Checking"]
    assert "Savings" not in [a["name"] for a in client.get("/api/accounts").json()["items"]]


def test_csv_export(store, client):
    acct = store["acct"]
    _upload(client, acct, b"date,merchant,amount\n2026-01-05,Whole Foods,-12.34\n")
    client.post("/api/import/batches/1/merge-all")
    r = client.get(f"/api/export/transactions?account_id={acct}")
    assert r.status_code == 200
    lines = r.text.strip().splitlines()
    assert lines[0] == "date,merchant,amount,category,note"
    assert lines[1].startswith("2026-01-05,Whole Foods,-12.34,Groceries,")


def _fixture_bytes():
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "monarch_ground_truth.csv")
    with open(path, "rb") as f:
        return f.read()


def test_monarch_ground_truth_end_to_end(store, client):
    import time
    acct = store["acct"]
    raw = _fixture_bytes()
    started = time.time()

    # 1. upload exactly like the Import page does
    r = client.post(f"/api/import/csv?account_id={acct}&profile=empower",
                    files={"file": ("test.csv", raw, "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["staged"] + body["skipped"] == 7151
    assert body["staged"] > 6900  # file itself holds ~160 exact-dupe rows

    # 2. review queue (exact dupes are held as duplicate rows, not dropped)
    detail = client.get(f"/api/import/batches/{body['batch_id']}").json()
    assert detail["profile"] == "empower"
    by_status = detail["by_status"]
    assert by_status.get("duplicate", 0) > 0  # file holds ~160 exact-dupe rows
    assert by_status.get("pending", 0) + by_status.get("duplicate", 0) == body["staged"]
    pending = by_status.get("pending", 0)
    rows = client.get(f"/api/import/batches/{body['batch_id']}/rows?status=pending&limit=5").json()
    assert rows["total"] == pending

    # 3. merge pending rows into the ledger (duplicates stay held)
    r = client.post(f"/api/import/batches/{body['batch_id']}/merge-all").json()
    assert r == {"ok": True, "merged": pending}
    assert client.get("/api/transactions?limit=1").json()["total"] == pending

    # 4. spot-check a known ground-truth row end to end
    # (fixture is anonymized: Merchant 0003/0004 are a -/+ pair, ex -162/+162c)
    neg = client.get("/api/transactions?q=Merchant+0003").json()["items"]
    pos = client.get("/api/transactions?q=Merchant+0004").json()["items"]
    assert -242 in [t["amount_cents"] for t in neg]
    assert 242 in [t["amount_cents"] for t in pos]

    # 5. export round-trips every merged row
    lines = client.get(f"/api/export/transactions?account_id={acct}").text.strip().splitlines()
    assert len(lines) == pending + 1

    # 6. re-upload holds everything as duplicates, double-posts nothing
    again = client.post(f"/api/import/csv?account_id={acct}&profile=empower",
                        files={"file": ("test.csv", raw, "text/csv")}).json()
    assert again["batch_id"] == body["batch_id"] + 1
    assert again["staged"] == body["staged"] and again["skipped"] == body["skipped"]
    assert again["accounts"] == ["Checking"]
    assert client.post(f"/api/import/batches/{again['batch_id']}/merge-all").json() == {
        "ok": True, "merged": 0}
    assert client.get("/api/transactions?limit=1").json()["total"] == pending

    elapsed = time.time() - started
    assert elapsed < 120, f"7151-row import took {elapsed:.1f}s"


def test_holding_scan_ignores_saved_mapping_for_deleted_account(store, client):
    client.post("/api/import/csv?profile=Holding&mapping=%7B%22accounts%22%3A%7B%22Ghost%22%3A1%7D%7D",
                files={"file": ("holdings.csv", b"Account,Holding,Quantity\nGhost,VTI,1\n",
                                "text/csv")})
    client.post("/api/admin/clear")
    body = client.post(
        "/api/import/holdings/scan",
        files={"file": ("holdings.csv", b"Account,Holding,Quantity\nGhost,VTI,1\n",
                                "text/csv")},
    ).json()
    assert body["external_accounts"][0]["saved_account_id"] is None

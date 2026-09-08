from conftest import make_txn


def _upload(client, acct, body, profile="generic", name="s.csv"):
    return client.post(f"/api/import/csv?account_id={acct}&profile={profile}",
                       files={"file": (name, body, "text/csv")})


def test_merge_safe_holds_only_obvious_dupes(store, client):
    acct = store["acct"]
    make_txn(client, acct, None, -1234, "Whole Foods", "2026-01-05")
    body = (b"date,merchant,amount\n"
            b"2026-01-05,Whole Foods,-12.34\n"        # exact dupe: skipped at stage time
            b"2026-01-05,Whole Foods Market #12,-12.34\n"  # near-identical: held
            b"2026-01-05,WHOLEFDS MKT #42,-12.34\n"  # reworded, no shared run: safe
            b"2026-01-06,Whole Foods,-12.34\n"       # same merchant, next day: safe
            b"2026-01-06,Starbucks,-5.50\n")         # safe
    assert _upload(client, acct, body).json()["staged"] == 5

    r = client.get("/api/import/batches/1/review")
    assert r.status_code == 200, r.text
    review = r.json()
    assert review["safe"] == 3 and review["needs_review"] == 2
    assert len(review["safe_ids"]) == 3
    held_ids = {h["staging_id"] for h in review["suspects"]}
    assert held_ids.isdisjoint(review["safe_ids"])
    by_status = {h["status"] for h in review["suspects"]}
    assert by_status == {"pending", "duplicate"}
    assert all(h["merchant"] and h["date"] for h in review["suspects"])

    r = client.post("/api/import/batches/1/merge-safe")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["merged"] == 3 and len(out["held"]) == 2
    assert client.get("/api/transactions").json()["total"] == 4

    rows = client.get("/api/import/batches/1/rows?status=pending&limit=100").json()
    assert rows["total"] == 1  # the near-identical suspect stays pending
    dupes = client.get("/api/import/batches/1/rows?status=duplicate&limit=100").json()
    assert dupes["total"] == 1  # the exact dupe stays held, not dropped

    # force-merge the held duplicate (keep both), then it is gone from review
    dupe_id = dupes["items"][0]["id"]
    r = client.post(f"/api/import/batches/1/resolve?staging_id={dupe_id}&action=merge")
    assert r.status_code == 200, r.text
    assert client.get("/api/transactions").json()["total"] == 5
    assert client.get("/api/import/batches/1/review").json()["needs_review"] == 1


def test_merge_safe_holds_in_batch_near_dupes(store, client):
    acct = store["acct"]
    body = (b"date,merchant,amount\n"
            b"2026-01-05,Shell,-45.00\n"
            b"2026-01-05,SHELL OIL 57444,-45.00\n")
    assert _upload(client, acct, body).json()["staged"] == 2
    out = client.post("/api/import/batches/1/merge-safe").json()
    assert out["merged"] == 1 and len(out["held"]) == 1
    assert "another row in this batch" in out["held"][0]["reasons"][0]


def test_merge_safe_leaves_repeats_outside_window_alone(store, client):
    acct = store["acct"]
    make_txn(client, acct, None, -550, "Starbucks", "2026-01-01")
    _upload(client, acct, b"date,merchant,amount\n2026-01-10,Starbucks,-5.50\n")
    review = client.get("/api/import/batches/1/review").json()
    assert review["safe"] == 1 and review["needs_review"] == 0
    assert client.post("/api/import/batches/1/merge-safe").json()["merged"] == 1


def test_merge_all_still_force_merges_held_rows(store, client):
    acct = store["acct"]
    make_txn(client, acct, None, -1234, "Whole Foods", "2026-01-05")
    _upload(client, acct, b"date,merchant,amount\n2026-01-05,Whole Foods Market #12,-12.34\n")
    assert client.get("/api/import/batches/1/review").json()["needs_review"] == 1
    # merge-all only blocks exact dupes; the held row still merges (force path kept)
    assert client.post("/api/import/batches/1/merge-all").json() == {"ok": True, "merged": 1}
    assert client.get("/api/transactions").json()["total"] == 2


def test_fingerprint_identity():
    import datetime as dt
    from app.services.fingerprint import compute_fingerprint, obvious_merchant_match
    d = dt.date(2026, 1, 5)
    base = compute_fingerprint(d, -1234, 1, "Whole Foods")
    assert compute_fingerprint(d, -1234, 1, "  WHOLE  FOODS, ") == base
    assert compute_fingerprint(d, 1234, 1, "Whole Foods") != base  # signed
    assert compute_fingerprint(d, -1234, 2, "Whole Foods") != base  # account
    assert compute_fingerprint(dt.date(2026, 1, 6), -1234, 1, "Whole Foods") != base
    assert compute_fingerprint(d, -1234, 1, "Other") != base
    assert obvious_merchant_match("Shell", "SHELL OIL 57444")
    assert obvious_merchant_match("Whole Foods", "Whole Foods Market #12")
    assert not obvious_merchant_match("WHOLEFDS MKT", "Whole Foods")
    assert not obvious_merchant_match("Starbucks", "Shell")
    assert not obvious_merchant_match("A", "B")


def test_stage_folds_note_into_exact_match(store, client):
    acct = store["acct"]
    make_txn(client, acct, None, -1234, "Whole Foods", "2026-01-05")
    body = b"date,merchant,amount,note\n2026-01-05,Whole Foods,-12.34,weekly shop\n"
    assert _upload(client, acct, body).json() == {
        "batch_id": 1, "staged": 1, "skipped": 0, "accounts": ["Checking"],
        "new_categories": []}
    txns = client.get("/api/transactions").json()["items"]
    assert txns[0]["note"] == "weekly shop"


def test_review_404(store, client):
    assert client.get("/api/import/batches/999/review").status_code == 404
    assert client.post("/api/import/batches/999/merge-safe").status_code == 404


def test_review_and_merge_safe_scale(store, client):
    import time
    acct = store["acct"]
    lines = ["date,merchant,amount"]
    for i in range(2000):
        lines.append(f"2026-03-{(i % 28) + 1:02d},Shop {i:05d},{-(i % 500) - 1}.00")
    body = ("\n".join(lines) + "\n").encode()
    started = time.time()
    out = client.post(f"/api/import/csv?account_id={acct}&profile=generic",
                      files={"file": ("big.csv", body, "text/csv")}).json()
    assert out["staged"] == 2000, out
    review = client.get("/api/import/batches/1/review").json()
    assert review["safe"] == 2000 and review["needs_review"] == 0
    assert client.post("/api/import/batches/1/merge-safe").json() == {
        "ok": True, "merged": 2000, "held": []}
    elapsed = time.time() - started
    assert elapsed < 30, f"review+merge-safe on 2k rows took {elapsed:.1f}s"

from conftest import make_txn


def test_clear_wipes_data_and_reseeds(store, client):
    acct = store["acct"]
    make_txn(client, acct, None, -1234, "Whole Foods", "2026-01-05")
    client.post(f"/api/import/csv?account_id={acct}&profile=generic",
                files={"file": ("s.csv", b"date,merchant,amount\n2026-01-06,B,-200\n",
                                "text/csv")})
    assert client.get("/api/transactions").json()["total"] == 1
    assert client.get("/api/import/batches").json()["total"] == 1

    r = client.post("/api/admin/clear")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True
    assert out["deleted"]["transactions"] == 1
    assert out["deleted"]["staging_rows"] == 1
    assert out["deleted"]["import_batches"] == 1

    assert client.get("/api/transactions").json()["total"] == 0
    assert client.get("/api/import/batches").json()["total"] == 0
    assert client.get("/api/accounts").json()["total"] == 0
    names = [c["name"] for c in client.get("/api/categories?limit=100").json()["items"]]
    assert "Uncategorized" in names

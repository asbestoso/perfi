from conftest import make_txn


def test_clear_wipes_data_and_reseeds(store, client):
    acct = store["acct"]
    make_txn(client, acct, None, -1234, "Whole Foods", "2026-01-05")
    client.post(f"/api/import/csv?account_id={acct}&profile=generic",
                files={"file": ("s.csv", b"date,merchant,amount\n2026-01-06,B,-200\n",
                                "text/csv")})
    assert client.get("/api/transactions").json()["total"] == 1
    assert client.get("/api/import/batches").json()["total"] == 1
    client.post("/api/import/csv?profile=Holding&mapping=%7B%22accounts%22%3A%7B%22Brokerage%20Alpha%22%3A"
                + str(acct) + "%7D%7D",
                files={"file": ("holdings.csv", b"Account,Holding,Quantity\nBrokerage Alpha,VTI,1\n",
                                "text/csv")})
    client.patch("/api/investments/classification/VOO", json={"category": "US"})
    client.put("/api/investments/allocation/VTI", json={"allocations": {"US": 100}})

    r = client.post("/api/admin/clear")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True
    assert out["deleted"]["transactions"] == 1
    assert out["deleted"]["staging_rows"] == 1
    assert out["deleted"]["import_batches"] == 2
    assert out["deleted"]["holdings"] == 1
    assert out["deleted"]["import_account_mappings"] == 1
    assert out["deleted"]["investment_classifications"] == 1
    assert out["deleted"]["investment_allocations"] == 1

    assert client.get("/api/transactions").json()["total"] == 0
    assert client.get("/api/import/batches").json()["total"] == 0
    assert client.get("/api/accounts").json()["total"] == 0
    assert client.get("/api/investments").json()["holdings"] == []
    body = client.post(
        "/api/import/holdings/scan",
        files={"file": ("holdings.csv", b"Account,Holding,Quantity\nBrokerage Alpha,VTI,1\n",
                        "text/csv")},
    ).json()
    assert body["external_accounts"][0]["saved_account_id"] is None
    names = [c["name"] for c in client.get("/api/categories?limit=100").json()["items"]]
    assert "Uncategorized" in names

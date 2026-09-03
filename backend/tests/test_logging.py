import logging


def test_request_and_domain_logs(store, client, caplog):
    acct = store["acct"]
    with caplog.at_level(logging.INFO, logger="perfi"):
        client.post(f"/api/import/csv?account_id={acct}&profile=generic",
                    files={"file": ("s.csv", b"date,merchant,amount\n2026-01-05,A,-100\n",
                                     "text/csv")})
    by_logger = {}
    for r in caplog.records:
        by_logger.setdefault(r.name, []).append(r.getMessage())
    assert any("POST /api/import/csv -> 200" in m for m in by_logger.get("perfi.http", []))
    assert any("staged=1 skipped=0" in m for m in by_logger.get("perfi.import", []))

import io
import json
import logging
import urllib.error
import urllib.parse

import pytest

from app import logging_setup
from app.services import market_data


class _FakeQuoteResponse:
    def __init__(self, payload):
        self._buf = io.StringIO(json.dumps(payload))

    def __enter__(self):
        return self._buf

    def __exit__(self, *args):
        return False


def _chart(price):
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price}}]}}


def test_quote_fetch_logs_result_and_batch(monkeypatch, caplog):
    market_data.clear_quote_cache()
    monkeypatch.setattr(
        "app.services.market_data.urllib.request.urlopen",
        lambda request, timeout=8: _FakeQuoteResponse(_chart(378.03)))
    with caplog.at_level(logging.INFO, logger="perfi"):
        assert market_data.get_live_prices(["VTI", "BND"]) == {
            "VTI": 37803, "BND": 37803}
    messages = [rec.getMessage() for rec in caplog.records
                if rec.name == "perfi.quotes"]
    assert any("quote VTI 37803c" in m for m in messages)
    assert any("quotes batch: 2 symbols, 0 failed" in m for m in messages)


def test_quote_failure_logs_warning(monkeypatch, caplog):
    market_data.clear_quote_cache()

    def _boom(request, timeout=8):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(
        "app.services.market_data.urllib.request.urlopen", _boom)
    with caplog.at_level(logging.INFO, logger="perfi"):
        with pytest.raises(market_data.QuoteUnavailableError):
            market_data.get_live_price("VTI")
    assert any("quote VTI failed" in rec.getMessage()
               and rec.levelno == logging.WARNING
               for rec in caplog.records if rec.name == "perfi.quotes")


def test_summary_refresh_logs_counts(store, client, monkeypatch, caplog):
    monkeypatch.setattr("app.api.routes.api.get_live_price", lambda symbol: 25000)
    monkeypatch.setattr("app.api.routes.api.get_live_name", lambda symbol: "VTI Fund")
    r = client.post("/api/investments", json={
        "symbol": "VTI", "account_id": store["acct"], "quantity_milli": 10000})
    assert r.status_code == 200
    with caplog.at_level(logging.INFO, logger="perfi"):
        assert client.get("/api/investments/summary").status_code == 200
    assert any("summary refresh: 1 symbols, 1 priced, 0 failed" in rec.getMessage()
               for rec in caplog.records if rec.name == "perfi.investments")


def test_holding_import_422_logs_detail(store, client, caplog):
    mapping = {"accounts": {"Brokerage Alpha": store["acct"]}}
    raw = (b"Account,Holding,Quantity\n"
           b"Brokerage Alpha,VTI,10\n"
           b"Brokerage Alpha,VTI,10\n")
    query = urllib.parse.quote(json.dumps(mapping))
    with caplog.at_level(logging.WARNING, logger="perfi"):
        r = client.post(f"/api/import/csv?profile=Holding&mapping={query}",
                        files={"file": ("holdings.csv", raw, "text/csv")})
    assert r.status_code == 422
    assert r.json() == {"detail": "duplicate holding row for Brokerage Alpha / VTI"}
    assert any("duplicate holding row for Brokerage Alpha / VTI" in rec.getMessage()
               for rec in caplog.records if rec.name == "perfi.http")


def test_setup_evicts_foreign_root_handlers_but_keeps_ours():
    root = logging.getLogger()
    saved = list(root.handlers)
    foreign = logging.StreamHandler()
    try:
        root.addHandler(foreign)
        logging_setup.setup()
        assert foreign not in root.handlers
        assert any(getattr(handler, "_perfi_owned", False)
                   for handler in root.handlers)
    finally:
        root.handlers[:] = saved


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

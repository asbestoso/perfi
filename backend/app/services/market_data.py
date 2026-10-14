"""Live market-price lookups with a short in-memory TTL cache."""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from ..logging_setup import get as get_log

log = get_log("quotes")

QUOTE_TTL_SECONDS = 15 * 60

_lock = threading.Lock()
_quotes = {}


class QuoteUnavailableError(RuntimeError):
    pass


def yahoo_symbol(symbol):
    symbol = (symbol or "").strip().upper()
    return "BTC-USD" if symbol == "BTC" else symbol


def get_live_name(symbol):
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise QuoteUnavailableError("symbol is required")
    if symbol == "CASH":
        return "Cash"
    yahoo = yahoo_symbol(symbol)
    encoded = urllib.parse.quote(yahoo, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=1d&interval=1m"
    request = urllib.request.Request(url, headers={"User-Agent": "perfi/1.0"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        ms = (time.perf_counter() - started) * 1000
        log.warning(f"name {symbol} failed after {ms:.0f}ms: {exc}")
        raise QuoteUnavailableError(f"could not fetch name for {symbol}") from exc
    ms = (time.perf_counter() - started) * 1000
    meta = ((data.get("chart", {}).get("result") or [None])[0] or {}).get("meta", {})
    name = meta.get("longName") or meta.get("shortName")
    log.info(f"name {symbol} {name!r} ({ms:.0f}ms)")
    return name


def get_live_price(symbol):
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise QuoteUnavailableError("symbol is required")
    if symbol == "CASH":
        log.debug("quote CASH pinned at 100c (no lookup)")
        return 100
    now = time.monotonic()
    with _lock:
        hit = _quotes.get(symbol)
        if hit is not None and now - hit[1] < QUOTE_TTL_SECONDS:
            log.debug(f"quote {symbol} cache hit")
            return hit[0]
    price = _fetch_price(symbol)
    with _lock:
        _quotes[symbol] = (price, time.monotonic())
    return price


def get_live_prices(symbols):
    """Fetch many quotes concurrently; failures map to None, never raise."""
    unique = list(dict.fromkeys(
        (s or "").strip().upper() for s in symbols if (s or "").strip()))
    if not unique:
        return {}
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=min(8, len(unique))) as pool:
        prices = list(pool.map(_safe_price, unique))
    failed = sum(1 for price in prices if price is None)
    ms = (time.perf_counter() - started) * 1000
    log.info(f"quotes batch: {len(unique)} symbols, {failed} failed ({ms:.0f}ms)")
    return dict(zip(unique, prices))


def clear_quote_cache():
    with _lock:
        _quotes.clear()


def _safe_price(symbol):
    try:
        return get_live_price(symbol)
    except QuoteUnavailableError:
        return None


def _fetch_price(symbol):
    yahoo = yahoo_symbol(symbol)
    encoded = urllib.parse.quote(yahoo, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=1d&interval=1m"
    request = urllib.request.Request(url, headers={"User-Agent": "perfi/1.0"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        ms = (time.perf_counter() - started) * 1000
        log.warning(f"quote {symbol} failed after {ms:.0f}ms: {exc}")
        raise QuoteUnavailableError(f"could not fetch quote for {symbol}") from exc
    result = (data.get("chart", {}).get("result") or [None])[0]
    price = result and result.get("meta", {}).get("regularMarketPrice")
    ms = (time.perf_counter() - started) * 1000
    if not isinstance(price, (int, float)) or price <= 0:
        log.warning(f"quote {symbol} failed after {ms:.0f}ms: no regularMarketPrice")
        raise QuoteUnavailableError(f"no live quote available for {symbol}")
    cents = round(price * 100)
    log.info(f"quote {symbol} {cents}c ({ms:.0f}ms)")
    return cents

"""Live market-price lookups with a short in-memory TTL cache."""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

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
    yahoo = yahoo_symbol(symbol)
    encoded = urllib.parse.quote(yahoo, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=1d&interval=1m"
    request = urllib.request.Request(url, headers={"User-Agent": "perfi/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise QuoteUnavailableError(f"could not fetch name for {symbol}") from exc
    meta = ((data.get("chart", {}).get("result") or [None])[0] or {}).get("meta", {})
    return meta.get("longName") or meta.get("shortName")


def get_live_price(symbol):
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise QuoteUnavailableError("symbol is required")
    now = time.monotonic()
    with _lock:
        hit = _quotes.get(symbol)
        if hit is not None and now - hit[1] < QUOTE_TTL_SECONDS:
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
    with ThreadPoolExecutor(max_workers=min(8, len(unique))) as pool:
        prices = list(pool.map(_safe_price, unique))
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
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise QuoteUnavailableError(f"could not fetch quote for {symbol}") from exc
    result = (data.get("chart", {}).get("result") or [None])[0]
    price = result and result.get("meta", {}).get("regularMarketPrice")
    if not isinstance(price, (int, float)) or price <= 0:
        raise QuoteUnavailableError(f"no live quote available for {symbol}")
    return round(price * 100)

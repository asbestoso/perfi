"""Live market-price lookups."""
import json
import urllib.error
import urllib.parse
import urllib.request


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

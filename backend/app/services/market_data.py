"""Live market-price lookups."""
import json
import urllib.error
import urllib.parse
import urllib.request


class QuoteUnavailableError(RuntimeError):
    pass


def get_live_price(symbol):
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise QuoteUnavailableError("symbol is required")
    encoded = urllib.parse.quote(symbol, safe="")
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

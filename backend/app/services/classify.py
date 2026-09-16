"""Row classification for mixed-file import.

Every staged row lands in one destination:

- spend: ordinary cash-ledger activity, merges into transactions.
- brokerage_cash: dividends, interest, deposits into a brokerage account.
  Merges into transactions with a capital-flow kind (never spend).
- trade: a buy or sell. Never merges; approves into an investment order.
- unknown: recognized layout but unrecognized activity (e.g. a Trans Code
  outside CASH_CODES). Held for review, never auto-posted.

The remembered file_kind answer gates the rules: brokerage-only files
skip spend classification entirely, spending-only files divert
trade-shaped rows to review, mixed files run everything.
"""
from .money import to_cents
from .profiles import parse_date

FILE_KINDS = ("mixed", "brokerage", "spending")
ROW_KINDS = ("spend", "brokerage_cash", "trade", "unknown")

#: Robinhood Trans Codes that post brokerage cash, with transaction kind.
CASH_CODES = {
    "CDIV": "investment_distribution",
    "DIV": "investment_distribution",
    "INT": "investment_distribution",
}

BUY_CODES = ("BUY", "B", "BOT", "BOUGHT")
SELL_CODES = ("SELL", "S", "SLD", "SOLD")


def _parse_milli(value):
    try:
        return round(float((value or "").strip().replace(",", "")) * 1000)
    except (ValueError, AttributeError):
        return None


def normalize_mapped(row, mapping):
    """Build a canonical parsed dict from a raw row via a confirmed mapping.

    mapping is {canonical field: file column}. Returns None when the date
    is unparseable. Quantity/price/symbol ride along for trade detection.
    """
    mapping = mapping or {}

    def get(field):
        col = mapping.get(field)
        if not col:
            return ""
        return str((row or {}).get(col) or "").strip()

    date = parse_date(get("date"))
    if date is None:
        return None
    amount_raw = get("amount")
    try:
        amount_cents = to_cents(amount_raw) if amount_raw else 0
    except Exception:
        return None
    quantity_milli = _parse_milli(get("quantity"))
    price_raw = get("price")
    try:
        price_cents = to_cents(price_raw) if price_raw else None
    except Exception:
        price_cents = None
    return {
        "date": date,
        "merchant": get("merchant"),
        "amount_cents": amount_cents,
        "category": get("category"),
        "note": get("note"),
        "account": get("account"),
        "symbol": get("symbol").upper(),
        "quantity_milli": quantity_milli,
        "price_cents": price_cents,
        "code": get("type").upper(),
    }


def _trade_side(parsed):
    if parsed.get("code") in BUY_CODES:
        return "buy"
    if parsed.get("code") in SELL_CODES:
        return "sell"
    desc = (parsed.get("merchant") or "").casefold()
    if desc.startswith("sell"):
        return "sell"
    if desc.startswith("buy"):
        return "buy"
    return "buy"


def is_trade_shaped(parsed):
    return bool(parsed.get("symbol")) and \
        (parsed.get("quantity_milli") or 0) != 0 and \
        (parsed.get("price_cents") or 0) != 0


def classify(parsed, file_kind="mixed"):
    """Return (row_kind, detail dict) for a normalized row.

    detail carries side for trades, transaction_kind for cash rows, and a
    human reason for unknown rows.
    """
    code = (parsed.get("code") or "").upper()
    if code in CASH_CODES:
        return "brokerage_cash", {"transaction_kind": CASH_CODES[code]}
    if is_trade_shaped(parsed):
        if file_kind == "spending":
            return "unknown", {"reason": "trade-shaped row in a spending-only file"}
        return "trade", {"side": _trade_side(parsed)}
    if code and file_kind == "brokerage":
        return "unknown", {"reason": f"unsupported activity code {code}"}
    if file_kind == "brokerage":
        kind = "income" if parsed.get("amount_cents", 0) >= 0 else "expense"
        return "brokerage_cash", {"transaction_kind": kind}
    kind = "income" if parsed.get("amount_cents", 0) > 0 else "expense"
    return "spend", {"transaction_kind": kind}

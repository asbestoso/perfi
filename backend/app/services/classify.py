"""Row classification for mixed-file import.

Every staged row lands in one destination:

- spend: ordinary cash-ledger activity, merges into transactions.
- brokerage_cash: dividends, interest, deposits into a brokerage account.
  Merges into transactions with a capital-flow kind (never spend).
- unknown: recognized layout but unrecognized activity (e.g. a Trans Code
  outside CASH_CODES). Held for review, never auto-posted.

The remembered file_kind answer gates the rules: brokerage-only files
skip spend classification entirely.
"""
from .money import to_cents
from .profiles import parse_date

FILE_KINDS = ("mixed", "brokerage", "spending")
ROW_KINDS = ("spend", "brokerage_cash", "unknown")

#: Robinhood Trans Codes that post brokerage cash, with transaction kind.
#: Codes absent here but known-transfer (ACH) are handled by sign below.
CASH_CODES = {
    "CDIV": "investment_distribution",
    "DIV": "investment_distribution",
    "INT": "investment_distribution",
    "DFEE": "expense",
}

#: Transfer codes: cash in/out of the brokerage, kinded by sign. Only
#: outside spending-only files, where an ACH row is ordinary bank activity.
TRANSFER_CODES = ("ACH",)


def normalize_mapped(row, mapping):
    """Build a canonical parsed dict from a raw row via a confirmed mapping.

    mapping is {canonical field: file column}. Returns None when the date
    is unparseable.
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
    return {
        "date": date,
        "merchant": get("merchant"),
        "amount_cents": amount_cents,
        "category": get("category"),
        "note": get("note"),
        "account": get("account"),
        "code": get("type").upper(),
    }


def classify(parsed, file_kind="mixed"):
    """Return (row_kind, detail dict) for a normalized row.

    detail carries transaction_kind for cash rows and a human reason
    for unknown rows.
    """
    code = (parsed.get("code") or "").upper()
    if file_kind == "spending":
        kind = "income" if parsed.get("amount_cents", 0) > 0 else "expense"
        return "spend", {"transaction_kind": kind}
    if code in CASH_CODES:
        return "brokerage_cash", {"transaction_kind": CASH_CODES[code]}
    if code in TRANSFER_CODES:
        kind = "income" if parsed.get("amount_cents", 0) >= 0 else "expense"
        return "brokerage_cash", {"transaction_kind": kind}
    if code:
        return "unknown", {"reason": f"unsupported activity code {code}"}
    if file_kind == "brokerage":
        kind = "income" if parsed.get("amount_cents", 0) >= 0 else "expense"
        return "brokerage_cash", {"transaction_kind": kind}
    kind = "income" if parsed.get("amount_cents", 0) > 0 else "expense"
    return "spend", {"transaction_kind": kind}

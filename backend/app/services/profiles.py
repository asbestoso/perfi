"""Source profiles for CSV import: Empower, Mint, generic.

A profile maps source-specific columns onto canonical fields and declares
how money signs work. Dates: ISO always accepted, plus MM/DD/YYYY[YY] for
the bank exports.
"""
import datetime as dt

PROFILES = {
    "generic": {
        "date": ["date"],
        "merchant": ["merchant", "description", "name"],
        "amount": ["amount"],
        "type": [],
        "debit_values": [],
        "credit_values": [],
        "category": ["category"],
        "note": ["note", "memo"],
        "account": ["account"],
    },
    "mint": {
        "date": ["date"],
        "merchant": ["description", "original description"],
        "amount": ["amount"],
        "type": ["transaction type", "type"],
        "debit_values": ["debit"],
        "credit_values": ["credit"],
        "category": ["category"],
        "note": ["notes", "labels"],
        "account": ["account name", "account"],
    },
    "empower": {
        "date": ["date", "posted date"],
        "merchant": ["description", "original description", "merchant", "name"],
        "amount": ["amount"],
        "type": ["type", "transaction type"],
        "debit_values": ["debit", "withdrawal", "expense"],
        "credit_values": ["credit", "deposit", "income"],
        "category": ["category"],
        "note": ["memo", "notes"],
        "account": ["account"],
    },
}

DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y")


def pick(row, names):
    lowered = {}
    for k, v in (row or {}).items():
        if k is not None:
            lowered[str(k).strip().lower()] = v
    for n in names:
        v = lowered.get(n)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return ""


def parse_date(value):
    value = (value or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def signed_cents(amount_str, type_str, profile):
    from .money import to_cents
    cents = to_cents(amount_str)
    t = (type_str or "").strip().lower()
    if t in profile["debit_values"]:
        return -abs(cents)
    if t in profile["credit_values"]:
        return abs(cents)
    return cents


def normalize_row(profile_name, row):
    profile = PROFILES.get(profile_name or "empower", PROFILES["empower"])
    date = parse_date(pick(row, profile["date"]))
    if date is None:
        return None
    merchant = pick(row, profile["merchant"])
    amount_raw = pick(row, profile["amount"]) or "0"
    cents = signed_cents(amount_raw, pick(row, profile["type"]), profile)
    return {
        "date": date,
        "merchant": merchant,
        "amount_cents": cents,
        "category": pick(row, profile["category"]),
        "note": pick(row, profile["note"]),
        "account": pick(row, profile["account"]),
    }

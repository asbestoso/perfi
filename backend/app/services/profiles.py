"""Source profiles for CSV import: Empower, Mint, generic, Robinhood activity.

A profile maps source-specific columns onto canonical fields and declares
how money signs work. Dates: ISO always accepted, plus MM/DD/YYYY[YY] for
the bank exports.

Header matching is alias-based, not exact: headers are normalized
(lowercased, non-alphanumerics stripped) and looked up in FIELD_ALIASES,
so "Account Name", "account_name" and "Account" all resolve to `account`.
New brokerages extend the alias tables instead of forking new profiles.
"""
import datetime as dt
import re

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

#: Canonical import fields shown on the mapping confirm screen, in order.
CANONICAL_FIELDS = ("date", "merchant", "amount", "type", "symbol",
                    "quantity", "price", "account", "category", "note")

#: Normalized-header aliases per canonical field. First entry is primary.
FIELD_ALIASES = {
    "date": ["date", "posteddate", "activitydate", "transactiondate",
             "dtposted", "time", "datetime"],
    "merchant": ["description", "originaldescription", "merchant", "name",
                 "memo", "narrative", "details"],
    "amount": ["amount", "total", "netamount", "totalamount"],
    "type": ["type", "transactiontype", "transcode", "action", "activity",
             "side"],
    "symbol": ["instrument", "symbol", "ticker", "security"],
    "quantity": ["quantity", "shares", "qty", "units", "shareamount"],
    "price": ["price", "unitprice", "pricepershare", "fillprice"],
    "account": ["account", "accountname", "accountnumber"],
    "category": ["category", "mastercategory", "typecategory"],
    "note": ["note", "notes", "memo", "labels", "comment"],
}

#: Header layouts fingerprinted for source auto-detection. Each entry maps
#: a source name to normalized headers that strongly signal it.
SOURCE_SIGNALS = {
    "robinhood": ["transcode", "instrument", "activitydate"],
    "mint": ["transactiontype", "accountname"],
    "empower": [],
}


def normalize_header(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").strip().lower())


def header_signature(headers):
    """Stable layout key for remembered mappings."""
    import hashlib
    normed = sorted(normalize_header(h) for h in headers or [])
    return hashlib.sha256(",".join(normed).encode("utf-8")).hexdigest()[:16]


def detect_source(headers):
    """Score headers against known layouts. Returns (source, confidence).

    Confidence is "high" when a source's signal headers are all present,
    "medium" when some match, else ("generic", "low").
    """
    normed = {normalize_header(h) for h in headers or []}
    best, hits = "generic", 0
    for source, signals in SOURCE_SIGNALS.items():
        if not signals:
            continue
        n = len(set(signals) & normed)
        if n == len(signals):
            return source, "high"
        if n > hits:
            best, hits = source, n
    if hits:
        return best, "medium"
    if "amount" in normed or "total" in normed:
        return "empower", "medium"
    return "generic", "low"


def propose_mapping(headers):
    """Propose canonical field -> file column. Returns {field: column|None}.

    First normalized-alias hit wins; a field stays None (never guessed)
    when no header matches. Extra file columns are left unmapped.
    """
    by_norm = {}
    for h in headers or []:
        by_norm.setdefault(normalize_header(h), h)
    mapping = {}
    for field in CANONICAL_FIELDS:
        mapping[field] = None
        for alias in FIELD_ALIASES.get(field, []):
            if alias in by_norm:
                mapping[field] = by_norm[alias]
                break
    return mapping


def unmapped_columns(headers, mapping):
    used = {c for c in mapping.values() if c}
    return [h for h in headers or [] if h not in used]


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

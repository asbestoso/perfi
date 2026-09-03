"""Cents money helpers (Ledgr port, simplified)."""
from decimal import Decimal, ROUND_HALF_UP


def to_cents(amount):
    s = str(amount).strip().replace("$", "").replace(",", "").replace(" ", "")
    neg = False
    if s.startswith("(") and s.endswith(")") and len(s) > 2:
        neg, s = True, s[1:-1]
    cents = int((Decimal(s or "0") * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return -cents if neg else cents


def to_dollars(cents):
    sign = "-" if cents < 0 else ""
    c = abs(cents)
    return f"{sign}{c // 100}.{c % 100:02d}"

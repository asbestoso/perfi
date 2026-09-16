"""Ledger identity, finance-app style: a persisted sha256 fingerprint.

Collision bar is deliberately high — only the most obvious matches count.
The fingerprint is exact equality on account + date + signed amount + a
tightly normalized merchant (case/punctuation/whitespace only; no suffix
stripping, no abbreviations logic). Anything fuzzier is handled by
``obvious_merchant_match`` in reconcile, which is containment-or-equal only.
"""
import re
from hashlib import sha256


def normalize_merchant(m):
    text = (m or "").lower().strip()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def compute_fingerprint(date, amount_cents, account_id, merchant):
    payload = "|".join((date.isoformat(), str(amount_cents),
                        str(account_id), normalize_merchant(merchant)))
    return sha256(payload.encode()).hexdigest()[:32]


def order_fingerprint(account_id, symbol, side, quantity_milli, price_cents,
                      fees_cents, executed_at):
    """Idempotency key for investment orders (double approval, re-upload)."""
    payload = "|".join((str(account_id), (symbol or "").upper(), side,
                        str(quantity_milli), str(price_cents),
                        str(fees_cents), executed_at.isoformat()))
    return sha256(payload.encode()).hexdigest()[:32]


def obvious_merchant_match(a, b):
    """True only for near-identical merchants: equal or containing.

    Catches "Shell" vs "SHELL OIL 57444" and "Whole Foods" vs
    "Whole Foods Market #12", but not rewordings with no shared run
    ("WHOLEFDS MKT" vs "Whole Foods") — those now auto-merge.
    """
    na, nb = normalize_merchant(a), normalize_merchant(b)
    if na == nb:
        return True
    if not na or not nb:
        return False
    return min(len(na), len(nb)) >= 4 and (na in nb or nb in na)

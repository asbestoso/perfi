"""Investment lots CSV: symbol, quantity, cost basis (+ optional acquired date).

Documented Empower-style columns accepted: symbol/ticker, quantity/shares,
cost/cost basis, acquired/date acquired. Prices stay manual (holdings).
"""
import csv
import io

from ..logging_setup import get as get_log
from ..models import InvestmentLot
from .money import to_cents
from .profiles import parse_date, pick

log = get_log("lots")


def import_lots(db, raw):
    text = raw.decode("utf-8-sig")
    created, skipped = 0, 0
    seen = {(l.symbol, l.quantity_milli, l.cost_cents, l.acquired)
            for l in db.query(InvestmentLot).all()}
    for lineno, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        symbol = pick(row, ["symbol", "ticker"]).upper()
        qty_raw = pick(row, ["quantity", "shares", "qty"]).replace(",", "")
        cost_raw = pick(row, ["cost", "cost basis", "basis"])
        if not symbol or not qty_raw:
            log.info(f"lots import line {lineno}: skipped (missing symbol/quantity)")
            skipped += 1
            continue
        if not cost_raw:
            log.info(f"lots import line {lineno}: skipped ({symbol}: missing cost basis)")
            skipped += 1
            continue
        try:
            milli = round(float(qty_raw) * 1000)
        except ValueError:
            log.info(f"lots import line {lineno}: skipped ({symbol}: bad quantity {qty_raw!r})")
            skipped += 1
            continue
        acquired = parse_date(pick(row, ["acquired", "date acquired", "date"]))
        cost_cents = to_cents(cost_raw)
        key = (symbol, milli, cost_cents, acquired)
        if key in seen:
            log.info(f"lots import line {lineno}: skipped ({symbol}: duplicate lot)")
            skipped += 1
            continue
        seen.add(key)
        db.add(InvestmentLot(symbol=symbol, quantity_milli=milli,
                             cost_cents=cost_cents, acquired=acquired))
        created += 1
    db.commit()
    log.info(f"lots import: created={created} skipped={skipped}")
    return {"created": created, "skipped": skipped}

"""Budgets, recurring, investments, reports, transfers (Ledgr port, simplified)."""
from sqlalchemy import func, select

from ..logging_setup import get as get_log
from ..models import Account, Budget, Category, Holding, Recurring, Transaction

log = get_log("analytics")


def prev_month(month):
    y, m = int(month[:4]), int(month[5:7])
    m -= 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def month_spent(db, category_id, month):
    spent = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.category_id == category_id,
            func.strftime("%Y-%m", Transaction.date) == month,
            Transaction.transfer_id.is_(None),
        )
    ) or 0
    return -min(spent, 0)


def rolled_in(db, category_id, month):
    """Unused budget carried forward through consecutive rollover months."""
    carry, m, hops = 0, prev_month(month), 0
    while hops < 24:
        prev = db.scalar(select(Budget).where(
            Budget.category_id == category_id, Budget.month == m))
        if prev is None or not prev.rollover:
            break
        carry = max(0, prev.limit_cents + carry - month_spent(db, category_id, m))
        m, hops = prev_month(m), hops + 1
    return carry


def budget_pace(month, spent, effective):
    import calendar
    import datetime as dt
    y, m = int(month[:4]), int(month[5:7])
    total = calendar.monthrange(y, m)[1]
    today = dt.date.today()
    cur = today.strftime("%Y-%m")
    elapsed = total if month < cur else (today.day if month == cur else 0)
    expected = effective * elapsed // total if total else effective
    if spent > effective:
        pace = "over"
    elif spent > expected:
        pace = "ahead"
    else:
        pace = "on_track"
    return expected, pace


def budget_status(db, month):
    out = []
    for b in db.scalars(select(Budget).where(Budget.month == month)).all():
        spent = month_spent(db, b.category_id, month)
        rolled = rolled_in(db, b.category_id, month)
        effective = b.limit_cents + rolled
        expected, pace = budget_pace(month, spent, effective)
        out.append({"budget_id": b.id, "category_id": b.category_id,
                    "limit_cents": b.limit_cents, "rolled_cents": rolled,
                    "effective_cents": effective, "spent_cents": spent,
                    "remaining_cents": effective - spent,
                    "expected_cents": expected, "pace": pace})
    return out


def portfolio_value(db):
    total = 0
    for h in db.scalars(select(Holding)).all():
        total += (h.quantity_milli * h.price_cents) // 1000
    return total


def portfolio_summary(db):
    from ..models import InvestmentLot
    lots = {}
    for lot in db.scalars(select(InvestmentLot)).all():
        sym = lot.symbol.upper()
        q, c = lots.get(sym, (0, 0))
        lots[sym] = (q + lot.quantity_milli, c + lot.cost_cents)
    holdings = {}
    for holding in db.scalars(select(Holding)).all():
        sym = holding.symbol.upper()
        position = holdings.setdefault(sym, {"quantity_milli": 0, "market_cents": 0,
                                             "accounts": {}})
        position["quantity_milli"] += holding.quantity_milli
        position["market_cents"] += (holding.quantity_milli * holding.price_cents) // 1000
        account_id = holding.account_id
        account_name = holding.account.name if holding.account is not None else "Unassigned"
        account = position["accounts"].setdefault(
            account_id, {"account_id": account_id, "name": account_name,
                         "quantity_milli": 0})
        account["quantity_milli"] += holding.quantity_milli
    positions, market_total, cost_total, gain_total = [], 0, 0, 0
    for sym in sorted(set(lots) | set(holdings)):
        lot_qty, lot_cost = lots.get(sym, (0, 0))
        holding = holdings.get(sym)
        holding_qty = holding["quantity_milli"] if holding else 0
        holding_market = holding["market_cents"] if holding else 0
        qty = holding_qty if sym in holdings else lot_qty
        market = holding_market if sym in holdings else 0
        price = (market * 1000) // qty if qty else 0
        has_cost = sym in lots
        gain = market - lot_cost if has_cost else None
        market_total += market
        if has_cost:
            cost_total += lot_cost
            gain_total += gain
        positions.append({"symbol": sym, "quantity_milli": qty,
                          "price_cents": price, "market_cents": market,
                          "cost_cents": lot_cost if has_cost else None,
                          "gain_cents": gain,
                          "accounts": list(holding["accounts"].values()) if holding else []})
    return {"positions": positions, "market_cents": market_total,
            "cost_cents": cost_total, "gain_cents": gain_total}


def monthly_spend(db, month):
    rows = db.execute(
        select(Transaction.category_id, func.sum(Transaction.amount_cents))
        .where(func.strftime("%Y-%m", Transaction.date) == month,
               Transaction.transfer_id.is_(None))
        .group_by(Transaction.category_id)
    ).all()
    return [{"category_id": cid, "total_cents": total} for cid, total in rows]


def net_worth(db):
    from ..models import Account
    cash = db.scalar(select(func.coalesce(func.sum(Account.balance_cents), 0))) or 0
    inv = portfolio_value(db)
    return {"cash_cents": cash, "investments_cents": inv, "net_worth_cents": cash + inv}


def transfer_suggestions(db, window_days=3, limit=50):
    """Candidate transfer pairs: opposite signs, same abs amount, close dates,
    different accounts, neither already linked."""
    rows = db.query(Transaction).filter(
        Transaction.transfer_id.is_(None)).order_by(Transaction.date.desc()).limit(2000).all()
    used = set()
    out = []
    for i, a in enumerate(rows):
        if a.id in used or not a.amount_cents:
            continue
        for b in rows[i + 1:]:
            if len(out) >= limit:
                return out
            if b.id in used or a.account_id == b.account_id:
                continue
            if a.amount_cents != -b.amount_cents:
                continue
            if abs((a.date - b.date).days) > int(window_days):
                continue
            out_tx = a if a.amount_cents < 0 else b
            in_tx = b if a.amount_cents < 0 else a
            used.add(a.id)
            used.add(b.id)
            out.append({"out_id": out_tx.id, "in_id": in_tx.id,
                        "amount_cents": abs(a.amount_cents),
                        "date": max(a.date, b.date).isoformat(),
                        "outgoing": {
                            "merchant": out_tx.merchant,
                            "date": out_tx.date.isoformat(),
                            "amount_cents": out_tx.amount_cents,
                            "account": db.get(Account, out_tx.account_id).name,
                        },
                        "incoming": {
                            "merchant": in_tx.merchant,
                            "date": in_tx.date.isoformat(),
                            "amount_cents": in_tx.amount_cents,
                            "account": db.get(Account, in_tx.account_id).name,
                        },
                        "confidence": "high"})
            break
    return out


CADENCES = (
    ("weekly", 6, 8),
    ("biweekly", 12, 16),
    ("monthly", 27, 32),
    ("quarterly", 89, 93),
    ("yearly", 360, 370),
)
_WINDOWS = {c: (lo, hi) for c, lo, hi in CADENCES}


def detect_recurring(db, min_occurrences=3):
    """Find repeat merchant+amount charges at regular intervals; upsert Recurring rows."""
    import datetime as dt
    groups = {}
    for t in db.query(Transaction).filter(
            Transaction.transfer_id.is_(None),
            Transaction.amount_cents != 0).order_by(Transaction.date).all():
        groups.setdefault((t.merchant.strip().lower(), t.amount_cents), []).append(t)
    created, updated = [], []
    for (key, cents), txns in groups.items():
        if len(txns) < min_occurrences:
            continue
        gaps = [(txns[i + 1].date - txns[i].date).days for i in range(len(txns) - 1)]
        median = sorted(gaps)[len(gaps) // 2]
        cadence = next((c for c, lo, hi in CADENCES if lo <= median <= hi), None)
        if cadence is None:
            continue
        lo, hi = _WINDOWS[cadence]
        if not all(lo <= g <= hi for g in gaps):
            continue
        name = txns[-1].merchant.strip()
        next_due = txns[-1].date + dt.timedelta(days=median)
        existing = db.query(Recurring).filter(
            Recurring.name == name, Recurring.amount_cents == cents).one_or_none()
        if existing is None:
            r = Recurring(name=name, amount_cents=cents,
                          cadence=cadence, next_due=next_due)
            db.add(r)
            db.flush()
            created.append(r.id)
        else:
            existing.cadence, existing.next_due = cadence, next_due
            updated.append(existing.id)
    db.commit()
    log.info(f"recurring detect: created={len(created)} updated={len(updated)}")
    return {"created": created, "updated": updated}


def month_list(n):
    import datetime as dt
    y, m = dt.date.today().year, dt.date.today().month
    out = []
    for _ in range(max(1, min(int(n), 60))):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def monthly_trends(db, months=12):
    out = []
    for month in month_list(months):
        filt = [func.strftime("%Y-%m", Transaction.date) == month,
                Transaction.transfer_id.is_(None)]
        income = db.scalar(select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            *filt, Transaction.amount_cents > 0)) or 0
        expense = db.scalar(select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            *filt, Transaction.amount_cents < 0)) or 0
        out.append({"month": month, "income_cents": income,
                    "expense_cents": -expense, "net_cents": income + expense})
    return out


def category_trends(db, months=6):
    wanted = month_list(months)
    cats = {c.id: c.name for c in db.query(Category).all()}
    cells = {}
    rows = db.execute(
        select(Transaction.category_id,
               func.strftime("%Y-%m", Transaction.date),
               func.sum(Transaction.amount_cents))
        .where(func.strftime("%Y-%m", Transaction.date).in_(wanted),
               Transaction.transfer_id.is_(None))
        .group_by(Transaction.category_id,
                  func.strftime("%Y-%m", Transaction.date))
    ).all()
    for cid, month, total in rows:
        cells[(cid, month)] = total or 0
    series = []
    for cid in sorted(cats, key=lambda i: (cats[i] or "").lower()):
        totals = [cells.get((cid, m), 0) for m in wanted]
        if any(totals):
            series.append({"category_id": cid, "category": cats[cid], "totals": totals})
    return {"months": wanted, "series": series}


def snapshot_balances(db, day=None):
    import datetime as dt
    from ..models import Account, BalanceSnapshot
    day = day or dt.date.today()
    cash = db.scalar(select(func.coalesce(func.sum(Account.balance_cents), 0))) or 0
    inv = portfolio_value(db)
    snap = db.query(BalanceSnapshot).filter_by(date=day).one_or_none()
    if snap is None:
        snap = BalanceSnapshot(date=day)
        db.add(snap)
    snap.cash_cents, snap.investments_cents, snap.net_worth_cents = cash, inv, cash + inv
    db.commit()
    db.refresh(snap)
    log.info(f"snapshot {snap.date.isoformat()}: net_worth={cash + inv}")
    return {"date": snap.date.isoformat(), "cash_cents": cash,
            "investments_cents": inv, "net_worth_cents": cash + inv}


def net_worth_history(db):
    from ..models import BalanceSnapshot
    return [{"date": s.date.isoformat(), "cash_cents": s.cash_cents,
             "investments_cents": s.investments_cents,
             "net_worth_cents": s.net_worth_cents}
            for s in db.query(BalanceSnapshot).order_by(BalanceSnapshot.date).all()]


REPORT_TYPES = ("spending", "trends", "net_worth", "category_trends")


def run_report(db, type, params):
    import datetime as dt
    from fastapi import HTTPException
    params = params or {}
    if type == "spending":
        month = params.get("month") or dt.date.today().strftime("%Y-%m")
        return {"month": month, "spend_by_category": monthly_spend(db, month),
                "budgets": budget_status(db, month)}
    if type == "trends":
        return monthly_trends(db, params.get("months", 12))
    if type == "net_worth":
        return net_worth_history(db)
    if type == "category_trends":
        return category_trends(db, params.get("months", 6))
    raise HTTPException(status_code=422, detail=f"unknown report type: {type}")


def link_transfer(db, out_id, in_id, transfer_id):
    for tid in (out_id, in_id):
        txn = db.get(Transaction, tid)
        if txn is not None:
            txn.transfer_id = transfer_id
    db.commit()

"""Funded buys: link a brokerage cash deposit to the buy it funded.

The usual shape is two steps: a transfer checking -> brokerage, then days
later a buy from the brokerage's cash. Auto-link fires only on an exact
principal-amount match inside a short window with exactly one candidate;
anything ambiguous stays a suggestion. Every mark is reversible via
unlink_order (transfer legs return to unlinked, spend-visible state).
"""
import datetime as dt

from fastapi import HTTPException
from sqlalchemy import or_

from ..models import InvestmentOrder, Transaction
from ..logging_setup import get as get_log

log = get_log("funding")

FUNDING_WINDOW_DAYS = 14


def principal(order):
    return (order.quantity_milli * order.price_cents) // 1000


def funding_mark(order_id):
    return f"order:{order_id}:funding"


def funding_candidates(db, order):
    """Unlinked deposits into the order's account matching the principal."""
    if order.side != "buy":
        return []
    lo = order.executed_at - dt.timedelta(days=FUNDING_WINDOW_DAYS)
    return db.query(Transaction).filter(
        Transaction.account_id == order.account_id,
        Transaction.transfer_id.is_(None),
        Transaction.amount_cents == principal(order),
        Transaction.date >= lo,
        Transaction.date <= order.executed_at,
    ).order_by(Transaction.date.desc()).all()


def order_funded(db, order):
    if order.linked_transaction_id is not None:
        return True
    return db.query(Transaction).filter(or_(
        Transaction.transfer_id == f"order:{order.id}",
        Transaction.transfer_id == funding_mark(order.id),
    )).limit(1).count() > 0


def auto_link_funding(db, order):
    """Mark the single exact funding candidate, if there is exactly one."""
    candidates = funding_candidates(db, order)
    if len(candidates) == 1:
        candidates[0].transfer_id = funding_mark(order.id)
        db.commit()
        log.info(f"funded buy: order {order.id} linked to transaction "
                 f"{candidates[0].id}")
        return candidates[0]
    return None


def link_funding(db, order_id, transaction_id=None):
    order = db.get(InvestmentOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Not found")
    if order.side != "buy":
        raise HTTPException(status_code=422, detail="only buys take funding")
    if transaction_id is not None:
        txn = db.get(Transaction, transaction_id)
        if txn is None:
            raise HTTPException(status_code=404, detail="Transaction not found")
        if txn.transfer_id is not None:
            raise HTTPException(status_code=422, detail="Transaction already linked")
        if txn.account_id != order.account_id:
            raise HTTPException(status_code=422, detail="Transaction is on another account")
        txn.transfer_id = funding_mark(order.id)
        db.commit()
        return txn
    candidates = funding_candidates(db, order)
    if len(candidates) == 1:
        return auto_link_funding(db, order)
    raise HTTPException(status_code=409, detail={
        "message": "ambiguous funding: pick a transaction",
        "candidates": [t.id for t in candidates],
    })


def suggestions(db, limit=50):
    """Buys without funding plus their candidate deposits, newest first."""
    out = []
    orders = db.query(InvestmentOrder).filter(
        InvestmentOrder.side == "buy").order_by(
        InvestmentOrder.executed_at.desc(),
        InvestmentOrder.id.desc()).all()
    for order in orders:
        if order_funded(db, order):
            continue
        candidates = funding_candidates(db, order)
        if not candidates:
            continue
        out.append({
            "order_id": order.id, "symbol": order.symbol,
            "executed_at": order.executed_at.isoformat(),
            "principal_cents": principal(order),
            "candidates": [{
                "id": t.id, "date": t.date.isoformat(),
                "merchant": t.merchant, "amount_cents": t.amount_cents,
            } for t in candidates],
        })
        if len(out) >= limit:
            break
    return out


def unlink_order(db, order_id):
    """Remove every funding/cash-leg mark pointing at this order."""
    order = db.get(InvestmentOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Not found")
    cleared = 0
    if order.linked_transaction_id is not None:
        order.linked_transaction_id = None
    for txn in db.query(Transaction).filter(or_(
            Transaction.transfer_id == f"order:{order.id}",
            Transaction.transfer_id == funding_mark(order.id))).all():
        txn.transfer_id = None
        cleared += 1
    db.commit()
    log.info(f"unlinked order {order.id}: cleared {cleared} legs")
    return {"ok": True, "cleared": cleared}

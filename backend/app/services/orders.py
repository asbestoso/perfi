"""Investment order creation shared by the API and trade approval.

Orders record raw trades (buys/sells with price and fees) and move the
separate holdings ledger. There is no tax-lot resolution: sells are
checked against holding quantity only. Orders are idempotent on a
fingerprint of account + symbol + side + quantity + price + fees +
date: posting the same order twice (double approval, re-uploaded file)
returns the existing order without moving holdings twice.
"""
from fastapi import HTTPException
from sqlalchemy import func

from ..models import Account, Holding, InvestmentOrder, Transaction
from .fingerprint import order_fingerprint


def find_order(db, fingerprint):
    return db.query(InvestmentOrder).filter_by(fingerprint=fingerprint).one_or_none()


def create_order(db, account_id, symbol, side, quantity_milli, price_cents,
                 fees_cents, executed_at, linked_transaction_id=None):
    if side not in ("buy", "sell"):
        raise HTTPException(status_code=422, detail="Side must be buy or sell")
    if quantity_milli <= 0 or price_cents <= 0 or fees_cents < 0:
        raise HTTPException(status_code=422, detail="Quantity, price, and fees are invalid")
    if db.get(Account, account_id) is None:
        raise HTTPException(status_code=404, detail="Not found")
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=422, detail="Symbol is required")
    fp = order_fingerprint(account_id, symbol, side, quantity_milli,
                           price_cents, fees_cents, executed_at)
    existing = find_order(db, fp)
    if existing is not None:
        return existing
    quantity = quantity_milli
    proceeds = (quantity * price_cents) // 1000 - fees_cents
    linked = None
    if linked_transaction_id is not None:
        linked = db.get(Transaction, linked_transaction_id)
        if linked is None:
            raise HTTPException(status_code=404, detail="Linked transaction not found")
        if linked.transfer_id is not None:
            raise HTTPException(status_code=422, detail="Transaction already linked")
    order = InvestmentOrder(
        account_id=account_id, symbol=symbol, side=side,
        quantity_milli=quantity, price_cents=price_cents,
        fees_cents=fees_cents, executed_at=executed_at,
        proceeds_cents=proceeds if side == "sell" else None,
        linked_transaction_id=linked_transaction_id,
        fingerprint=fp,
    )
    holding = db.query(Holding).filter(
        func.upper(Holding.symbol) == symbol,
        Holding.account_id == account_id).order_by(Holding.id).first()
    delta = quantity if side == "buy" else -quantity
    if holding is None:
        if delta < 0:
            raise HTTPException(status_code=422, detail="No holding exists for this sell")
        holding = Holding(symbol=symbol, account_id=account_id,
                          quantity_milli=delta, price_cents=price_cents)
        db.add(holding)
    else:
        if holding.quantity_milli + delta < 0:
            raise HTTPException(status_code=422, detail="Sell exceeds holding shares")
        holding.quantity_milli += delta
        holding.price_cents = price_cents
    db.add(order)
    db.flush()
    if linked is not None:
        linked.transfer_id = f"order:{order.id}"
    db.commit()
    db.refresh(order)
    return order

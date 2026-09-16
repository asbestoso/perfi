"""Reversible removal of records created by an import batch."""
import datetime as dt
from fastapi import HTTPException
from sqlalchemy import or_

from ..models import Holding, ImportBatch, InvestmentLot, InvestmentOrder, Transaction


def rollback_batch(db, batch_id):
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Not found")
    if batch.status == "rolled_back":
        raise HTTPException(status_code=409, detail="import batch is already rolled back")

    orders = db.query(InvestmentOrder).filter_by(import_batch_id=batch.id).all()
    transactions = db.query(Transaction).filter_by(import_batch_id=batch.id).all()
    for order in orders:
        for txn in db.query(Transaction).filter(or_(
                Transaction.transfer_id == f"order:{order.id}",
                Transaction.transfer_id == f"order:{order.id}:funding")).all():
            txn.transfer_id = None
        order.linked_transaction_id = None
        holding = db.query(Holding).filter(
            Holding.account_id == order.account_id,
            Holding.symbol.ilike(order.symbol),
        ).order_by(Holding.id).first()
        delta = order.quantity_milli if order.side == "buy" else -order.quantity_milli
        if holding is not None:
            holding.quantity_milli -= delta
            if holding.quantity_milli < 0:
                raise HTTPException(
                    status_code=409,
                    detail=f"cannot roll back order {order.id}: holding was changed later",
                )
            if holding.quantity_milli == 0:
                db.delete(holding)
        if order.side == "buy":
            lot = db.query(InvestmentLot).filter(
                InvestmentLot.account_id == order.account_id,
                InvestmentLot.symbol.ilike(order.symbol),
                InvestmentLot.quantity_milli == order.quantity_milli,
                InvestmentLot.cost_cents == (order.cost_basis_cents or 0),
                InvestmentLot.acquired == order.executed_at,
            ).order_by(InvestmentLot.id.desc()).first()
            if lot is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"cannot roll back order {order.id}: original lot is missing or changed",
                )
            db.delete(lot)
        else:
            db.add(InvestmentLot(
                symbol=order.symbol, account_id=order.account_id,
                quantity_milli=order.quantity_milli,
                cost_cents=order.cost_basis_cents or 0,
                acquired=order.executed_at,
            ))
        db.delete(order)

    for transaction in transactions:
        db.delete(transaction)
    for row in batch.rows:
        if row.status == "merged":
            row.status = "pending"
    batch.status = "rolled_back"
    batch.rolled_back_at = dt.datetime.utcnow()
    db.commit()
    return {
        "ok": True,
        "batch_id": batch.id,
        "transactions": len(transactions),
        "investment_orders": len(orders),
    }

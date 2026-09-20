"""Reversible removal of records created by an import batch."""
import datetime as dt
import json
from fastapi import HTTPException
from sqlalchemy import or_

from ..models import Holding, ImportBatch, InvestmentOrder, Transaction


def rollback_batch(db, batch_id):
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Not found")
    if batch.status == "rolled_back":
        raise HTTPException(status_code=409, detail="import batch is already rolled back")

    orders = db.query(InvestmentOrder).filter_by(import_batch_id=batch.id).all()
    holdings = db.query(Holding).filter_by(import_batch_id=batch.id).all()
    previous = json.loads(batch.mapping or "{}").get("_holding_previous", [])
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
        db.delete(order)

    for transaction in transactions:
        db.delete(transaction)
    for holding in holdings:
        db.delete(holding)
    for item in previous:
        holding = db.query(Holding).filter_by(
            account_id=item["account_id"], symbol=item["symbol"]).one_or_none()
        if holding is None:
            holding = Holding(account_id=item["account_id"], symbol=item["symbol"])
            db.add(holding)
        holding.quantity_milli = item["quantity_milli"]
        holding.name = item.get("name")
        holding.price_cents = item.get("price_cents", 0)
        holding.import_batch_id = item.get("import_batch_id")
    for row in batch.rows:
        if row.status == "merged":
            row.status = "pending"
    batch.status = "rolled_back"
    batch.rolled_back_at = dt.datetime.utcnow()
    db.commit()
    result = {
        "ok": True,
        "batch_id": batch.id,
        "transactions": len(transactions),
        "investment_orders": len(orders),
    }
    if holdings:
        result["holdings"] = len(holdings)
    return result

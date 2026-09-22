"""Reversible removal of records created by an import batch."""
import datetime as dt
import json
from fastapi import HTTPException

from ..models import Holding, ImportBatch, Transaction


def rollback_batch(db, batch_id):
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Not found")
    if batch.status == "rolled_back":
        raise HTTPException(status_code=409, detail="import batch is already rolled back")

    holdings = db.query(Holding).filter_by(import_batch_id=batch.id).all()
    previous = json.loads(batch.mapping or "{}").get("_holding_previous", [])
    transactions = db.query(Transaction).filter_by(import_batch_id=batch.id).all()
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
    }
    if holdings:
        result["holdings"] = len(holdings)
    return result

"""Reconcile queue: merge staged rows into transactions or discard them."""
from fastapi import HTTPException

from ..logging_setup import get as get_log
from ..models import StagingRow, Transaction

log = get_log("reconcile")


def _row_account_id(s):
    return s.account_id if s.account_id is not None else s.batch.account_id


def merge_row(db, staging_id):
    from .csv_import import transaction_exists
    s = db.get(StagingRow, staging_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Not found")
    if s.status != "pending":
        raise HTTPException(status_code=409, detail=f"already {s.status}")
    if transaction_exists(db, _row_account_id(s), s.date, s.amount_cents, s.merchant):
        raise HTTPException(status_code=409, detail="duplicate of an existing transaction")
    t = Transaction(account_id=_row_account_id(s), category_id=s.category_id,
                    amount_cents=s.amount_cents, merchant=s.merchant,
                    date=s.date, note=s.note, category_source=s.category_source)
    s.status = "merged"
    db.add(t)
    db.commit()
    db.refresh(t)
    log.info(f"merged staging {staging_id} -> transaction {t.id}")
    return t


def discard_row(db, staging_id):
    s = db.get(StagingRow, staging_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Not found")
    if s.status != "pending":
        raise HTTPException(status_code=409, detail=f"already {s.status}")
    s.status = "discarded"
    db.commit()
    log.info(f"discarded staging {staging_id}")
    return s


def merge_batch(db, batch_id):
    from ..models import ImportBatch
    from .csv_import import dedupe_key, transaction_exists
    b = db.get(ImportBatch, batch_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Not found")
    merged, skipped = 0, 0
    done = set()
    for s in db.query(StagingRow).filter_by(batch_id=b.id, status="pending").all():
        aid = _row_account_id(s)
        key = dedupe_key(aid, s.date, s.amount_cents, s.merchant)
        if key in done or transaction_exists(db, aid, s.date, s.amount_cents, s.merchant):
            skipped += 1
            continue
        done.add(key)
        db.add(Transaction(account_id=aid, category_id=s.category_id,
                           amount_cents=s.amount_cents, merchant=s.merchant,
                           date=s.date, note=s.note,
                           category_source=s.category_source))
        s.status = "merged"
        merged += 1
    db.commit()
    log.info(f"merge-all batch {batch_id}: merged={merged} skipped_dupes={skipped}")
    return merged, skipped

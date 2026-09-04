"""Reconcile queue: merge staged rows into transactions or discard them.

Two merge paths: ``merge_batch`` merges everything that is not an exact
duplicate (the force path), while ``merge_safe`` auto-merges only rows with
no exact *or* near-duplicate candidates and leaves the maybes pending for
review (see ``classify_batch`` / ``GET /import/batches/{id}/review``).
"""
from fastapi import HTTPException

from ..logging_setup import get as get_log
from ..models import StagingRow, Transaction
from .fingerprint import compute_fingerprint, obvious_merchant_match

log = get_log("reconcile")


def _row_account_id(s):
    return s.account_id if s.account_id is not None else s.batch.account_id


def _posted_merchant_map(db):
    """(account, date, amount) -> [merchants], one streamed pass.

    Lets classify_batch match purely in Python: per-row queries plus a
    per-row peer scan turned a 9k-row batch into an 80M-iteration hang.
    """
    out = {}
    q = db.query(Transaction.account_id, Transaction.date,
                 Transaction.amount_cents, Transaction.merchant)
    for aid, d, cents, m in q.yield_per(1000):
        out.setdefault((aid, d, cents), []).append(m)
    return out


def _staged_tx(s, aid):
    return Transaction(account_id=aid, category_id=s.category_id,
                       amount_cents=s.amount_cents, merchant=s.merchant,
                       date=s.date, note=s.note,
                       category_source=s.category_source,
                       fingerprint=compute_fingerprint(
                           s.date, s.amount_cents, aid, s.merchant))


def classify_batch(db, batch_id):
    """Split a batch's pending rows into safe ids and suspects with reasons.

    Suspects cover exact dupes (vs posted transactions or a sibling row)
    plus obvious near-dupes: same date + amount with a near-identical
    merchant (equal or containing, vs posted or an earlier in-batch row).
    First occurrence wins; rewordings and drifted dates auto-merge.
    """
    from ..models import ImportBatch
    from .csv_import import norm_merchant
    b = db.get(ImportBatch, batch_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Not found")
    pending = db.query(StagingRow).filter_by(
        batch_id=b.id, status="pending").order_by(StagingRow.id).all()
    by_key, meta = {}, {}
    for s in pending:
        aid = _row_account_id(s)
        key = (aid, s.date, s.amount_cents)
        by_key.setdefault(key, []).append(s)
        meta[s.id] = (aid, compute_fingerprint(
            s.date, s.amount_cents, aid, s.merchant))
    posted = _posted_merchant_map(db)
    safe, suspects = [], []
    seen = set()
    for s in pending:
        aid, fp = meta[s.id]
        if fp in seen:
            suspects.append({"staging_id": s.id,
                             "reasons": ["exact duplicate of another row in this batch"]})
            continue
        seen.add(fp)
        key = (aid, s.date, s.amount_cents)
        names = posted.get(key, [])
        want = norm_merchant(s.merchant)
        if any(norm_merchant(m) == want for m in names):
            suspects.append({"staging_id": s.id,
                             "reasons": ["exact duplicate of an existing transaction"]})
            continue
        reasons, cited = [], set()
        for m in names:
            if m in cited or not obvious_merchant_match(s.merchant, m):
                continue
            cited.add(m)
            reasons.append(
                f"same date and amount as existing '{m}' (near-identical merchant)")
            if len(reasons) == 3:
                break
        if not reasons:
            for p in by_key[key]:  # id-ordered: first occurrence wins
                if p.id >= s.id:
                    break
                if meta[p.id][1] == fp:
                    continue  # covered by the exact in-batch case above
                if obvious_merchant_match(s.merchant, p.merchant):
                    reasons.append(
                        f"same date and amount as another row in this batch ('{p.merchant}')")
                    break
        if reasons:
            suspects.append({"staging_id": s.id, "reasons": reasons})
        else:
            safe.append(s.id)
    return safe, suspects


def merge_safe(db, batch_id):
    """Merge only rows with no dupe candidates; leave suspects pending."""
    safe, suspects = classify_batch(db, batch_id)
    wanted = set(safe)
    merged = 0
    for s in db.query(StagingRow).filter_by(
            batch_id=batch_id, status="pending").all():
        if s.id not in wanted:
            continue
        db.add(_staged_tx(s, _row_account_id(s)))
        s.status = "merged"
        merged += 1
    db.commit()
    log.info(f"merge-safe batch {batch_id}: merged={merged} held={len(suspects)}")
    return merged, suspects


def merge_row(db, staging_id):
    from .csv_import import transaction_exists
    s = db.get(StagingRow, staging_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Not found")
    if s.status != "pending":
        raise HTTPException(status_code=409, detail=f"already {s.status}")
    if transaction_exists(db, _row_account_id(s), s.date, s.amount_cents, s.merchant):
        raise HTTPException(status_code=409, detail="duplicate of an existing transaction")
    t = _staged_tx(s, _row_account_id(s))
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
    from .csv_import import transaction_exists
    b = db.get(ImportBatch, batch_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Not found")
    merged, skipped = 0, 0
    done = set()
    for s in db.query(StagingRow).filter_by(batch_id=b.id, status="pending").all():
        aid = _row_account_id(s)
        fp = compute_fingerprint(s.date, s.amount_cents, aid, s.merchant)
        if fp in done or transaction_exists(db, aid, s.date, s.amount_cents, s.merchant):
            skipped += 1
            continue
        done.add(fp)
        db.add(_staged_tx(s, aid))
        s.status = "merged"
        merged += 1
    db.commit()
    log.info(f"merge-all batch {batch_id}: merged={merged} skipped_dupes={skipped}")
    return merged, skipped

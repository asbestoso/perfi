"""CSV import into staging: profile normalize + dedupe, user merges after."""
import csv
import io
import json

from sqlalchemy import select

from ..logging_setup import get as get_log
from ..models import Account, Category, CategoryRule, ImportBatch, StagingRow, Transaction
from .categorization import resolve_category
from .profiles import PROFILES, normalize_row

log = get_log("import")


def resolve_account(db, name):
    name = (name or "").strip() or "Default"
    a = db.query(Account).filter_by(name=name).one_or_none()
    if a is None:
        a = Account(name=name)
        db.add(a)
        db.flush()
    return a


def norm_merchant(merchant):
    return (merchant or "").strip().casefold()


def dedupe_key(account_id, date, amount_cents, merchant):
    return (account_id, date.isoformat(), amount_cents, norm_merchant(merchant))


def dedupe_keys(db):
    """All (account, date, amount, merchant) keys already staged or posted.

    Streams in pages instead of materializing whole tables.
    """
    keys = set()
    txn_q = db.query(Transaction.account_id, Transaction.date,
                     Transaction.amount_cents, Transaction.merchant)
    for aid, d, cents, m in txn_q.yield_per(1000):
        keys.add(dedupe_key(aid, d, cents, m))
    stage_q = db.query(StagingRow.account_id, StagingRow.date,
                       StagingRow.amount_cents, StagingRow.merchant).filter(
        StagingRow.status != "discarded")
    for aid, d, cents, m in stage_q.yield_per(1000):
        keys.add(dedupe_key(aid, d, cents, m))
    return keys


def transaction_exists(db, account_id, date, amount_cents, merchant):
    """Merge-time recheck using the same normalization as dedupe_key."""
    want = norm_merchant(merchant)
    merchants = db.query(Transaction.merchant).filter_by(
        account_id=account_id, date=date, amount_cents=amount_cents).all()
    return any(norm_merchant(m) == want for (m,) in merchants)


def trusted_category(cats_by_lower, name):
    if name:
        hit = cats_by_lower.get(name.strip().lower())
        if hit is not None:
            return hit, "import"
    return None, None


def stage_rows(db, account_id, profile_name, filename, parsed):
    cats = {c.name: c.id for c in db.scalars(select(Category)).all()}
    cats_by_lower = {n.lower(): n for n in cats}
    unc_id = cats.get("Uncategorized")
    seen = dedupe_keys(db)
    rules = db.query(CategoryRule).order_by(CategoryRule.priority).all()
    override = None
    if account_id is not None:
        override = db.get(Account, account_id)
        if override is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")
    batch = ImportBatch(profile=profile_name, filename=filename or "",
                        account_id=account_id)
    db.add(batch)
    db.flush()
    staged, skipped, accounts = 0, 0, set()
    for p, raw in parsed:
        acct = override or resolve_account(db, p.get("account", ""))
        key = dedupe_key(acct.id, p["date"], p["amount_cents"], p["merchant"])
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        accounts.add(acct.name)
        if batch.account_id is None:
            batch.account_id = acct.id
        tname, tsource = trusted_category(cats_by_lower, p["category"])
        if tname is None:
            tname, tsource = resolve_category(db, p["merchant"], rules)
        db.add(StagingRow(batch_id=batch.id, account_id=acct.id,
                          date=p["date"], merchant=p["merchant"],
                          amount_cents=p["amount_cents"],
                          category_id=cats.get(tname, unc_id),
                          category_source=tsource, note=p["note"] or None,
                          raw=json.dumps(raw, default=str)))
        staged += 1
    batch.staged, batch.skipped = staged, skipped
    db.commit()
    db.refresh(batch)
    log.info(f"batch {batch.id} ({profile_name} {filename or '-'}): "
             f"staged={staged} skipped={skipped} accounts={sorted(accounts)}")
    return {"batch_id": batch.id, "staged": staged, "skipped": skipped,
            "accounts": sorted(accounts)}


def import_csv(db, account_id, raw, profile="generic", filename=""):
    if profile not in PROFILES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"unknown profile: {profile}")
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    parsed, skipped = [], 0
    for row in reader:
        norm = normalize_row(profile, row)
        if norm is None:
            skipped += 1
            continue
        parsed.append((norm, row))
    result = stage_rows(db, account_id, profile, filename, parsed)
    result["skipped"] += skipped
    db.query(ImportBatch).filter_by(id=result["batch_id"]).update(
        {"skipped": result["skipped"]}, synchronize_session=False)
    db.commit()
    return result

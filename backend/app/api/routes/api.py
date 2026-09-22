"""Thin CRUD + domain routes under /api."""
import datetime as dt
import math
import re
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_, select

from ... import models, schemas
from ..deps import get_db
from ..pagination import pagination
from ...services import analytics, reconcile
from ...services.csv_import import import_csv
from ...services.fingerprint import compute_fingerprint
from ...services.market_data import QuoteUnavailableError, get_live_name, get_live_price
from ...services.profiles import detect_source, header_signature, propose_mapping, unmapped_columns

router = APIRouter()

ACCOUNT_DOMAINS = ("spending", "investing", "mixed")
TRANSACTION_KINDS = ("expense", "income", "investment_contribution",
                     "investment_distribution")


def _check_domain(domain):
    if domain not in ACCOUNT_DOMAINS:
        raise HTTPException(status_code=422, detail="Invalid account domain")


def _check_kind(kind):
    if kind not in TRANSACTION_KINDS:
        raise HTTPException(status_code=422, detail="Invalid transaction kind")


def _check_domain_param(domain):
    if domain != "all":
        _check_domain(domain)


def _get_or_404(db, model, id):
    obj = db.get(model, id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


def _as_int(value, name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{name} must be an integer")


def _as_date(value, name):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{name} must be YYYY-MM-DD")


def _check_pattern(pattern):
    try:
        re.compile(pattern)
    except re.error:
        raise HTTPException(status_code=422, detail="pattern must be a valid regex")


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/accounts", response_model=schemas.Page[schemas.AccountRead])
def list_accounts(paging=Depends(pagination), db=Depends(get_db)):
    limit, offset = paging
    total = db.scalar(select(func.count()).select_from(models.Account)) or 0
    items = db.scalars(select(models.Account).limit(limit).offset(offset)).all()
    holding_totals = {}
    for account_id, value in db.query(
        models.Holding.account_id,
        func.sum((models.Holding.quantity_milli * models.Holding.price_cents) / 1000),
    ).filter(models.Holding.account_id.is_not(None)).group_by(models.Holding.account_id).all():
        holding_totals[account_id] = round(value or 0)
    return {
        "items": [
            {
                "id": account.id,
                "name": account.name,
                "type": account.type,
                "domain": account.domain,
                "balance_cents": holding_totals.get(account.id, account.balance_cents),
            }
            for account in items
        ],
        "total": total,
    }


@router.post("/accounts", response_model=schemas.AccountRead)
def create_account(payload: schemas.AccountCreate, db=Depends(get_db)):
    if db.query(models.Account).filter_by(name=payload.name).one_or_none() is not None:
        raise HTTPException(status_code=409, detail="account name exists")
    _check_domain(payload.domain)
    a = models.Account(**payload.model_dump())
    db.add(a); db.commit(); db.refresh(a)
    return a


@router.patch("/accounts/{id}", response_model=schemas.AccountRead)
def update_account(id, payload: schemas.AccountUpdate, db=Depends(get_db)):
    account = _get_or_404(db, models.Account, _as_int(id, "id"))
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name is required")
        duplicate = db.query(models.Account).filter(
            models.Account.name == name, models.Account.id != account.id,
        ).one_or_none()
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="account name exists")
        account.name = name
    if payload.type is not None:
        account.type = payload.type.strip()
    if payload.domain is not None:
        _check_domain(payload.domain)
        account.domain = payload.domain
    if payload.balance_cents is not None:
        if account.type != "manual":
            raise HTTPException(status_code=422,
                                detail="only manual accounts have an editable balance")
        account.balance_cents = int(payload.balance_cents)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/accounts/{id}")
def delete_account(id, db=Depends(get_db)):
    account = _get_or_404(db, models.Account, _as_int(id, "id"))
    db.query(models.Transaction).filter_by(account_id=account.id).delete(
        synchronize_session=False)
    db.query(models.Holding).filter_by(account_id=account.id).delete(
        synchronize_session=False)
    db.query(models.PortfolioSnapshot).filter_by(account_id=account.id).delete(
        synchronize_session=False)
    db.query(models.StagingRow).filter_by(account_id=account.id).update(
        {"account_id": None}, synchronize_session=False)
    db.query(models.ImportAccountMapping).filter_by(account_id=account.id).delete(
        synchronize_session=False)
    db.query(models.ImportBatch).filter_by(account_id=account.id).update(
        {"account_id": None}, synchronize_session=False)
    db.delete(account)
    db.commit()
    return {"ok": True, "deleted": id}


@router.get("/categories", response_model=schemas.Page[schemas.CategoryRead])
def list_categories(paging=Depends(pagination), db=Depends(get_db)):
    limit, offset = paging
    total = db.scalar(select(func.count()).select_from(models.Category)) or 0
    items = db.scalars(select(models.Category).limit(limit).offset(offset)).all()
    return {"items": items, "total": total}


@router.post("/categories", response_model=schemas.CategoryRead)
def create_category(payload: schemas.CategoryCreate, db=Depends(get_db)):
    c = models.Category(**payload.model_dump())
    db.add(c); db.commit(); db.refresh(c)
    return c


@router.put("/categories/{id}", response_model=schemas.CategoryRead)
def update_category(id, payload: schemas.CategoryUpdate, db=Depends(get_db)):
    c = _get_or_404(db, models.Category, _as_int(id, "id"))
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/categories/{id}")
def delete_category(id, db=Depends(get_db)):
    c = _get_or_404(db, models.Category, _as_int(id, "id"))
    if c.name == "Uncategorized":
        raise HTTPException(status_code=400, detail="Cannot delete Uncategorized")
    unc = db.query(models.Category).filter_by(name="Uncategorized").one_or_none()
    if unc is None:
        raise HTTPException(status_code=409, detail="Uncategorized missing")
    moved_tx = db.query(models.Transaction).filter_by(category_id=c.id).update(
        {"category_id": unc.id, "category_source": None}, synchronize_session=False)
    moved_rules = db.query(models.CategoryRule).filter_by(category_id=c.id).update(
        {"category_id": unc.id}, synchronize_session=False)
    db.delete(c)
    db.commit()
    return {"ok": True, "moved_transactions": moved_tx, "moved_rules": moved_rules}


@router.get("/transactions", response_model=schemas.Page[schemas.TransactionRead])
def list_transactions(paging=Depends(pagination), account_id=None, category_id=None,
                      date_from=None, date_to=None, q=None, domain=None,
                      transaction_kind=None, db=Depends(get_db)):
    limit, offset = paging
    stmt = select(models.Transaction)
    total_stmt = select(func.count()).select_from(models.Transaction)
    if account_id is not None:
        aid = _as_int(account_id, "account_id")
        stmt = stmt.where(models.Transaction.account_id == aid)
        total_stmt = total_stmt.where(models.Transaction.account_id == aid)
    if domain is not None:
        _check_domain(domain)
        stmt = stmt.join(models.Account).where(models.Account.domain == domain)
        total_stmt = total_stmt.join(models.Account).where(models.Account.domain == domain)
    if transaction_kind is not None:
        stmt = stmt.where(models.Transaction.transaction_kind == transaction_kind)
        total_stmt = total_stmt.where(models.Transaction.transaction_kind == transaction_kind)
    if category_id is not None:
        cid = _as_int(category_id, "category_id")
        stmt = stmt.where(models.Transaction.category_id == cid)
        total_stmt = total_stmt.where(models.Transaction.category_id == cid)
    if date_from is not None:
        d = _as_date(date_from, "date_from")
        stmt = stmt.where(models.Transaction.date >= d)
        total_stmt = total_stmt.where(models.Transaction.date >= d)
    if date_to is not None:
        d = _as_date(date_to, "date_to")
        stmt = stmt.where(models.Transaction.date <= d)
        total_stmt = total_stmt.where(models.Transaction.date <= d)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(models.Transaction.merchant.ilike(like),
                              models.Transaction.note.ilike(like)))
        total_stmt = total_stmt.where(or_(models.Transaction.merchant.ilike(like),
                                          models.Transaction.note.ilike(like)))
    total = db.scalar(total_stmt) or 0
    items = db.scalars(
        stmt.order_by(models.Transaction.date.desc()).limit(limit).offset(offset)
    ).all()
    return {"items": items, "total": total}


@router.get("/transactions/{id}", response_model=schemas.TransactionRead)
def get_transaction(id, db=Depends(get_db)):
    return _get_or_404(db, models.Transaction, _as_int(id, "id"))


@router.patch("/transactions/{id}", response_model=schemas.TransactionRead)
def update_transaction(id, payload: schemas.TransactionUpdate, db=Depends(get_db)):
    t = _get_or_404(db, models.Transaction, _as_int(id, "id"))
    data = payload.model_dump(exclude_unset=True)
    if data.get("account_id") is not None:
        _get_or_404(db, models.Account, data["account_id"])
    if data.get("category_id") is not None:
        _get_or_404(db, models.Category, data["category_id"])
    if data.get("transaction_kind") is not None:
        _check_kind(data["transaction_kind"])
    if "category_id" in data:
        data["category_source"] = "manual"
    for k, v in data.items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/transactions/{id}")
def delete_transaction(id, db=Depends(get_db)):
    t = _get_or_404(db, models.Transaction, _as_int(id, "id"))
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.post("/transactions", response_model=schemas.TransactionRead)
def create_transaction(payload: schemas.TransactionCreate, db=Depends(get_db)):
    _get_or_404(db, models.Account, payload.account_id)
    if payload.category_id is not None:
        _get_or_404(db, models.Category, payload.category_id)
    _check_kind(payload.transaction_kind)
    t = models.Transaction(**payload.model_dump())
    t.fingerprint = compute_fingerprint(
        t.date, t.amount_cents, t.account_id, t.merchant)
    db.add(t); db.commit(); db.refresh(t)
    return t


@router.post("/import/csv")
def csv_import(file: UploadFile, account_id=None, profile="empower",
               file_kind="mixed", mapping=None, db=Depends(get_db)):
    aid = None
    if account_id is not None:
        aid = _as_int(account_id, "account_id")
        _get_or_404(db, models.Account, aid)
    if file_kind not in ("mixed", "brokerage", "spending"):
        raise HTTPException(status_code=422, detail="Invalid file kind")
    parsed_mapping = None
    if mapping:
        import json
        try:
            parsed_mapping = json.loads(mapping)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="mapping must be a JSON object")
        if not isinstance(parsed_mapping, dict):
            raise HTTPException(status_code=422, detail="mapping must be a JSON object")
    return import_csv(db, aid, file.file.read(), profile, file.filename or "",
                      file_kind, parsed_mapping)


@router.post("/import/holdings/scan")
def holdings_import_scan(file: UploadFile, db=Depends(get_db)):
    import csv as csvmod
    import io
    try:
        text = file.file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="file must be UTF-8 CSV")
    reader = csvmod.DictReader(io.StringIO(text))
    required = {"Account", "Holding", "Quantity"}
    headers = set(reader.fieldnames or [])
    if not required.issubset(headers):
        raise HTTPException(status_code=422,
                            detail="holding CSV must contain Account, Holding, and Quantity columns")
    rows = []
    labels = set()
    known_symbols = {
        holding.symbol.upper()
        for holding in db.query(models.Holding).all()
        if holding.symbol
    }
    for index, row in enumerate(reader):
        label = (row.get("Account") or "").strip()
        symbol = (row.get("Holding") or "").strip().upper()
        if label:
            labels.add(label)
        rows.append({
            "id": index,
            "account": label,
            "symbol": symbol,
            "quantity": (row.get("Quantity") or "").strip(),
            "known": symbol in known_symbols,
        })
    live_ids = {row[0] for row in db.query(models.Account.id).all()}
    saved = {
        item.external_label: item.account_id
        for item in db.query(models.ImportAccountMapping).filter_by(profile="Holding").all()
        if item.account_id in live_ids
    }
    accounts = [
        {"id": account.id, "name": account.name, "type": account.type,
         "domain": account.domain}
        for account in db.query(models.Account).order_by(models.Account.name).all()
    ]
    return {
        "accounts": accounts,
        "external_accounts": [
            {"label": label, "saved_account_id": saved.get(label)}
            for label in sorted(labels)
        ],
        "rows": rows,
        "row_count": len(rows),
    }


@router.post("/import/scan")
def import_scan(file: UploadFile, file_kind=None, mapping=None, db=Depends(get_db)):
    """Dry-run header scan: detection + proposed mapping + samples, no writes.

    Optional file_kind + mapping (JSON object) preview classification
    counts for a user-edited mapping instead of the proposed one.
    """
    import csv as csvmod
    import io
    import json
    from ...services.classify import classify, normalize_mapped
    try:
        text = file.file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="file must be UTF-8 CSV")
    reader = csvmod.DictReader(io.StringIO(text))
    headers = [h for h in (reader.fieldnames or []) if h is not None]
    headers = [h for h in headers if str(h).strip() != ""]
    if not headers:
        raise HTTPException(status_code=422, detail="no columns found: not a CSV")
    proposed = propose_mapping(headers)
    if all(v is None for v in proposed.values()):
        raise HTTPException(status_code=422, detail="no recognizable columns")
    active_mapping = proposed
    if mapping:
        try:
            custom = json.loads(mapping)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="mapping must be a JSON object")
        if not isinstance(custom, dict):
            raise HTTPException(status_code=422, detail="mapping must be a JSON object")
        active_mapping = {f: custom.get(f) for f in proposed}
    source, confidence = detect_source(headers)
    if source == "robinhood":
        suggested_file_kind = "brokerage"
    else:
        suggested_file_kind = "mixed"
    kind = file_kind or suggested_file_kind
    if kind not in ("mixed", "brokerage", "spending"):
        raise HTTPException(status_code=422, detail="Invalid file kind")
    rows = list(reader)
    samples = []
    for row in rows[:5]:
        rendered = {}
        for field, col in active_mapping.items():
            if col is not None:
                rendered[field] = (row.get(col) or "").strip()
        samples.append({"raw": {k: row.get(k, "") for k in headers},
                        "rendered": rendered})
    counts, skipped = {}, 0
    for row in rows:
        norm = normalize_mapped(row, active_mapping)
        if norm is None:
            skipped += 1
            continue
        row_kind, _detail = classify(norm, kind)
        counts[row_kind] = counts.get(row_kind, 0) + 1
    return {"filename": file.filename or "",
            "signature": header_signature(headers),
            "headers": headers,
            "detected_source": source,
            "detection_confidence": confidence,
            "mapping": active_mapping,
            "unmapped_columns": unmapped_columns(headers, active_mapping),
            "has_date": active_mapping.get("date") is not None,
            "has_money": active_mapping.get("amount") is not None or (
                active_mapping.get("price") is not None
                and active_mapping.get("quantity") is not None),
            "suggested_file_kind": suggested_file_kind,
            "file_kind": kind,
            "counts": counts,
            "skipped": skipped,
            "samples": samples}


@router.get("/import/batches", response_model=schemas.Page[schemas.BatchRead])
def list_batches(paging=Depends(pagination), db=Depends(get_db)):
    limit, offset = paging
    total = db.scalar(select(func.count()).select_from(models.ImportBatch)) or 0
    batches = db.scalars(select(models.ImportBatch).order_by(
        models.ImportBatch.id.desc()).limit(limit).offset(offset)).all()
    items = []
    for batch in batches:
        if batch.profile == "Holding":
            committed = batch.staged
        else:
            committed = db.query(models.StagingRow).filter_by(
                batch_id=batch.id, status="merged").count()
        items.append({
            "id": batch.id, "profile": batch.profile, "filename": batch.filename,
            "account_id": batch.account_id, "created_at": batch.created_at,
            "staged": batch.staged, "skipped": batch.skipped,
            "committed": committed, "file_kind": batch.file_kind,
            "status": batch.status, "rolled_back_at": batch.rolled_back_at,
        })
    return {"items": items, "total": total}


@router.get("/import/batches/{id}", response_model=schemas.BatchDetailRead)
def get_batch(id, db=Depends(get_db)):
    b = _get_or_404(db, models.ImportBatch, _as_int(id, "id"))
    counts = dict(db.query(models.StagingRow.status, func.count()).filter_by(
        batch_id=b.id).group_by(models.StagingRow.status).all())
    kinds = dict(db.query(models.StagingRow.row_kind, func.count()).filter_by(
        batch_id=b.id).group_by(models.StagingRow.row_kind).all())
    committed = b.staged if b.profile == "Holding" else counts.get("merged", 0)
    return {"id": b.id, "profile": b.profile, "filename": b.filename,
            "account_id": b.account_id, "created_at": b.created_at,
            "staged": b.staged, "skipped": b.skipped, "committed": committed,
            "by_status": counts,
            "by_kind": kinds, "file_kind": b.file_kind, "mapping": b.mapping,
            "status": b.status, "rolled_back_at": b.rolled_back_at}


@router.post("/import/batches/{id}/rollback")
def rollback_import(id, db=Depends(get_db)):
    from ...services.import_rollback import rollback_batch
    return rollback_batch(db, _as_int(id, "id"))


@router.get("/import/batches/{id}/rows", response_model=schemas.Page[schemas.StagingRowRead])
def batch_rows(id, paging=Depends(pagination), status=None, kind=None, db=Depends(get_db)):
    bid = _as_int(id, "id")
    _get_or_404(db, models.ImportBatch, bid)
    limit, offset = paging
    stmt = select(models.StagingRow).where(models.StagingRow.batch_id == bid)
    total_stmt = select(func.count()).select_from(models.StagingRow).where(
        models.StagingRow.batch_id == bid)
    if status is not None:
        stmt = stmt.where(models.StagingRow.status == status)
        total_stmt = total_stmt.where(models.StagingRow.status == status)
    if kind is not None:
        if kind not in ("spend", "brokerage_cash", "unknown"):
            raise HTTPException(status_code=422, detail="Invalid row kind")
        stmt = stmt.where(models.StagingRow.row_kind == kind)
        total_stmt = total_stmt.where(models.StagingRow.row_kind == kind)
    total = db.scalar(total_stmt) or 0
    items = db.scalars(stmt.order_by(models.StagingRow.id).limit(limit).offset(offset)).all()
    return {"items": items, "total": total}


@router.post("/import/batches/{id}/resolve")
def resolve_row(id, staging_id: int, action="merge", db=Depends(get_db)):
    _get_or_404(db, models.ImportBatch, _as_int(id, "id"))
    if action == "merge":
        t = reconcile.merge_row(db, _as_int(staging_id, "staging_id"))
        return {"ok": True, "transaction_id": t.id}
    if action == "discard":
        reconcile.discard_row(db, _as_int(staging_id, "staging_id"))
        return {"ok": True}
    raise HTTPException(status_code=422, detail="action must be merge or discard")


@router.post("/import/batches/{id}/merge-all")
def merge_all(id, db=Depends(get_db)):
    merged, _skipped = reconcile.merge_batch(db, _as_int(id, "id"))
    return {"ok": True, "merged": merged}


@router.get("/import/batches/{id}/review")
def review_batch(id, db=Depends(get_db)):
    safe, suspects = reconcile.classify_batch(db, _as_int(id, "id"))
    return {"safe_ids": safe, "suspects": suspects,
            "safe": len(safe), "needs_review": len(suspects)}


@router.get("/import/batches/{id}/changes")
def batch_changes(id, db=Depends(get_db)):
    import json
    batch = _get_or_404(db, models.ImportBatch, _as_int(id, "id"))
    mapping = json.loads(batch.mapping or "{}")
    stored = mapping.get("_holding_changes", [])
    imported_symbols = mapping.get("_holding_symbols", {})
    names = {row[0]: row[1] for row in db.query(models.Account.id, models.Account.name).all()}
    current = {(h.account_id, h.symbol.upper()): h.quantity_milli
               for h in db.query(models.Holding).all()}
    changes = []
    for item in stored:
        key = (item["account_id"], item["symbol"])
        changes.append({
            "account_id": item["account_id"],
            "account_name": names.get(item["account_id"], "Unknown account"),
            "symbol": item["symbol"],
            "added": item.get("added", False),
            "previous_quantity_milli": item["previous_quantity_milli"],
            "quantity_milli": item["quantity_milli"],
            "current_quantity_milli": current.get(key),
        })
    missing = []
    for aid_raw, symbols in imported_symbols.items():
        aid = int(aid_raw)
        wanted = set(symbols)
        for (held_aid, symbol), quantity in current.items():
            if held_aid != aid or symbol in wanted:
                continue
            missing.append({
                "account_id": aid,
                "account_name": names.get(aid, "Unknown account"),
                "symbol": symbol,
                "current_quantity_milli": quantity,
            })
    missing.sort(key=lambda item: (item["account_name"], item["symbol"]))
    return {"batch_id": batch.id, "changes": changes, "missing": missing}


@router.post("/import/batches/{id}/remove-missing")
def batch_remove_missing(id, payload: dict, db=Depends(get_db)):
    import json
    batch = _get_or_404(db, models.ImportBatch, _as_int(id, "id"))
    if batch.profile != "Holding":
        raise HTTPException(status_code=422, detail="only holding batches support remove-missing")
    mapping = json.loads(batch.mapping or "{}")
    imported_symbols = mapping.get("_holding_symbols", {})
    wanted = set()
    for entry in payload.get("holdings", []) or []:
        wanted.add((int(entry[0]), str(entry[1]).upper()))
    previous = mapping.get("_holding_previous", [])
    known = {(item["account_id"], item["symbol"]) for item in previous}
    changes = mapping.get("_holding_changes", [])
    holding_keys = {
        (item["account_id"], item["symbol"])
        for item in changes
        if item.get("previous_quantity_milli", 0) > 0
    }
    removed = []
    for aid, symbol in sorted(wanted):
        if symbol in set(imported_symbols.get(str(aid), [])):
            continue
        holding = db.query(models.Holding).filter_by(account_id=aid, symbol=symbol).one_or_none()
        if holding is None:
            continue
        if (aid, symbol) not in known:
            previous.append({
                "account_id": aid, "symbol": symbol, "quantity_milli": holding.quantity_milli,
                "name": holding.name, "price_cents": holding.price_cents,
                "import_batch_id": holding.import_batch_id,
            })
            known.add((aid, symbol))
        if (aid, symbol) not in holding_keys:
            changes.append({
                "account_id": aid, "symbol": symbol,
                "previous_quantity_milli": holding.quantity_milli,
                "quantity_milli": 0,
                "added": False, "removed": True,
            })
            holding_keys.add((aid, symbol))
        db.delete(holding)
        removed.append({"account_id": aid, "symbol": symbol})
    batch.mapping = json.dumps({**mapping, "_holding_previous": previous,
                                "_holding_changes": changes})
    db.commit()
    return {"ok": True, "batch_id": batch.id, "removed": removed}


@router.post("/import/batches/{id}/merge-safe")
def merge_safe(id, db=Depends(get_db)):
    merged, held = reconcile.merge_safe(db, _as_int(id, "id"))
    return {"ok": True, "merged": merged, "held": held}


@router.post("/admin/clear")
def admin_clear(db=Depends(get_db)):
    from ...services.admin import clear_database
    return {"ok": True, "deleted": clear_database(db)}


@router.get("/export/transactions")
def export_transactions(account_id=None, date_from=None, date_to=None, db=Depends(get_db)):
    import csv as csvmod
    import io
    stmt = select(models.Transaction).order_by(models.Transaction.date)
    if account_id is not None:
        stmt = stmt.where(models.Transaction.account_id == _as_int(account_id, "account_id"))
    if date_from is not None:
        stmt = stmt.where(models.Transaction.date >= _as_date(date_from, "date_from"))
    if date_to is not None:
        stmt = stmt.where(models.Transaction.date <= _as_date(date_to, "date_to"))
    cats = {c.id: c.name for c in db.query(models.Category).all()}
    buf = io.StringIO()
    w = csvmod.writer(buf)
    w.writerow(["date", "merchant", "amount", "category", "note"])
    for t in db.scalars(stmt).all():
        w.writerow([t.date.isoformat(), t.merchant, f"{t.amount_cents / 100:.2f}",
                    cats.get(t.category_id, ""), t.note or ""])
    return Response(content=buf.getvalue(), media_type="text/csv")


@router.get("/investments")
def investments(db=Depends(get_db)):
    holdings = db.scalars(select(models.Holding)).all()
    classifications = {
        item.symbol.upper(): item.category
        for item in db.scalars(select(models.InvestmentClassification)).all()
    }
    allocations = {}
    for item in db.scalars(select(models.InvestmentAllocation)).all():
        allocations.setdefault(item.symbol.upper(), {})[item.category] = item.percent_bps / 100
    return {"holdings": [{"id": h.id, "symbol": h.symbol,
                          "name": h.name,
                          "account_id": h.account_id,
                          "account_name": h.account.name if h.account else "Unassigned",
                          "category": classifications.get(h.symbol.upper()),
                          "allocations": allocations.get(h.symbol.upper(), {}),
                          "quantity_milli": h.quantity_milli,
                          "price_cents": h.price_cents} for h in holdings],
            "total_cents": analytics.portfolio_value(db)}


@router.get("/investments/name/{symbol}")
def investment_name(symbol: str, db=Depends(get_db)):
    normalized = symbol.strip().upper()
    holding = db.query(models.Holding).filter(
        func.upper(models.Holding.symbol) == normalized,
        models.Holding.name.isnot(None),
    ).first()
    if holding is not None:
        return {"symbol": normalized, "name": holding.name}
    try:
        name = get_live_name(normalized)
    except QuoteUnavailableError:
        return {"symbol": normalized, "name": None}
    if name:
        db.query(models.Holding).filter(
            func.upper(models.Holding.symbol) == normalized,
        ).update({"name": name}, synchronize_session=False)
        db.commit()
    return {"symbol": normalized, "name": name}


@router.post("/investments", response_model=schemas.HoldingRead)
def create_holding(payload: schemas.HoldingCreate, db=Depends(get_db)):
    if payload.account_id is not None:
        _get_or_404(db, models.Account, payload.account_id)
    data = payload.model_dump()
    try:
        data["price_cents"] = get_live_price(data["symbol"])
    except QuoteUnavailableError as exc:
        if not data.get("price_cents"):
            raise HTTPException(status_code=503, detail=str(exc))
    try:
        data["name"] = get_live_name(data["symbol"])
    except QuoteUnavailableError:
        data["name"] = None
    existing = db.query(models.Holding).filter(
        func.upper(models.Holding.symbol) == data["symbol"].upper(),
        models.Holding.account_id == data["account_id"],
    ).order_by(models.Holding.id).all()
    if existing:
        h = existing[0]
        h.symbol = data["symbol"].upper()
        h.quantity_milli = data["quantity_milli"]
        h.price_cents = data["price_cents"]
        if data.get("name"):
            h.name = data["name"]
        for duplicate in existing[1:]:
            db.delete(duplicate)
    else:
        h = models.Holding(**data)
        db.add(h)
    db.commit(); db.refresh(h)
    return h


@router.patch("/investments/{id}")
def update_holding(id, payload: dict, db=Depends(get_db)):
    holding = _get_or_404(db, models.Holding, _as_int(id, "id"))
    if "quantity_milli" not in payload:
        raise HTTPException(status_code=422, detail="quantity_milli is required")
    try:
        quantity = int(payload["quantity_milli"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="quantity_milli must be an integer")
    if quantity < 0:
        raise HTTPException(status_code=422, detail="quantity_milli cannot be negative")
    if quantity == 0:
        db.delete(holding)
        db.commit()
        return {"ok": True, "deleted": True}
    holding.quantity_milli = quantity
    db.commit()
    db.refresh(holding)
    return {"ok": True, "deleted": False,
            **schemas.HoldingRead.model_validate(holding).model_dump()}


@router.patch("/investments/classification/{symbol}")
def update_investment_classification(symbol: str, payload: dict, db=Depends(get_db)):
    category = payload.get("category")
    if category is not None:
        if not isinstance(category, str) or not category.strip():
            raise HTTPException(status_code=422, detail="Category must be a non-empty string")
        category = category.strip()
        if len(category) > 20:
            raise HTTPException(status_code=422, detail="Category is too long")
    normalized = symbol.strip().upper()
    if not normalized:
        raise HTTPException(status_code=422, detail="Symbol is required")
    classification = db.scalar(select(models.InvestmentClassification).where(
        models.InvestmentClassification.symbol == normalized))
    if category is None:
        if classification is not None:
            db.delete(classification)
    elif classification is None:
        db.add(models.InvestmentClassification(symbol=normalized, category=category))
    else:
        classification.category = category
    db.query(models.InvestmentAllocation).filter(
        models.InvestmentAllocation.symbol == normalized).delete()
    db.commit()
    return {"symbol": normalized, "category": category}


@router.put("/investments/allocation/{symbol}")
def update_investment_allocation(symbol: str, payload: dict, db=Depends(get_db)):
    normalized = symbol.strip().upper()
    allocations = payload.get("allocations")
    if not isinstance(allocations, dict) or not allocations:
        raise HTTPException(status_code=422, detail="Allocations are required")
    cleaned = {}
    for category, percent in allocations.items():
        if not isinstance(category, str) or not category.strip():
            raise HTTPException(status_code=422, detail="Invalid category")
        if percent is None or percent == "":
            value = 0
        else:
            try:
                value = float(percent)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="Percentages must be numeric")
        if not math.isfinite(value) or value < 0 or value > 100:
            raise HTTPException(status_code=422, detail="Percentages must be between 0 and 100")
        if value:
            cleaned[category.strip()] = round(value, 2)
    if abs(sum(cleaned.values()) - 100) > 0.01:
        raise HTTPException(status_code=422, detail="Percentages must total 100")
    db.query(models.InvestmentAllocation).filter(
        models.InvestmentAllocation.symbol == normalized).delete()
    for category, value in cleaned.items():
        db.add(models.InvestmentAllocation(symbol=normalized, category=category,
                                           percent_bps=round(value * 100)))
    db.query(models.InvestmentClassification).filter(
        models.InvestmentClassification.symbol == normalized).delete()
    db.commit()
    return {"symbol": normalized, "allocations": cleaned}


@router.get("/investments/summary")
def investments_summary(db=Depends(get_db)):
    symbols = []
    for holding in db.scalars(select(models.Holding)).all():
        if holding.symbol.upper() not in symbols:
            symbols.append(holding.symbol.upper())

    def _safe_price(symbol):
        try:
            return get_live_price(symbol)
        except QuoteUnavailableError:
            return None

    prices = {}
    if symbols:
        with ThreadPoolExecutor(max_workers=min(8, len(symbols))) as pool:
            prices = dict(zip(symbols, pool.map(_safe_price, symbols)))
    names = {}
    for holding in db.scalars(select(models.Holding)).all():
        symbol = holding.symbol.upper()
        if prices.get(symbol) is not None:
            holding.price_cents = prices[symbol]
        if not holding.name and symbol not in names:
            try:
                names[symbol] = get_live_name(symbol)
            except QuoteUnavailableError:
                names[symbol] = None
        if not holding.name and names.get(symbol):
            holding.name = names[symbol]
    db.commit()
    result = analytics.portfolio_summary(db)
    today = dt.date.today()
    live = {}
    for holding in db.scalars(select(models.Holding)).all():
        key = (holding.account_id, holding.symbol.upper())
        live[key] = holding
        snapshot = db.scalar(select(models.PortfolioSnapshot).where(
            models.PortfolioSnapshot.date == today,
            models.PortfolioSnapshot.account_id == holding.account_id,
            models.PortfolioSnapshot.symbol == holding.symbol.upper()))
        market = (holding.quantity_milli * holding.price_cents) // 1000
        if snapshot is None:
            db.add(models.PortfolioSnapshot(
                date=today, account_id=holding.account_id,
                symbol=holding.symbol.upper(),
                quantity_milli=holding.quantity_milli,
                price_cents=holding.price_cents, market_cents=market))
        else:
            snapshot.quantity_milli = holding.quantity_milli
            snapshot.price_cents = holding.price_cents
            snapshot.market_cents = market
    for stale in db.scalars(select(models.PortfolioSnapshot).where(
            models.PortfolioSnapshot.date == today)).all():
        if (stale.account_id, stale.symbol) not in live:
            db.delete(stale)
    db.commit()
    return result


@router.get("/investments/history")
def investments_history(db=Depends(get_db)):
    points = db.scalars(select(models.PortfolioSnapshot).order_by(
        models.PortfolioSnapshot.date)).all()
    return {"points": [
        {"date": point.date.isoformat(), "account_id": point.account_id,
         "symbol": point.symbol,
         "quantity_milli": point.quantity_milli,
         "price_cents": point.price_cents,
         "market_cents": point.market_cents}
        for point in points
    ]}


@router.post("/transfers/link")
def link_transfer(out_id: int, in_id: int, transfer_id: str, db=Depends(get_db)):
    analytics.link_transfer(db, out_id, in_id, transfer_id)
    return {"ok": True}


@router.get("/transfers/suggestions")
def transfer_suggestions(window_days=3, db=Depends(get_db)):
    return analytics.transfer_suggestions(db, window_days=_as_int(window_days, "window_days"))


@router.get("/rules", response_model=list[schemas.RuleRead])
def list_rules(db=Depends(get_db)):
    return db.query(models.CategoryRule).order_by(models.CategoryRule.priority).all()


@router.post("/rules", response_model=schemas.RuleRead)
def create_rule(payload: schemas.RuleCreate, db=Depends(get_db)):
    _check_pattern(payload.pattern)
    _get_or_404(db, models.Category, payload.category_id)
    r = models.CategoryRule(**payload.model_dump())
    db.add(r); db.commit(); db.refresh(r)
    return r


@router.patch("/rules/{id}", response_model=schemas.RuleRead)
def update_rule(id, payload: schemas.RuleUpdate, db=Depends(get_db)):
    r = _get_or_404(db, models.CategoryRule, _as_int(id, "id"))
    data = payload.model_dump(exclude_unset=True)
    if "pattern" in data:
        _check_pattern(data["pattern"])
    if "category_id" in data:
        _get_or_404(db, models.Category, data["category_id"])
    for k, v in data.items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return r


@router.delete("/rules/{id}")
def delete_rule(id, db=Depends(get_db)):
    r = _get_or_404(db, models.CategoryRule, _as_int(id, "id"))
    db.delete(r)
    db.commit()
    return {"ok": True}

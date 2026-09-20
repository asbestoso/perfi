"""Thin CRUD + domain routes under /api."""
import datetime as dt
import calendar
import math
import re
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_, select

from ... import models, schemas
from ..deps import get_db
from ..pagination import pagination
from ...services import ai_provider, analytics, mcp_server, reconcile, settings_store
from ...services.csv_import import import_csv
from ...services.fingerprint import compute_fingerprint
from ...services.market_data import QuoteUnavailableError, get_live_name, get_live_price
from ...services.ofx_import import import_ofx
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
    db.commit()
    db.refresh(account)
    return account


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


@router.post("/import/ofx")
def ofx_import(file: UploadFile, account_id=None, db=Depends(get_db)):
    aid = None
    if account_id is not None:
        aid = _as_int(account_id, "account_id")
        _get_or_404(db, models.Account, aid)
    return import_ofx(db, aid, file.file.read(), file.filename or "")


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
    items = db.scalars(select(models.ImportBatch).order_by(
        models.ImportBatch.id.desc()).limit(limit).offset(offset)).all()
    return {"items": items, "total": total}


@router.get("/import/batches/{id}", response_model=schemas.BatchDetailRead)
def get_batch(id, db=Depends(get_db)):
    b = _get_or_404(db, models.ImportBatch, _as_int(id, "id"))
    counts = dict(db.query(models.StagingRow.status, func.count()).filter_by(
        batch_id=b.id).group_by(models.StagingRow.status).all())
    kinds = dict(db.query(models.StagingRow.row_kind, func.count()).filter_by(
        batch_id=b.id).group_by(models.StagingRow.row_kind).all())
    return {"id": b.id, "profile": b.profile, "filename": b.filename,
            "account_id": b.account_id, "created_at": b.created_at,
            "staged": b.staged, "skipped": b.skipped, "by_status": counts,
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
        if kind not in ("spend", "brokerage_cash", "trade", "unknown"):
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


@router.post("/import/batches/{id}/merge-safe")
def merge_safe(id, db=Depends(get_db)):
    merged, held = reconcile.merge_safe(db, _as_int(id, "id"))
    return {"ok": True, "merged": merged, "held": held}


@router.post("/import/batches/{id}/approve-trade")
def approve_trade(id, staging_id: int, side=None, db=Depends(get_db)):
    """Approve a staged trade row into an investment order (idempotent).

    Optional side override (buy/sell) corrects a misread suggestion.
    Approving twice, or approving a re-uploaded duplicate, returns the
    same order without moving holdings twice.
    """
    import json
    from ...services.fingerprint import order_fingerprint
    from ...services.funding import auto_link_funding
    from ...services.orders import create_order, find_order
    b = _get_or_404(db, models.ImportBatch, _as_int(id, "id"))
    s = db.get(models.StagingRow, _as_int(staging_id, "staging_id"))
    if s is None or s.batch_id != b.id:
        raise HTTPException(status_code=404, detail="Not found")
    if s.status not in ("pending", "duplicate"):
        raise HTTPException(status_code=409, detail=f"already {s.status}")
    if s.row_kind != "trade":
        raise HTTPException(status_code=422, detail="only trade rows approve as orders")
    try:
        trade = json.loads(s.trade_json or "{}")
    except ValueError:
        trade = {}
    trade_side = side or trade.get("side", "buy")
    if trade_side not in ("buy", "sell"):
        raise HTTPException(status_code=422, detail="Side must be buy or sell")
    if not trade.get("symbol") or not trade.get("quantity_milli") \
            or not trade.get("price_cents"):
        raise HTTPException(status_code=422, detail="trade needs symbol, quantity, and price")
    aid = s.account_id if s.account_id is not None else b.account_id
    if aid is None:
        raise HTTPException(status_code=422, detail="trade needs an account")
    fp = order_fingerprint(aid, trade["symbol"], trade_side,
                           trade["quantity_milli"], trade["price_cents"], 0,
                           s.date)
    existed = find_order(db, fp) is not None
    order = create_order(db, aid, trade["symbol"], trade_side,
                         trade["quantity_milli"], trade["price_cents"], 0,
                         s.date)
    funded_id = None
    if not existed:
        leg = auto_link_funding(db, order)
        funded_id = leg.id if leg is not None else None
        order.import_batch_id = b.id
        db.commit()
    if s.status == "pending":
        s.status = "merged"
        db.commit()
    return {"ok": True, "order_id": order.id, "created": not existed,
            "funded_transaction_id": funded_id}


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


@router.get("/budgets/{month}")
def budgets(month: str, domain=None, db=Depends(get_db)):
    if domain is not None:
        _check_domain_param(domain)
    return analytics.budget_status(db, month, domain)


@router.post("/budgets", response_model=schemas.BudgetRead)
def create_budget(payload: schemas.BudgetCreate, db=Depends(get_db)):
    b = models.Budget(**payload.model_dump())
    db.add(b); db.commit(); db.refresh(b)
    return b


@router.put("/budgets/{id}", response_model=schemas.BudgetRead)
def update_budget(id, payload: schemas.BudgetUpdate, db=Depends(get_db)):
    b = _get_or_404(db, models.Budget, _as_int(id, "id"))
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(b, k, v)
    db.commit()
    db.refresh(b)
    return b


@router.delete("/budgets/{id}")
def delete_budget(id, db=Depends(get_db)):
    b = _get_or_404(db, models.Budget, _as_int(id, "id"))
    db.delete(b)
    db.commit()
    return {"ok": True}


@router.get("/recurring", response_model=schemas.Page[schemas.RecurringRead])
def list_recurring(paging=Depends(pagination), db=Depends(get_db)):
    limit, offset = paging
    total = db.scalar(select(func.count()).select_from(models.Recurring)) or 0
    items = db.scalars(select(models.Recurring).order_by(
        models.Recurring.next_due).limit(limit).offset(offset)).all()
    return {"items": items, "total": total}


@router.post("/recurring/detect")
def detect_recurring(db=Depends(get_db)):
    return analytics.detect_recurring(db)


@router.post("/recurring", response_model=schemas.RecurringRead)
def create_recurring(payload: schemas.RecurringCreate, db=Depends(get_db)):
    r = models.Recurring(**payload.model_dump())
    db.add(r); db.commit(); db.refresh(r)
    return r


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
    prices = {}
    names = {}
    for holding in db.scalars(select(models.Holding)).all():
        symbol = holding.symbol.upper()
        if symbol in prices:
            holding.price_cents = prices[symbol]
            continue
        try:
            holding.price_cents = get_live_price(symbol)
            prices[symbol] = holding.price_cents
        except QuoteUnavailableError:
            continue
        if not holding.name and symbol not in names:
            try:
                names[symbol] = get_live_name(symbol)
            except QuoteUnavailableError:
                names[symbol] = None
        if not holding.name and names.get(symbol):
            holding.name = names[symbol]
    db.commit()
    return analytics.portfolio_summary(db)


@router.get("/investment-orders", response_model=schemas.Page[schemas.OrderRead])
def list_investment_orders(paging=Depends(pagination), db=Depends(get_db)):
    limit, offset = paging
    total = db.scalar(select(func.count()).select_from(models.InvestmentOrder)) or 0
    items = db.scalars(select(models.InvestmentOrder).order_by(
        models.InvestmentOrder.executed_at.desc(),
        models.InvestmentOrder.id.desc()).limit(limit).offset(offset)).all()
    return {"items": items, "total": total}


@router.get("/investment-orders/analysis")
def investment_orders_analysis(db=Depends(get_db)):
    """Order-level trade P&L from raw orders only.

    Buys show purchase cost (qty x price + fees) against the latest
    quote. Sells show proceeds against the average buy price for that
    account + symbol, computed here on the fly. This is display-only
    trade analysis, not tax-lot resolution: nothing is stored.
    """
    orders = db.scalars(select(models.InvestmentOrder).order_by(
        models.InvestmentOrder.executed_at.desc(),
        models.InvestmentOrder.id.desc())).all()
    bought = {}
    for order in orders:
        if order.side != "buy":
            continue
        key = (order.account_id, order.symbol.upper())
        qty, cost = bought.get(key, (0, 0))
        bought[key] = (qty + order.quantity_milli,
                       cost + (order.quantity_milli * order.price_cents) // 1000
                       + (order.fees_cents or 0))
    prices = {}
    items = []
    today = dt.date.today()
    target_month = today.month - 4
    target_year = today.year
    if target_month <= 0:
        target_month += 12
        target_year -= 1
    four_months_ago = dt.date(
        target_year, target_month,
        min(today.day, calendar.monthrange(target_year, target_month)[1]),
    )
    for order in orders:
        symbol = order.symbol.upper()
        if symbol not in prices:
            try:
                prices[symbol] = get_live_price(symbol)
            except QuoteUnavailableError:
                prices[symbol] = order.price_cents
        if order.side == "buy":
            cost = ((order.quantity_milli * order.price_cents) // 1000
                    + (order.fees_cents or 0))
            market_value = (order.quantity_milli * prices[symbol]) // 1000
            gain = market_value - cost
        else:
            market_value = order.proceeds_cents or 0
            qty, total = bought.get((order.account_id, symbol), (0, 0))
            cost = (order.quantity_milli * total) // qty if qty else 0
            gain = market_value - cost
        percent = gain / cost * 100 if cost else 0
        days = max((today - order.executed_at).days, 1)
        annualized = ((1 + gain / cost) ** (365 / days) - 1) * 100 \
            if order.executed_at <= four_months_ago and cost \
            and 1 + gain / cost > 0 else None
        items.append({
            "id": order.id, "account_name": order.account.name,
            "symbol": symbol, "side": order.side,
            "quantity_milli": order.quantity_milli,
            "executed_at": order.executed_at,
            "market_value_cents": market_value,
            "cost_cents": cost,
            "gain_cents": gain,
            "percent": percent,
            "annualized_percent": annualized,
        })
    return {"items": items, "total": len(items)}


@router.post("/investment-orders", response_model=schemas.OrderRead)
def create_investment_order(payload: schemas.OrderCreate, db=Depends(get_db)):
    from ...services.orders import create_order
    return create_order(db, payload.account_id, payload.symbol, payload.side,
                        payload.quantity_milli, payload.price_cents,
                        payload.fees_cents, payload.executed_at,
                        payload.linked_transaction_id)


@router.get("/funded-buys/suggestions")
def funded_buy_suggestions(db=Depends(get_db)):
    from ...services.funding import suggestions
    return suggestions(db)


@router.post("/investment-orders/{id}/link-funding")
def link_order_funding(id, transaction_id=None, db=Depends(get_db)):
    from ...services.funding import link_funding
    tid = None
    if transaction_id is not None:
        tid = _as_int(transaction_id, "transaction_id")
    txn = link_funding(db, _as_int(id, "id"), tid)
    return {"ok": True, "transaction_id": txn.id}


@router.delete("/investment-orders/{id}/link")
def unlink_order(id, db=Depends(get_db)):
    from ...services.funding import unlink_order as do_unlink
    return do_unlink(db, _as_int(id, "id"))


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


@router.get("/reports/{month}")
def reports(month: str, domain=None, db=Depends(get_db)):
    if domain is not None:
        _check_domain_param(domain)
    return {"month": month,
            "spend_by_category": analytics.monthly_spend(db, month, domain),
            "budgets": analytics.budget_status(db, month, domain),
            "net_worth": analytics.net_worth(db)}


@router.get("/reports-trends")
def reports_trends(months=12, domain=None, db=Depends(get_db)):
    try:
        n = int(months)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="months must be an integer")
    if domain is not None:
        _check_domain_param(domain)
    return analytics.monthly_trends(db, n, domain)


@router.get("/reports-category-trends")
def reports_category_trends(months=6, domain=None, db=Depends(get_db)):
    try:
        n = int(months)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="months must be an integer")
    if domain is not None:
        _check_domain_param(domain)
    return analytics.category_trends(db, n, domain)


@router.get("/net-worth-history")
def net_worth_history(db=Depends(get_db)):
    return analytics.net_worth_history(db)


@router.post("/snapshots/run")
def run_snapshot(db=Depends(get_db)):
    return analytics.snapshot_balances(db)


@router.get("/saved-reports", response_model=list[schemas.SavedReportRead])
def list_saved_reports(db=Depends(get_db)):
    return db.query(models.SavedReport).order_by(models.SavedReport.id).all()


@router.post("/saved-reports", response_model=schemas.SavedReportRead)
def create_saved_report(payload: schemas.SavedReportCreate, db=Depends(get_db)):
    import json
    if payload.type not in analytics.REPORT_TYPES:
        raise HTTPException(status_code=422, detail=f"unknown report type: {payload.type}")
    try:
        params = json.dumps(payload.params or {})
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="params must be JSON-serializable")
    r = models.SavedReport(name=payload.name, type=payload.type, params=params)
    db.add(r); db.commit(); db.refresh(r)
    return r


@router.delete("/saved-reports/{id}")
def delete_saved_report(id, db=Depends(get_db)):
    r = _get_or_404(db, models.SavedReport, _as_int(id, "id"))
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.post("/saved-reports/{id}/run")
def run_saved_report(id, db=Depends(get_db)):
    import json
    r = _get_or_404(db, models.SavedReport, _as_int(id, "id"))
    return analytics.run_report(db, r.type, json.loads(r.params or "{}"))


@router.get("/settings/ai", response_model=schemas.AISettingsRead)
def get_ai_settings(db=Depends(get_db)):
    return settings_store.get_ai_config(db)


@router.put("/settings/ai", response_model=schemas.AISettingsRead)
def update_ai_settings(payload: schemas.AISettingsUpdate, db=Depends(get_db)):
    return settings_store.set_ai_config(db, **payload.model_dump(exclude_unset=True))


@router.post("/ai/categorize")
def ai_categorize(limit=20, min_confidence=0.7, db=Depends(get_db)):
    try:
        n = int(limit)
        threshold = float(min_confidence)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="limit must be an integer and min_confidence a number")
    return ai_provider.categorize_uncategorized(db, limit=n, min_confidence=threshold)


@router.post("/mcp")
def mcp_endpoint(payload: dict, request: Request, db=Depends(get_db)):
    if not mcp_server.mcp_enabled():
        raise HTTPException(status_code=404, detail="MCP disabled (set PERFI_MCP_ENABLED=1)")
    want = mcp_server.expected_token()
    if not want:
        raise HTTPException(status_code=503, detail="MCP misconfigured (set PERFI_MCP_TOKEN)")
    got = (request.headers.get("authorization") or "")
    if got != f"Bearer {want}":
        raise HTTPException(status_code=401, detail="bad MCP token")
    out = mcp_server.handle(db, payload)
    if out is None:
        return Response(status_code=202)
    return out

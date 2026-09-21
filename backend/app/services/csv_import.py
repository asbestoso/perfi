"""CSV import into staging: profile normalize + dedupe, user merges after."""
import csv
import io
import json

from sqlalchemy import select

from ..logging_setup import get as get_log
from ..models import (Account, Category, CategoryRule, Holding, ImportAccountMapping,
                      ImportBatch, StagingRow, Transaction)
from .categorization import resolve_category
from .classify import FILE_KINDS, classify
from .fingerprint import compute_fingerprint
from .profiles import PROFILES, normalize_row

log = get_log("import")


def resolve_account(db, name, investing=False):
    name = (name or "").strip() or "Default"
    a = db.query(Account).filter_by(name=name).one_or_none()
    if a is None:
        # New accounts from brokerage-context rows join the investing
        # group so their rows cannot leak into spend. Existing accounts
        # are never moved: the user re-groups them on the Accounts page.
        if investing:
            a = Account(name=name, type="brokerage", domain="investing")
        else:
            a = Account(name=name)
        db.add(a)
        db.flush()
    return a


def norm_merchant(merchant):
    return (merchant or "").strip().casefold()


def fingerprint_keys(db):
    """All fingerprints already staged or posted.

    Posted rows read straight off the indexed fingerprint column;
    staging rows are computed on the fly. Streams instead of
    materializing whole tables.
    """
    keys = set()
    for (fp,) in db.query(Transaction.fingerprint).yield_per(1000):
        if fp is not None:
            keys.add(fp)
    pairs = db.query(StagingRow, ImportBatch.account_id).join(
        ImportBatch, StagingRow.batch_id == ImportBatch.id).filter(
        StagingRow.status != "discarded").yield_per(1000)
    for s, batch_aid in pairs:
        aid = s.account_id if s.account_id is not None else batch_aid
        keys.add(compute_fingerprint(s.date, s.amount_cents, aid, s.merchant))
    return keys


def fold_note_into_match(db, fingerprint, note):
    """Finance-app auto-merge metadata: fill an empty note on the match."""
    if not note:
        return
    t = db.query(Transaction).filter_by(fingerprint=fingerprint).first()
    if t is not None and not t.note:
        t.note = note


def transaction_exists(db, account_id, date, amount_cents, merchant):
    """Merge-time recheck: casefold equality, broader than the fingerprint.

    Catches rows staged before fingerprints existed, so old pending rows
    still cannot post a duplicate.
    """
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


def stage_rows(db, account_id, profile_name, filename, parsed,
               file_kind="mixed", mapping=None):
    if file_kind not in FILE_KINDS:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"unknown file kind: {file_kind}")
    import json as jsonmod
    cats = {c.name: c.id for c in db.scalars(select(Category)).all()}
    cats_by_lower = {n.lower(): n for n in cats}
    unc_id = cats.get("Uncategorized")
    seen = fingerprint_keys(db)
    rules = db.query(CategoryRule).order_by(CategoryRule.priority).all()
    override = None
    if account_id is not None:
        override = db.get(Account, account_id)
        if override is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")
    mapping_json = jsonmod.dumps(mapping or {})
    batch = ImportBatch(profile=profile_name, filename=filename or "",
                        account_id=account_id, file_kind=file_kind,
                        mapping=mapping_json)
    db.add(batch)
    db.flush()
    # First pass: classify so new-account grouping is deterministic (a new
    # account is investing when any of its rows is non-spend, or when the
    # whole file is brokerage-only).
    classified = []
    for p, raw in parsed:
        kind, detail = classify(p, file_kind)
        classified.append((p, raw, kind, detail))
    investing_accounts = set()
    for p, raw, kind, detail in classified:
        name = (p.get("account", "") or "").strip() or "Default"
        if file_kind == "brokerage" or kind in ("brokerage_cash", "trade", "unknown"):
            investing_accounts.add(name)
    staged, skipped, accounts, new_categories = 0, 0, set(), []
    by_kind = {}
    for p, raw, kind, detail in classified:
        name = (p.get("account", "") or "").strip() or "Default"
        acct = override or resolve_account(db, name, name in investing_accounts)
        fp = compute_fingerprint(p["date"], p["amount_cents"], acct.id, p["merchant"])
        dupe = fp in seen
        if dupe:
            fold_note_into_match(db, fp, p["note"])
        seen.add(fp)
        accounts.add(acct.name)
        if batch.account_id is None:
            batch.account_id = acct.id
        tname, tsource = trusted_category(cats_by_lower, p["category"])
        imported_category = (p.get("category") or "").strip()
        if tname is None and imported_category:
            category = Category(name=imported_category)
            db.add(category)
            db.flush()
            cats[category.name] = category.id
            cats_by_lower[category.name.lower()] = category.name
            tname, tsource = category.name, "import"
            new_categories.append(category.name)
        if tname is None:
            tname, tsource = resolve_category(db, p["merchant"], rules)
        txn_kind = detail.get("transaction_kind") or (
            "income" if p["amount_cents"] > 0 else "expense")
        trade_json = "{}"
        if kind == "trade":
            import json as _json
            trade_json = _json.dumps({
                "symbol": p.get("symbol") or "",
                "quantity_milli": p.get("quantity_milli") or 0,
                "price_cents": p.get("price_cents") or 0,
                "side": detail.get("side", "buy"),
            })
        # Exact dupes are held as duplicate rows for review, never silently
        # dropped: the user discards them or force-merges (keep both).
        # Trades and unknown rows never merge into transactions; they wait
        # for trade approval or review on the Import page.
        db.add(StagingRow(batch_id=batch.id, account_id=acct.id,
                          date=p["date"], merchant=p["merchant"],
                          amount_cents=p["amount_cents"],
                          category_id=cats.get(tname, unc_id),
                          category_source=tsource, note=p["note"] or None,
                          status="duplicate" if dupe else "pending",
                          row_kind=kind, transaction_kind=txn_kind,
                          row_detail=detail.get("reason", "") or (
                              f"suggested {detail['side']}" if kind == "trade" else ""),
                          trade_json=trade_json,
                          raw=json.dumps(raw, default=str)))
        staged += 1
        by_kind[kind] = by_kind.get(kind, 0) + 1
    batch.staged, batch.skipped = staged, skipped
    db.commit()
    db.refresh(batch)
    log.info(f"batch {batch.id} ({profile_name} {filename or '-'} "
             f"{file_kind}): staged={staged} skipped={skipped} "
             f"by_kind={by_kind} accounts={sorted(accounts)}")
    return {"batch_id": batch.id, "staged": staged, "skipped": skipped,
            "accounts": sorted(accounts), "new_categories": new_categories,
            "file_kind": file_kind, "by_kind": by_kind}


def import_csv(db, account_id, raw, profile="generic", filename="",
               file_kind="mixed", mapping=None):
    if profile not in PROFILES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"unknown profile: {profile}")
    from .classify import normalize_mapped
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if profile == "Holding":
        return import_holdings(db, account_id, reader, filename, mapping)
    parsed, skipped = [], 0
    for row in reader:
        if mapping:
            norm = normalize_mapped(row, mapping)
        else:
            norm = normalize_row(profile, row)
            if norm is not None:
                norm = dict(norm, symbol="", quantity_milli=None,
                            price_cents=None, code="")
        if norm is None:
            skipped += 1
            continue
        parsed.append((norm, row))
    result = stage_rows(db, account_id, profile, filename, parsed,
                        file_kind, mapping)
    result["skipped"] += skipped
    db.query(ImportBatch).filter_by(id=result["batch_id"]).update(
        {"skipped": result["skipped"]}, synchronize_session=False)
    db.commit()
    return result


def import_holdings(db, account_id, reader, filename, mapping=None):
    from fastapi import HTTPException
    mapping = mapping or {}
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=422, detail="holding CSV is empty")
    excluded_accounts = set(mapping.get("excluded_accounts", []))
    excluded_rows = {int(value) for value in mapping.get("excluded_rows", [])}
    active_rows = [
        row for index, row in enumerate(rows)
        if index not in excluded_rows
        and (row.get(mapping.get("account", "Account")) or "").strip()
        not in excluded_accounts
    ]
    labels = sorted({(row.get(mapping.get("account", "Account")) or "").strip()
                     for row in active_rows})
    labels = [label for label in labels if label]
    live_ids = {row[0] for row in db.query(Account.id).all()}
    saved = {
        item.external_label: item.account_id
        for item in db.query(ImportAccountMapping).filter_by(profile="Holding").all()
        if item.account_id in live_ids
    }
    unresolved = []
    resolved = {}
    for label in labels:
        target = account_id or saved.get(label)
        if target is None:
            unresolved.append(label)
        else:
            if db.get(Account, target) is None:
                raise HTTPException(status_code=422, detail=f"unknown account id for {label}")
            resolved[label] = target
    supplied = mapping.get("accounts", {})
    for label, target in supplied.items():
        if label in labels:
            target = int(target)
            if db.get(Account, target) is None:
                raise HTTPException(status_code=422, detail=f"unknown account id for {label}")
            resolved[label] = target
            if label in unresolved:
                unresolved.remove(label)
    if unresolved:
        raise HTTPException(status_code=409, detail={
            "message": "account mapping required",
            "accounts": unresolved,
            "available_accounts": [
                {"id": a.id, "name": a.name}
                for a in db.query(Account).order_by(Account.name).all()
            ],
        })
    batch = ImportBatch(profile="Holding", filename=filename or "",
                        file_kind="brokerage", mapping=json.dumps(mapping))
    db.add(batch)
    db.flush()
    changed = 0
    seen = set()
    previous = []
    saved_mappings = {}
    for row in active_rows:
        label = (row.get(mapping.get("account", "Account")) or "").strip()
        symbol = (row.get(mapping.get("symbol", "Holding")) or "").strip().upper()
        quantity_raw = (row.get(mapping.get("quantity", "Quantity")) or "").strip()
        if not label or not symbol or not quantity_raw:
            raise HTTPException(status_code=422, detail="holding rows require Account, Holding, and Quantity")
        try:
            quantity = round(float(quantity_raw.replace(",", "")) * 1000)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"invalid quantity for {symbol}")
        if quantity < 0:
            raise HTTPException(status_code=422, detail=f"negative quantity for {symbol}")
        aid = resolved[label]
        key = (aid, symbol)
        if key in seen:
            raise HTTPException(status_code=422, detail=f"duplicate holding row for {label} / {symbol}")
        seen.add(key)
        holding = db.query(Holding).filter_by(account_id=aid, symbol=symbol).one_or_none()
        if holding is None:
            holding = Holding(account_id=aid, symbol=symbol, quantity_milli=quantity,
                              import_batch_id=batch.id)
            db.add(holding)
        else:
            previous.append({
                "account_id": aid, "symbol": symbol, "quantity_milli": holding.quantity_milli,
                "name": holding.name, "price_cents": holding.price_cents,
                "import_batch_id": holding.import_batch_id,
            })
            holding.quantity_milli = quantity
            holding.import_batch_id = batch.id
        changed += 1
        if label in saved_mappings:
            continue
        saved_mappings[label] = True
        existing = db.query(ImportAccountMapping).filter_by(
            profile="Holding", external_label=label).one_or_none()
        if existing is None:
            db.add(ImportAccountMapping(profile="Holding",
                                        external_label=label, account_id=aid))
        else:
            existing.account_id = aid
    batch.mapping = json.dumps({**mapping, "_holding_previous": previous})
    batch.staged = len(active_rows)
    batch.skipped = len(rows) - len(active_rows)
    db.commit()
    return {"batch_id": batch.id, "staged": len(active_rows), "updated": changed,
            "skipped": len(rows) - len(active_rows), "accounts": sorted(labels),
            "file_kind": "brokerage", "by_kind": {"holding": len(active_rows)}}

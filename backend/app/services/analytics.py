"""Investments and transfers (Ledgr port, simplified)."""
from sqlalchemy import select

from ..logging_setup import get as get_log
from ..models import Account, Holding, Transaction

log = get_log("analytics")


def portfolio_value(db):
    total = 0
    for h in db.scalars(select(Holding)).all():
        total += (h.quantity_milli * h.price_cents) // 1000
    return total


def portfolio_summary(db):
    """Holdings-only positions: quantity and market value per symbol.

    Trades live separately in investment_orders; the summary never
    carries cost or gain (no tax lots).
    """
    holdings = {}
    for holding in db.scalars(select(Holding)).all():
        sym = holding.symbol.upper()
        position = holdings.setdefault(sym, {"name": holding.name, "quantity_milli": 0, "market_cents": 0,
                                             "accounts": {}})
        if not position["name"] and holding.name:
            position["name"] = holding.name
        position["quantity_milli"] += holding.quantity_milli
        position["market_cents"] += (holding.quantity_milli * holding.price_cents) // 1000
        account_id = holding.account_id
        account_name = holding.account.name if holding.account is not None else "Unassigned"
        account = position["accounts"].setdefault(
            account_id, {"account_id": account_id, "name": account_name,
                         "quantity_milli": 0})
        account["quantity_milli"] += holding.quantity_milli
    positions, market_total = [], 0
    for sym in sorted(holdings):
        holding = holdings[sym]
        qty, market = holding["quantity_milli"], holding["market_cents"]
        price = (market * 1000) // qty if qty else 0
        market_total += market
        positions.append({"symbol": sym, "name": holding["name"],
                          "quantity_milli": qty,
                          "price_cents": price, "market_cents": market,
                          "accounts": list(holding["accounts"].values())})
    return {"positions": positions, "market_cents": market_total}


def transfer_suggestions(db, window_days=3, limit=50):
    """Candidate transfer pairs: opposite signs, same abs amount, close dates,
    different accounts, neither already linked."""
    rows = db.query(Transaction).filter(
        Transaction.transfer_id.is_(None)).order_by(Transaction.date.desc()).limit(2000).all()
    used = set()
    out = []
    for i, a in enumerate(rows):
        if a.id in used or not a.amount_cents:
            continue
        for b in rows[i + 1:]:
            if len(out) >= limit:
                return out
            if b.id in used or a.account_id == b.account_id:
                continue
            if a.amount_cents != -b.amount_cents:
                continue
            if abs((a.date - b.date).days) > int(window_days):
                continue
            out_tx = a if a.amount_cents < 0 else b
            in_tx = b if a.amount_cents < 0 else a
            used.add(a.id)
            used.add(b.id)
            out.append({"out_id": out_tx.id, "in_id": in_tx.id,
                        "amount_cents": abs(a.amount_cents),
                        "date": max(a.date, b.date).isoformat(),
                        "outgoing": {
                            "merchant": out_tx.merchant,
                            "date": out_tx.date.isoformat(),
                            "amount_cents": out_tx.amount_cents,
                            "account": db.get(Account, out_tx.account_id).name,
                        },
                        "incoming": {
                            "merchant": in_tx.merchant,
                            "date": in_tx.date.isoformat(),
                            "amount_cents": in_tx.amount_cents,
                            "account": db.get(Account, in_tx.account_id).name,
                        },
                        "confidence": "high"})
            break
    return out


def link_transfer(db, out_id, in_id, transfer_id):
    for tid in (out_id, in_id):
        txn = db.get(Transaction, tid)
        if txn is not None:
            txn.transfer_id = transfer_id
    db.commit()

"""Minimal MCP server (Streamable HTTP, plain JSON-RPC) over the local DB.

No MCP SDK: the streamable-HTTP transport is JSON-RPC POSTs, so a small
dispatcher suffices for a single-user local app.

Gates (env):
  PERFI_MCP_ENABLED=1        expose POST /api/mcp at all
  PERFI_MCP_TOKEN=<secret>   required bearer token (no token -> 503)
  PERFI_MCP_WRITE_ENABLED=1  register the write tools; otherwise read-only
"""
import os

from ..logging_setup import get as get_log

log = get_log("mcp")

PROTOCOL_VERSION = "2024-11-05"


def mcp_enabled():
    return os.environ.get("PERFI_MCP_ENABLED") == "1"


def expected_token():
    return os.environ.get("PERFI_MCP_TOKEN", "")


def write_enabled():
    return os.environ.get("PERFI_MCP_WRITE_ENABLED") == "1"


def _accounts(db, args):
    from ..models import Account
    return [{"id": a.id, "name": a.name, "type": a.type,
             "balance_cents": a.balance_cents}
            for a in db.query(Account).order_by(Account.id).all()]


def _account_summary(db, args):
    from sqlalchemy import func, select
    from ..models import Account
    rows = db.execute(select(Account.type, func.sum(Account.balance_cents),
                             func.count())).group_by(Account.type).all()
    return {"by_type": [{"type": t, "balance_cents": b, "count": n}
                        for t, b, n in rows],
            "total_cents": sum(b for _, b, _ in rows)}


def _transactions(db, args):
    from ..models import Transaction
    q = db.query(Transaction).order_by(Transaction.date.desc())
    if args.get("account_id") is not None:
        q = q.filter_by(account_id=int(args["account_id"]))
    if args.get("category_id") is not None:
        q = q.filter_by(category_id=int(args["category_id"]))
    if args.get("month"):
        q = q.filter(Transaction.date.like(args["month"] + "%"))
    if args.get("q"):
        like = f"%{args['q']}%"
        q = q.filter(Transaction.merchant.ilike(like))
    limit = max(1, min(int(args.get("limit", 50)), 500))
    return [{"id": t.id, "account_id": t.account_id, "category_id": t.category_id,
             "amount_cents": t.amount_cents, "merchant": t.merchant,
             "date": t.date.isoformat(), "category_source": t.category_source}
            for t in q.limit(limit).all()]


def _budget(db, args):
    from . import analytics
    from ..models import Budget
    month = args.get("month")
    if not month:
        import datetime as dt
        month = dt.date.today().strftime("%Y-%m")
    out = analytics.budget_status(db, month)
    if args.get("category_id") is not None:
        out = [b for b in out if b["category_id"] == int(args["category_id"])]
    return {"month": month, "budgets": out}


def _spending_report(db, args):
    from . import analytics
    month = args.get("month")
    if not month:
        import datetime as dt
        month = dt.date.today().strftime("%Y-%m")
    cats = {c.id: c.name for c in db.query(analytics.Category).all()}
    rows = analytics.monthly_spend(db, month)
    return {"month": month,
            "by_category": [{"category_id": r["category_id"],
                             "category": cats.get(r["category_id"], "?"),
                             "total_cents": r["total_cents"]} for r in rows]}


def _income_vs_expense(db, args):
    from . import analytics
    return analytics.monthly_trends(db, int(args.get("months", 12)))


def _net_worth_history(db, args):
    from . import analytics
    return analytics.net_worth_history(db)


def _upcoming_bills(db, args):
    from ..models import Recurring
    return [{"id": r.id, "name": r.name, "amount_cents": r.amount_cents,
             "cadence": r.cadence, "next_due": r.next_due.isoformat()}
            for r in db.query(Recurring).order_by(Recurring.next_due).all()]


def _holdings(db, args):
    from . import analytics
    return analytics.portfolio_summary(db)


def _dashboard(db, args):
    from . import analytics
    import datetime as dt
    month = dt.date.today().strftime("%Y-%m")
    net = analytics.net_worth(db)
    trends = analytics.monthly_trends(db, 3)
    return {"month": month, "net_worth": net,
            "recent_trend": trends[-1] if trends else None,
            "budgets": analytics.budget_status(db, month)}


def _update_category(db, args):
    from ..models import Transaction
    t = db.get(Transaction, int(args["transaction_id"]))
    if t is None:
        raise ValueError("transaction not found")
    t.category_id = int(args["category_id"])
    t.category_source = "manual"
    db.commit()
    return {"ok": True, "id": t.id}


def _set_budget(db, args):
    from ..models import Budget
    b = db.query(Budget).filter_by(category_id=int(args["category_id"]),
                                   month=args["month"]).one_or_none()
    if b is None:
        b = Budget(category_id=int(args["category_id"]), month=args["month"],
                   limit_cents=int(args["limit_cents"]))
        db.add(b)
    else:
        b.limit_cents = int(args["limit_cents"])
    db.commit()
    return {"ok": True, "id": b.id}


READ_TOOLS = {
    "list_accounts": ("Linked accounts and balances", _accounts),
    "get_account_summary": ("Balance totals by account type", _account_summary),
    "get_transactions": ("Search and filter transactions", _transactions),
    "get_budget": ("Budget progress for a month", _budget),
    "get_spending_report": ("Spending breakdown for a month", _spending_report),
    "get_income_vs_expense": ("Income vs expense per month", _income_vs_expense),
    "get_net_worth_history": ("Net worth snapshots over time", _net_worth_history),
    "get_upcoming_bills": ("Recurring transactions ordered by due date", _upcoming_bills),
    "get_holdings": ("Investment positions with cost and gain", _holdings),
    "get_dashboard_summary": ("Net worth, recent trend, current budgets", _dashboard),
}

WRITE_TOOLS = {
    "update_transaction_category": ("Recategorize a transaction (source becomes manual)", _update_category),
    "set_budget_category": ("Create or update a month budget for a category", _set_budget),
}


def tool_table():
    table = dict(READ_TOOLS)
    if write_enabled():
        table.update(WRITE_TOOLS)
    return table


def _result(id, result):
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _error(id, code, message):
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def handle(db, payload):
    method = (payload or {}).get("method", "")
    id = (payload or {}).get("id")
    params = (payload or {}).get("params", {}) or {}
    if method == "initialize":
        return _result(id, {"protocolVersion": PROTOCOL_VERSION,
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "perfi", "version": "0.1.0"}})
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        table = tool_table()
        return _result(id, {"tools": [
            {"name": n, "description": d,
             "inputSchema": {"type": "object"}} for n, (d, _) in table.items()]})
    if method == "tools/call":
        name = params.get("name", "")
        table = tool_table()
        if name not in table:
            log.warning(f"tool call unknown: {name}")
            return _error(id, -32601, f"unknown tool: {name}")
        try:
            data = table[name][1](db, params.get("arguments", {}) or {})
        except (ValueError, KeyError) as e:
            log.warning(f"tool call {name}: bad args: {e}")
            return _error(id, -32602, f"invalid arguments: {e}")
        except Exception as e:
            log.exception(f"tool call {name} failed")
            return _error(id, -32603, f"tool failed: {e}")
        import json
        log.info(f"tool call {name} ok")
        return _result(id, {"content": [{"type": "text", "text": json.dumps(data)}]})
    return _error(id, -32601, f"unknown method: {method}")

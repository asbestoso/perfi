# Architecture

Single-user, local-only personal finance app. No auth, no Docker, no Postgres.

## Stack

- **Backend**: FastAPI (Python, no type hints by convention — see AGENTS.md),
  SQLite in WAL mode at `data/perfi.db`, SQLAlchemy 2 style with plain `Column`
  (not `mapped_column`, so models stay annotation-free). Alembic, single
  revision (`51171a03795c`). Migrations must stay at one squashed file; see
  `docs/operations.md`.
- **Frontend**: React 18 + React Router + Tailwind v4 + Recharts, built with
  Vite. Dev on `:5173` proxied to the API; `npm run build` is the only check
  (no tsc gate — typescript is not installed).
- **Money**: integer cents everywhere (`services/money.py`). Frontend converts
  dollars↔cents at the form boundary.

## Request flow

`main.py` (logging middleware + lifespan startup: migrate → seed) →
`api/routes/api.py` (one router file, `response_model` on reads) →
`services/` domain logic → `models.py`. Pydantic `schemas.py` splits
Read/Create/Update. Pagination helper caps `limit` at 500 (default 100).

## Core domain: stage → reconcile → ledger

CSV uploads never write transactions directly. They create an
`ImportBatch` + `StagingRow`s (`services/csv_import.py`), the user reviews the
queue on the Import page, and merging (`services/reconcile.py`) inserts
`Transaction`s.

- **Intake gate**: `POST /api/import/scan` dry-runs a CSV (detection +
  proposed mapping + samples + per-kind counts, zero writes). New header
  layouts confirm mapping + file kind (Mixed / Brokerage only / Spending
  only) on the Import page; known layouts reuse the remembered mapping
  from localStorage. Headers match by normalized alias
  (`services/profiles.py`), not exact strings.
- **Row kinds**: every staged row is `spend`, `brokerage_cash`, `trade`,
  or `unknown` (`services/classify.py`, mode-gated by the batch's
  file_kind). Spend and brokerage cash merge normally (cash rows carry a
  capital-flow kind); trades and unknowns never merge — trades approve
  into orders, unknowns wait for review or discard.
- **New accounts**: brokerage-context rows create investing-group
  accounts; existing accounts are never re-grouped by import.
- **Trade approval**: `POST .../approve-trade` creates the order and
  moves the holding via `services/orders.py`, idempotent on an order
  fingerprint (double approval and re-uploads collapse to the same
  order).
- **Funded buys**: `services/funding.py` links a checking→brokerage
  deposit to the buy it funded on exact principal match inside 14 days
  (auto on approval when unambiguous, suggestions + explicit link
  otherwise, undo via `DELETE /investment-orders/{id}/link`).

- **Fingerprint** (`services/fingerprint.py`, stored + indexed on
  `transactions.fingerprint`): sha256 of account + date + signed amount +
  tightly normalized merchant. Exact hits stage as `duplicate` rows held for
  review (never silently dropped) and fill an empty note on the existing row;
  the user discards them or force-merges (keep both). Merge time re-checks
  pending rows with broader casefold equality (409s) so pre-fingerprint rows
  stay safe. `skipped` now counts only unparseable rows.
- **Merge-safe** (`GET .../review`, `POST .../merge-safe`): auto-merges rows
  with no candidates and holds only obvious near-dupes — same date + amount
  with an equal/containing merchant — as `pending` with reasons.
  `merge-all` stays the force path (merges everything but exact dupes).
- **Categorization tiers**: trusted file category → regex rules
  (`CategoryRule`, seed patterns in `categorization.py`) → BYOK AI (last tier,
  never overwrites `manual`) → Uncategorized.
- **Transfers**: opposite-sign same-amount pairs across accounts link via
  `transfer_id`; linked rows are excluded from spend/analytics. Suggestions at
  `GET /api/transfers/suggestions`, shown on the Transactions page.
- **Budgets**: per-category monthly limits with Monarch-style flexible
  rollover; `budget_status` returns limit/spent/remaining/pace per row.
- **Investments**: holdings and trades are separate. `Holding`s carry live
  price/qty and are moved by orders; `InvestmentOrder`s record raw
  buy/sell trades (price, fees, proceeds) with no tax-lot resolution —
  sells validate against holding quantity only. The summary is
  holdings-only (positions + market value, no cost/gain); trade analysis
  computes sell P&L against the on-the-fly average buy price. Orders may
  link one cash `Transaction` via `linked_transaction_id`; the linked
  leg gets `transfer_id=order:<id>` so it leaves spend totals.
- **Domains**: every `Account` has a `domain` (`spending` | `investing` |
  `mixed`; backfilled from type, user-overridable). Spend queries
  (`month_spent`, `monthly_spend`, `monthly_trends`, `category_trends`,
  `budget_status`, `detect_recurring`) exclude investing-domain accounts by
  default and accept `domain=` (`spending` view, a single domain, or `all`).
  A second axis, `Transaction.transaction_kind` (`expense`, `income`,
  `investment_contribution`, `investment_distribution`), keeps capital flows
  out of spend even when the domain is widened.
- **Net worth**: cash sums `spending` + `mixed` balances only — investing
  accounts contribute via holdings (`portfolio_value`), never via balance,
  so the two sides can't double-count. `POST /api/snapshots/run` records
  the same split; history chart needs at least one snapshot — nothing is
  scheduled.

## Secrets

AI API key is Fernet-encrypted at rest. Key resolution: `PERFI_ENCRYPTION_KEY`
env, else `data/.ai_key` (0600, auto-created, gitignored). Losing it orphans
the stored key.

## Frontend map

`main.tsx` owns nav + the `api()` helper (throws on non-2xx, parses JSON).
The sidebar groups links into Overview / Spending / Investing / Manage
(top bar stays flat). `pages/_shared.tsx` owns `Page`, `Card`, `useGet`,
`dollars`, input/button classes. Pages are otherwise independent; after a
mutation they bump a `tick` state appended to the query string to refetch
(same pattern as Import). Dashboard is the combined overview (net worth +
spending + portfolio cards with drill links); Import has Activity /
Brokerage tabs; Reports and Transactions carry a Group (domain) selector
and saved reports store `params.domain`.

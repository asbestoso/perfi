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

CSV/OFX uploads never write transactions directly. They create an
`ImportBatch` + `StagingRow`s (`services/csv_import.py`), the user reviews the
queue on the Import page, and merging (`services/reconcile.py`) inserts
`Transaction`s.

- **Fingerprint** (`services/fingerprint.py`, stored + indexed on
  `transactions.fingerprint`): sha256 of account + date + signed amount +
  tightly normalized merchant. Exact hits skip at stage time (streamed,
  `yield_per`) and fill an empty note on the existing row; merge time
  re-checks with broader casefold equality (409s) so pre-fingerprint rows
  stay safe. Re-uploading a file skips everything already staged or posted.
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
- **Investments**: `Holding`s carry live price/qty; `InvestmentLot`s carry tax
  lots. Lots CSV import is idempotent on (symbol, qty, cost, acquired) and
  rejects missing cost basis instead of defaulting $0.
- **Snapshots**: `POST /api/snapshots/run` records cash/investments/net-worth;
  history chart needs at least one snapshot — nothing is scheduled.

## Secrets

AI API key is Fernet-encrypted at rest. Key resolution: `PERFI_ENCRYPTION_KEY`
env, else `data/.ai_key` (0600, auto-created, gitignored). Losing it orphans
the stored key. MCP is reads-first behind `PERFI_MCP_*` gates; Bearer compared
with `hmac.compare_digest`.

## Frontend map

`main.tsx` owns nav + the `api()` helper (throws on non-2xx, parses JSON).
`pages/_shared.tsx` owns `Page`, `Card`, `useGet`, `dollars`, input/button
classes. Pages are otherwise independent; after a mutation they bump a `tick`
state appended to the query string to refetch (same pattern as Import).

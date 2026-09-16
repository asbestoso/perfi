# Decisions & gotchas

Standing constraints: local-only (no Docker/Postgres), single user (no auth),
CSV-first import, flexible rollover, BYOK AI as last categorization tier that
never overwrites manual labels, reads-first MCP. Python stays hint-free.

## 2026-09-04 — review fixes (HIGHs fixed, MEDIUMs deferred)

- Transaction create/update 404 on unknown account/category instead of 500.
- Dedupe key is account-aware with normalized merchants; merge re-checks
  (single 409s, merge-all skips + logs, response shape unchanged).
- Lots import idempotent; missing cost is an explicit logged skip, explicit
  `$0` still imports. Every skip logs line + reason.
- `GET /api/import/batches/{id}` has `response_model=BatchDetailRead`
  (`BatchRead` + `by_status`); response now includes `created_at`.
- Deferred (MEDIUM, still open): unbounded export `.all()`, unbounded
  `file.file.read()` on imports, MCP token `!=` → `hmac.compare_digest`.

## 2026-09-04 — encryption key path bug

`encryption.py` copy-pasted `database.py`'s 3-dirname idiom one level too
deep, so the key landed in `backend/data/.ai_key` instead of `data/.ai_key`
— and the stray file was committed. Fixed to share `REPO_ROOT`, hardened the
loader (empty file regenerates, corrupt non-empty raises a restore-or-delete
error instead of a raw Fernet 500), removed the stray file, untracked it.
If `backend/data/` reappears, a path helper regressed.

## 2026-09-04 — fixture anonymized, dev DB cleared

Ground-truth fixture pseudonymized (see `docs/testing.md`); dev DB wiped
after it held a real import. Session tool-output artifacts holding real rows
were deleted; the live session log itself was left alone.

## Older gotchas (from worklog, still true)

- `api.py` import depth, `Mapped` vs `Column` (plain `Column` + explicit
  `nullable=False`), CWD-relative DB fixed via absolute `REPO_ROOT`.
- SQLite batch mode for FK/unique rewrites; `monthly_trends` truthiness fix.
- `disable_existing_loggers=False` or uvicorn eats app logs on reload.
- Same-name accounts across institutions merge by name on import — by design
  for now, flagged as a merge risk, not fixed.
- Category seed-mapping for Monarch names is still manual; snapshot
  scheduling is manual (`POST /api/snapshots/run`); bank sync is a non-goal.

## 2026-09-16 — mixed-file import rework

- Intake is scan-then-confirm: unknown layouts stage nothing until the
  user confirms mapping + file kind; remembered layouts (localStorage,
  keyed by header signature) skip confirmation with a Change affordance.
- Classification is mode-gated (Mixed / Brokerage only / Spending only),
  not one confidence-ranked classifier: brokerage-only skips spend
  entirely, spending-only diverts trade-shaped rows to review. Unknown
  Trans Codes fail safe to `unknown` review rows; the code table
  (`CASH_CODES`) grows one line per new cash activity.
- Order creation moved verbatim into `services/orders.py` (API + approval
  share it) and gained fingerprint idempotency; re-uploads and double
  approvals return the same order without touching lots.
- Funded-buy auto-link needs an exact principal match, one candidate, 14
  days. `DELETE /investment-orders/{id}/link` reverses every `order:*`
  mark — closing the "no unlink yet" gap from the domain-separation entry.
- Repair migration `b8c9d0e1f2a3`: the f6 revision file grew new columns
  after app-startup auto-migrate had already stamped it on the dev DB, so
  a follow-up revision applies the difference. Lesson: treat a migration
  file as frozen once any environment may have run it — new columns mean
  a new revision.

## 2026-09-16 — spending/investing domain separation

- `Account.domain` (`spending` | `investing` | `mixed`) is the separation
  axis; migration `d4e5f6a7b8c9` backfills investing from type
  (`brokerage`, `401k`, `roth`, `traditional ira`, `hsa`, `529`).
  `Transaction.transaction_kind` (`expense`, `income`,
  `investment_contribution`, `investment_distribution`) is the second axis:
  capital flows stay out of spend even under `domain=all`.
- Spend analytics exclude investing-domain accounts by default; report and
  trend endpoints accept `domain=` (single domain or `all`), and saved
  reports persist it in `params.domain`. Net-worth cash sums spending+mixed
  balances; investing accounts count via holdings only.
- `GET /api/accounts` keeps holdings-derived balances for every account
  with holdings: `test_accounts_balance_is_derived_from_holdings` pins that
  behavior (a Checking account with holdings shows market value), so domain
  governs analytics, not the accounts display.
- Orders link one cash leg via `linked_transaction_id` (`e5f6a7b8c9d0`);
  the leg is marked `transfer_id=order:<id>` so existing spend/recurring
  exclusions pick it up. No mirror posting, no unlink endpoint yet — a
  linked leg stays marked if the order is deleted (follow-up if needed).

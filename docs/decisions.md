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

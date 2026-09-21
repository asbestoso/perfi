# perfi — single-user local personal finance app


## Quickstart

```bash
./scripts/dev.sh        # backend :8000 + frontend :5173
# or manually:
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --port 8000 --app-dir backend
cd frontend && npm install && npm run dev
```

API: `http://localhost:8000/api/health`, docs at `/docs`.
SQLite file: `data/perfi.db` (WAL, auto-created + seeded on startup).

## Layout

- `backend/app/` — FastAPI app: `main.py`, `config.py`, `database.py`,
  `models.py`, `schemas.py`, `seed.py`, `api/` routes, `services/` domain logic
- `frontend/` — Vite + React pages: Dashboard, Transactions, Accounts,
  Investments, Import, Settings
- `data/` — local SQLite dir (gitignored db files)
- `scripts/dev.sh` — runs backend + frontend concurrently

## Domain logic (ported from Ledgr, simplified)

- **Cents money**: all amounts stored as INTEGER cents (`services/money.py`).
- **Import flow**: CSV/OFX stages rows into a review queue; merging posts
  transactions. Identity is a persisted sha256 fingerprint (account + date +
  signed amount + normalized merchant); Merge-safe auto-posts clean rows and
  holds only obvious near-dupes for review (`fingerprint.py`, `reconcile.py`).
- **Categorization tiers**: trusted file category -> regex rules ->
  builtin merchant patterns -> Uncategorized.
- **Investments**: holdings (symbol, qty, price cents) + market value.
- **Transfers**: paired transactions linked by `transfer_id` (excluded from spend).

## Configuration (env)

| Variable | Default | Purpose |
|----------|---------|---------|
| `PERFI_LOG_LEVEL` | INFO | Log verbosity (DEBUG for full request + domain logs) |

## Docs

- `docs/architecture.md` — stack, request flow, domain concepts
- `docs/operations.md` — dev servers, ports, logging, DB, migrations, gitignore
- `docs/testing.md` — suite, anonymized ground-truth fixture, frontend checks
- `docs/decisions.md` — standing constraints, fixes, open risks

Use `http://localhost:5173` for the UI (not `127.0.0.1` — see operations).
Test data in the repo is anonymized by policy; never commit real exports,
`data/` contents, or key files.

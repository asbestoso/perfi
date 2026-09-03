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
- `frontend/` — Vite + React pages: Dashboard, Transactions, Accounts, Budgets,
  Recurring, Investments, Import, Reports, Settings
- `data/` — local SQLite dir (gitignored db files)
- `scripts/dev.sh` — runs backend + frontend concurrently

## Domain logic (ported from Ledgr, simplified)

- **Cents money**: all amounts stored as INTEGER cents (`services/money.py`).
- **Import flow**: CSV/OFX stages rows into a review queue; merging posts
  transactions. Dedupe key is account + date + amount + normalized merchant,
  enforced at stage and re-checked at merge (`csv_import.py`, `reconcile.py`).
- **Categorization tiers**: trusted file category -> regex rules ->
  BYOK AI (last tier, never overwrites manual) -> Uncategorized.
- **Budgets**: monthly per-category limit cents + spend computed from transactions.
- **Recurring**: detected/declared bills with cadence + next-due date.
- **Investments**: holdings (symbol, qty, price cents) + market value.
- **Reports**: monthly spend by category, net worth, cash flow.
- **Transfers**: paired transactions linked by `transfer_id` (excluded from spend).

## Configuration (env)

| Variable | Default | Purpose |
|----------|---------|---------|
| `PERFI_MCP_ENABLED=1` | off | Expose `POST /api/mcp` (MCP, Streamable HTTP JSON-RPC) |
| `PERFI_MCP_TOKEN` | -- | Required bearer token for MCP; missing token is a 503 |
| `PERFI_MCP_WRITE_ENABLED=1` | off | Register MCP write tools (recategorize, set budget) |
| `PERFI_ENCRYPTION_KEY` | auto | Fernet key for the stored AI key; else `data/.ai_key` |
| `PERFI_LOG_LEVEL` | INFO | Log verbosity (DEBUG for full request + domain logs) |

AI setup: `PUT /api/settings/ai` with provider (`openai`, `anthropic`,
`google`, `custom`), model, and API key (stored encrypted, never returned).
Then `POST /api/ai/categorize?limit=&min_confidence=` classifies only
never-categorized transactions. MCP read tools work out of the box once
enabled; write tools stay unlisted until explicitly enabled.

## Docs

- `docs/architecture.md` — stack, request flow, domain concepts
- `docs/operations.md` — dev servers, ports, logging, DB, migrations, gitignore
- `docs/testing.md` — suite, anonymized ground-truth fixture, frontend checks
- `docs/decisions.md` — standing constraints, fixes, open risks

Use `http://localhost:5173` for the UI (not `127.0.0.1` — see operations).
Test data in the repo is anonymized by policy; never commit real exports,
`data/` contents, or key files.

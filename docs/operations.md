# Operations

## Dev servers

```bash
./scripts/dev.sh        # backend :8000 + frontend :5173, one terminal
```

- Prints both URLs at startup, then fails fast: if either service exits it
  names the survivor's PID and stops the other (`wait -n` replacement poll
  loop — macOS ships bash 3.2, which has no `wait -n`).
- Shutdown is TERM, 2s grace, then KILL — Ctrl-C always finishes.
- Frontend runs Vite directly (`exec …/node_modules/.bin/vite`), not via
  `npm run dev`, because npm swallows SIGTERM and orphaned Vite on `:5173`.
- `npm install` uses `--no-progress --no-audit --no-fund`: quiet but errors
  still print (the old `-q 2>/dev/null` hid install failures completely).

## URLs and ports

- UI: `http://localhost:5173`. Backend: `http://localhost:8000`
  (`/api/health`, docs at `/docs`).
- Use `localhost`, **not** `127.0.0.1`, for the UI: Vite binds IPv6-only, so
  the IPv4 address refuses connections while the hostname works.
- Port conflicts (`[Errno 48]`): uvicorn prints only the errno, never which
  address. Find the holder with `lsof -i :8000` / `lsof -i :5173`. Leftover
  PIDs are almost always a killed terminal whose `dev.sh` trap never ran:
  `lsof -ti :8000 | xargs kill -9`.

## Logging

`perfi.*` loggers (`logging_setup.py`), `disable_existing_loggers=False` so
uvicorn worker output survives reload; lifespan re-asserts levels.
`PERFI_LOG_LEVEL=DEBUG` for full request + domain logs. Backend terminal shows
which service died and why — that visibility is intentional, keep it.

## Database

- Fresh start: delete `data/perfi.db*` and boot — migrations + seed run on
  startup (11 categories). Nothing else to reset.
- **Migrations stay squashed at one file.** To change schema: edit `models.py`,
  `alembic revision --autogenerate`, then fold the delta into
  `51171a03795c_initial_squashed_schema.py` and delete the new file. Verify
  with `alembic upgrade head` on an empty DB + `alembic check` (must report
  "No new upgrade operations detected"). Dev DBs stamped with a deleted
  revision id must be deleted, not restamped — data/ is disposable.
- Never commit `data/`: db files (`data/*.db*`) and the key
  (`data/.ai_key`) are gitignored. `backend/data/` must never exist — if you
  see it, some path helper regressed (see decisions log 2026-09-04).

## Tests & checks

```bash
cd backend && ../.venv/bin/python -m pytest tests -q   # 66 tests
cd frontend && npm run build                            # only frontend gate
```

No tsc gate exists. Python stays hint-free (AGENTS.md) — Pydantic/FastAPI
declarations are the only allowed annotations.

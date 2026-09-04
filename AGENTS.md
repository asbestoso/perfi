# AGENTS.md


## Project

- Name: perfi

## Context / Goal

## Common Commands

- `./scripts/dev.sh` — backend :8000 + frontend :5173 (UI at http://localhost:5173)
- `cd backend && ../.venv/bin/python -m pytest tests -q` — backend suite
- `cd frontend && npm run build` — only frontend gate (no tsc installed)

## Project Layout

- No common source, test, docs, or spec directories detected yet.

## Project Layout


## Worklog (required, every time)

- Append a dated entry to `worklog.md` (repo root, newest at bottom, `## YYYY-MM-DD — title`) for every task, no matter how small.
- Each entry: what changed, why, and what was decided or deferred. One line is fine for trivia; give real work a real entry.
- Never skip it, never batch it for later — the worklog is the project's memory.

## Python style rules

- NEVER add type hints, typing imports, or TypedDict / List[str] / Dict / etc to Python code
- Do not add `from typing import...`
- Do not add `-> str`, `: int`, `: list[str]` annotations
- Keep Python code untyped, as written. If existing file has no types, don't add them.
- This applies to all new files and edits.
# Testing

## Backend — pytest

`cd backend && ../.venv/bin/python -m pytest tests -q` (66 tests).
One `client` + `store` fixture and `make_txn()` live in `conftest.py`:
in-memory SQLite, `store` seeds 4 categories + 2 zero-balance accounts
(Checking, Card). Tests needing balances create their own accounts.

## Ground-truth fixture

`backend/tests/fixtures/monarch_ground_truth.csv` (7151 rows) drives
`test_monarch_ground_truth_end_to_end` using the Empower profile: upload → queue → merge-all → export →
re-upload-skips-everything, plus a spot-check on two mapped rows.

- The fixture is **anonymized**: real account names → `Account 01…`,
  descriptions → `Merchant 0001…`, amounts remapped through an odd injective
  map (sign/zero kept, magnitudes destroyed). Dates, generic Monarch
  categories, and tags are verbatim.
- Anonymization is structure-preserving by construction: deterministic 1:1
  maps keep every duplicate key, transfer pair, and per-account distribution
  identical, so dedupe/merge counts still exercise the real paths.
- Never reintroduce real data here. Never touch `/Users/j/Desktop/test.csv`
  (the real export this was derived from — outside the repo).
- Inline hand-written fixtures (`Whole Foods`, `NETFLIX`, …) are synthetic
  and stay: the seed categorization regexes legitimately match real merchant
  names, and renaming them would weaken the product.

## Frontend

`cd frontend && npm run build`. Covers all pages compiling; nothing checks
types. UI↔API wiring is verified by hand: boot the stack, open
`http://localhost:5173`, walk Import → Transactions → Reports.

## Scratch probes

One-off verification scripts belong in `/tmp` (e.g. `/tmp/perfi_page_probe.py`
boots the app in-process and hits endpoints), never in the repo. The repo's
own suite is the gate; probes supplement it.

#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/data"

if [ ! -d "$ROOT/.venv" ]; then
  python3 -m venv "$ROOT/.venv"
fi
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
pip install -q -r "$ROOT/backend/requirements.txt"

echo "API http://localhost:8000   UI http://localhost:5173"
uvicorn app.main:app --reload --port 8000 --app-dir "$ROOT/backend" &
BACK_PID=$!
(cd "$ROOT/frontend" && npm install --no-progress --no-audit --no-fund && exec ./node_modules/.bin/vite --port 5173) &
FRONT_PID=$!
# TERM first for a clean stop, KILL fallback: npm never forwarded
# signals to vite (orphaning it), and the uvicorn reloader can hang.
trap 'kill $BACK_PID $FRONT_PID 2>/dev/null; sleep 2; kill -9 $BACK_PID $FRONT_PID 2>/dev/null' EXIT INT TERM
# Fail fast: if either service exits, say which and stop the other
# instead of silently running half the stack.
# (Poll loop instead of `wait -n`: macOS bash is 3.2 and lacks it.)
alive() { ps -o stat= -p "$1" 2>/dev/null | grep -qv 'Z'; }
while alive "$BACK_PID" && alive "$FRONT_PID"; do sleep 1; done
echo "ERROR: a dev service exited (backend pid $BACK_PID, frontend pid $FRONT_PID); shutting down."
exit 1

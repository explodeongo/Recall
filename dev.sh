#!/usr/bin/env bash
# Start Recall for development in one terminal: checks the database, applies migrations, then
# runs the API (with the background worker inside it) and the web app. Ctrl+C stops it all.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\033[1m%s\033[0m\n' "$*"; }

say "Checking the database…"
if ! (cd backend && uv run python -c "from app.db import engine; engine.connect().close()" >/dev/null 2>&1); then
  if command -v brew >/dev/null && brew list postgresql@17 >/dev/null 2>&1; then
    say "Starting Postgres (Homebrew)…"
    brew services start postgresql@17 >/dev/null
    sleep 3
  fi
  if ! (cd backend && uv run python -c "from app.db import engine; engine.connect().close()" >/dev/null 2>&1); then
    echo "Can't reach the database in backend/.env (DATABASE_URL). Start Postgres and try again." >&2
    exit 1
  fi
fi

say "Updating the database schema…"
(cd backend && uv sync -q && uv run alembic upgrade head 2>&1 | grep -v "^INFO" || true)
[ -d frontend/node_modules ] || (say "Installing the web app…" && cd frontend && npm install --silent)

trap 'trap - EXIT; kill 0' INT TERM EXIT
say "Starting the API and worker on :8000 and the web app on :3000…"
(cd backend && RUN_WORKER_IN_API=true uv run uvicorn app.main:app --reload --port 8000) &
(cd frontend && npm run dev -- --port 3000) &
sleep 6
say "Recall is running: http://localhost:3000  (Ctrl+C to stop)"
wait

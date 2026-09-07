#!/usr/bin/env bash
# Run the Araxys Desk backend.
#   backend/scripts/dev.sh          -> http://localhost:8000
#   PORT=8080 backend/scripts/dev.sh
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"
BIND_HOST="${BIND_HOST:-0.0.0.0}"

if [ -x "${BACKEND_DIR}/.venv/Scripts/python.exe" ]; then
    PYTHON="${BACKEND_DIR}/.venv/Scripts/python.exe"   # Windows layout
elif [ -x "${BACKEND_DIR}/.venv/bin/python" ]; then
    PYTHON="${BACKEND_DIR}/.venv/bin/python"
else
    echo "venv python not found under ${BACKEND_DIR}/.venv" >&2
    exit 1
fi

cd "${BACKEND_DIR}"
echo "Araxys Desk backend on http://localhost:${PORT} (docs at /docs)"
exec "${PYTHON}" -m uvicorn app.main:app --host "${BIND_HOST}" --port "${PORT}" --reload

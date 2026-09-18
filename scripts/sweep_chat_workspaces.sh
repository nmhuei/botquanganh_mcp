#!/usr/bin/env bash
# Append one chat-workspace lifecycle sweep to logs/sweeper.log.
#
# Thin wrapper around `python -m app.chat_sweeper` using the repo venv, so the
# supervisor (scripts/start_tunnel_server.sh) and operators share one logging
# path. Safe to run repeatedly: log writes are appends and the sweeper itself
# is idempotent (dry run by default; pass --apply for real archiving/deletion).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

LOG_FILE="logs/sweeper.log"
mkdir -p logs

PYTHON="$ROOT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "[!] sweep skipped: $PYTHON is missing; run ./scripts/install_basic.sh first." >&2
    exit 1
fi

rc=0
{
    echo "=== $(date '+%Y-%m-%dT%H:%M:%S%z') chat sweeper start args:$* ==="
    PYTHONPATH="$ROOT_DIR" "$PYTHON" -m app.chat_sweeper "$@" || rc=$?
    echo "=== chat sweeper end rc=$rc ==="
} >> "$LOG_FILE" 2>&1

exit "$rc"

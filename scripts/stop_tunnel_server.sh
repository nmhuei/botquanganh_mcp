#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck source=scripts/process_helpers.sh
source ./scripts/process_helpers.sh

SERVER_PID_FILE="logs/server.pid"
TUNNEL_PID_FILE="logs/tunnel.pid"
WATCHDOG_PID_FILE="logs/watchdog.pid"
LAUNCHER_PID_FILE="logs/launcher.pid"
TUNNEL_URL_FILE="logs/tunnel_url.txt"

# Stop ownership controller first so it cannot recreate children.
stop_managed_pid_file "$WATCHDOG_PID_FILE" supervisor "Supervisor"
stop_managed_pid_file "$LAUNCHER_PID_FILE" launcher "Launcher"
stop_managed_pid_file "$TUNNEL_PID_FILE" tunnel "Cloudflare Tunnel"
stop_managed_pid_file "$SERVER_PID_FILE" server "MCP Server"
rm -f "$TUNNEL_URL_FILE"

# Report unrelated port occupants but never terminate them.
MCP_PORT=8000
if [ -x .venv/bin/python ]; then
    MCP_PORT=$(.venv/bin/python - <<'PY'
from dotenv import dotenv_values
print(dotenv_values('.env').get('MCP_PORT') or '8000')
PY
)
fi
if command -v lsof >/dev/null 2>&1; then
    for port_pid in $(lsof -t -i :"$MCP_PORT" 2>/dev/null | sort -u || true); do
        if pid_matches_kind "$port_pid" server; then
            echo "[!] Managed server process remained on port $MCP_PORT (PID $port_pid)." >&2
        else
            echo "[i] Unrelated process remains on port $MCP_PORT (PID $port_pid); it was not touched."
        fi
    done
fi

echo "[+] Managed MCP server and tunnel processes stopped."

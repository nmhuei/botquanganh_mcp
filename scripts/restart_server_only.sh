#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

[ -x .venv/bin/fastmcp ] || ./scripts/install_basic.sh
mkdir -p logs

read_env() {
    local key="$1" default_value="$2"
    .venv/bin/python - "$key" "$default_value" <<'PY'
import sys
from dotenv import dotenv_values
values = dotenv_values('.env')
print(values.get(sys.argv[1]) or sys.argv[2])
PY
}

MCP_BIND_HOST="${MCP_BIND_HOST:-$(read_env MCP_BIND_HOST 127.0.0.1)}"
MCP_CONNECT_HOST="${MCP_CONNECT_HOST:-127.0.0.1}"
MCP_PORT="${MCP_PORT:-$(read_env MCP_PORT 8000)}"
MCP_PATH="${MCP_PATH:-/mcp}"
PID_FILE="logs/server.pid"

stop_server() {
    local pid=""
    pid=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        for _ in $(seq 1 20); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.2
        done
        kill -9 "$pid" 2>/dev/null || true
    fi

    if command -v lsof >/dev/null 2>&1; then
        local port_pids
        port_pids=$(lsof -t -i :"$MCP_PORT" 2>/dev/null || true)
        [ -z "$port_pids" ] || kill $port_pids 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
}

stop_server
export PYTHONPATH="$ROOT_DIR"
export FASTMCP_MESSAGE_PATH="$MCP_PATH"

nohup .venv/bin/fastmcp run app/main.py \
    --transport streamable-http \
    --host "$MCP_BIND_HOST" \
    --port "$MCP_PORT" \
    --path "$MCP_PATH" \
    > logs/server.log 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

for _ in $(seq 1 30); do
    if .venv/bin/python - "$MCP_CONNECT_HOST" "$MCP_PORT" <<'PY' >/dev/null 2>&1
import socket, sys
with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=0.3):
    pass
PY
    then
        echo "[+] Host MCP restarted: http://${MCP_CONNECT_HOST}:${MCP_PORT}${MCP_PATH} (PID $SERVER_PID)"
        exit 0
    fi
    kill -0 "$SERVER_PID" 2>/dev/null || {
        echo "[-] Server exited during startup. Check logs/server.log."
        exit 1
    }
    sleep 0.5
done

echo "[-] Server socket did not become ready. Check logs/server.log."
exit 1

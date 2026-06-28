#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

MCP_HOST="${MCP_HOST:-127.0.0.1}"
MCP_PORT="${MCP_PORT:-8000}"
MCP_PATH="${MCP_PATH:-/mcp}"
MAX_WAIT="${MAX_RESTART_WAIT:-15}"
SERVER_PID_FILE="logs/server.pid"
RESTART_COUNT_FILE="logs/restart_count"
MAX_RESTART_COUNT=5

# --- Restart count protection ---
mkdir -p logs
COUNT=0
if [ -f "$RESTART_COUNT_FILE" ]; then
    COUNT=$(cat "$RESTART_COUNT_FILE" 2>/dev/null || echo 0)
fi
if [ "$COUNT" -ge "$MAX_RESTART_COUNT" ]; then
    echo "[CRITICAL] Too many restarts ($COUNT) in short period. Giving up."
    exit 2
fi
echo $((COUNT + 1)) > "$RESTART_COUNT_FILE"

# --- Kill existing server on port ---
SERVER_PID=$(lsof -t -i :"$MCP_PORT" 2>/dev/null || true)
if [ -n "$SERVER_PID" ]; then
    echo "[*] Stopping server on port $MCP_PORT (PID: $SERVER_PID)..."
    kill -15 $SERVER_PID 2>/dev/null || true
    sleep 1
    kill -9 $SERVER_PID 2>/dev/null || true

    # Wait for port to actually be free
    for _ in $(seq 1 10); do
        if ! lsof -i :"$MCP_PORT" >/dev/null 2>&1; then
            break
        fi
        sleep 0.3
    done
else
    echo "[*] No server process found on port $MCP_PORT."
fi

# --- Start new server ---
source .venv/bin/activate
export PYTHONPATH=.
export FASTMCP_MESSAGE_PATH="$MCP_PATH"
export MCP_DISABLE_DNS_REBINDING=1

fastmcp run app/main.py --transport streamable-http --port "$MCP_PORT" --host "$MCP_HOST" --path "$MCP_PATH" > logs/server.log 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$SERVER_PID_FILE"

# --- Verify socket readiness ---
echo "[*] Waiting for server socket readiness..."
for _ in $(seq 1 "$MAX_WAIT"); do
    if .venv/bin/python -c "
import socket
try:
    socket.create_connection(('$MCP_HOST', $MCP_PORT), timeout=0.3).close()
    print('ready')
except Exception:
    exit(1)
" >/dev/null 2>&1; then
        echo "[+] Server restarted successfully (PID: $NEW_PID)."
        echo "[+] Cloudflare Tunnel remains active."

        # Decrement restart counter on success
        if [ "$COUNT" -gt 0 ]; then
            echo $((COUNT - 1)) > "$RESTART_COUNT_FILE"
        fi
        exit 0
    fi

    if ! kill -0 $NEW_PID 2>/dev/null; then
        echo "[-] Server process $NEW_PID died during startup. Check logs/server.log."
        exit 1
    fi
    sleep 0.5
done

echo "[-] Server started but socket not ready after ${MAX_WAIT}s. Check logs/server.log."
exit 1

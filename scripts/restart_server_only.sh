#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

MCP_HOST="${MCP_HOST:-127.0.0.1}"
MCP_PORT="${MCP_PORT:-8000}"
MCP_PATH="${MCP_PATH:-/mcp}"
SERVER_PID_FILE="logs/server.pid"

# Find server PID on port 8000
SERVER_PID=$(lsof -t -i :"$MCP_PORT" 2>/dev/null || true)
if [ -n "$SERVER_PID" ]; then
    echo "[*] Stopping current server process on port $MCP_PORT (PID: $SERVER_PID)..."
    kill -15 $SERVER_PID 2>/dev/null || true
    sleep 1
    kill -9 $SERVER_PID 2>/dev/null || true
else
    echo "[*] No server process found listening on port $MCP_PORT."
fi

echo "[*] Starting new server process..."
source .venv/bin/activate
export PYTHONPATH=.
export FASTMCP_MESSAGE_PATH="$MCP_PATH"
export MCP_DISABLE_DNS_REBINDING=1
mkdir -p logs
fastmcp run app/main.py --transport streamable-http --port "$MCP_PORT" --host "$MCP_HOST" --path "$MCP_PATH" > logs/server.log 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$SERVER_PID_FILE"
echo "[+] Server restarted successfully (PID: $NEW_PID)."
echo "[+] Cloudflare Tunnel remains untouched and will automatically route requests to the new server."

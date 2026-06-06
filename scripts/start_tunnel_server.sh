#!/bin/bash
# Start the MCP server in ChatGPT-compatible Streamable HTTP mode and expose it
# through a Cloudflare quick tunnel.

cd "$(dirname "$0")/.."

MCP_HOST="${MCP_HOST:-127.0.0.1}"
MCP_PORT="${MCP_PORT:-8000}"
MCP_PATH="${MCP_PATH:-/mcp}"

# Clean up any existing instances of the server port or quick tunnel.
echo "[*] Detecting and stopping existing server/tunnel instances..."
PORT_PIDS=$(lsof -t -i :"$MCP_PORT" 2>/dev/null)
if [ ! -z "$PORT_PIDS" ]; then
    echo "[*] Stopping existing server process(es) on port $MCP_PORT (PID: $PORT_PIDS)..."
    kill -15 $PORT_PIDS 2>/dev/null
    sleep 1
    kill -9 $PORT_PIDS 2>/dev/null
fi

TUNNEL_PIDS=$(pgrep -f "cloudflared tunnel --url http://${MCP_HOST}:${MCP_PORT}" 2>/dev/null)
if [ -z "$TUNNEL_PIDS" ] && [ "$MCP_HOST" = "127.0.0.1" ]; then
    TUNNEL_PIDS=$(pgrep -f "cloudflared tunnel --url http://localhost:${MCP_PORT}" 2>/dev/null)
fi
if [ ! -z "$TUNNEL_PIDS" ]; then
    echo "[*] Stopping existing cloudflared tunnel process(es) for port $MCP_PORT (PID: $TUNNEL_PIDS)..."
    kill -15 $TUNNEL_PIDS 2>/dev/null
    sleep 1
    kill -9 $TUNNEL_PIDS 2>/dev/null
fi

# 1. Ensure only the basic Python environment is ready.
# Advanced Docker runner images are intentionally installed separately via:
#   ./scripts/install_advanced_tools.sh
./scripts/install_basic.sh
source .venv/bin/activate

ADVANCED_TOOLS_FLAG=$(grep -E '^ENABLE_ADVANCED_TOOLS=' .env 2>/dev/null | tail -n 1 | cut -d= -f2-)
if [ "${ADVANCED_TOOLS_FLAG:-false}" != "true" ]; then
    echo "[*] Starting in BASIC mode. Advanced Docker runner tools are disabled."
    echo "[*] To enable them later, run: ./scripts/install_advanced_tools.sh"
else
    echo "[*] Starting in ADVANCED mode. Docker runner tools will be exposed."
fi

export PYTHONPATH=.

# Ensure logs directory exists
mkdir -p logs

# Clean up previous logs
rm -f logs/cloudflared.log

echo "[*] Starting Fallback Runner MCP server on ${MCP_HOST}:${MCP_PORT}${MCP_PATH}..."
export FASTMCP_MESSAGE_PATH="$MCP_PATH"
export MCP_DISABLE_DNS_REBINDING=1
.venv/bin/fastmcp run app/main.py --transport streamable-http --port "$MCP_PORT" --host "$MCP_HOST" --path "$MCP_PATH" > logs/server.log 2>&1 &
SERVER_PID=$!

# Ensure server PID is cleaned up on exit
cleanup() {
    echo -e "\n[*] Shutting down tunnel and MCP server..."
    kill $TUNNEL_PID 2>/dev/null
    kill $SERVER_PID 2>/dev/null
    wait $SERVER_PID 2>/dev/null
    wait $TUNNEL_PID 2>/dev/null
    echo "[+] Shutdown complete."
    exit 0
}
trap cleanup SIGINT SIGTERM

# Wait for the socket to be ready instead of probing MCP without a session.
for _ in $(seq 1 30); do
    if .venv/bin/python - "$MCP_HOST" "$MCP_PORT" <<'PY' >/dev/null 2>&1
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.create_connection((host, port), timeout=0.3):
    pass
PY
    then
        break
    fi
    if ! kill -0 $SERVER_PID 2>/dev/null; then
        echo "[-] Error: MCP server failed to start. Check logs/server.log for details."
        exit 1
    fi
    sleep 0.5
done

# Check if server process is still running
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "[-] Error: MCP server failed to start. Check logs/server.log for details."
    exit 1
fi
echo "[+] MCP server started successfully (PID: $SERVER_PID)."

echo "[*] Initiating Cloudflare Tunnel..."
# Start cloudflared to forward the MCP server port.
cloudflared tunnel --url "http://${MCP_HOST}:${MCP_PORT}" > logs/cloudflared.log 2>&1 &
TUNNEL_PID=$!
echo "[+] Tunnel process launched (PID: $TUNNEL_PID)."

# Extract TryCloudflare URL from log file
echo "[*] Waiting for TryCloudflare URL generation (approx 5-10s)..."
RETRIES=15
URL=""
for ((i=1; i<=RETRIES; i++)); do
    if [ -f logs/cloudflared.log ]; then
        URL=$(grep -o -E "https://[a-zA-Z0-9-]+\.trycloudflare\.com" logs/cloudflared.log | head -n 1)
        if [ ! -z "$URL" ]; then
            break
        fi
    fi
    sleep 1
done

if [ -z "$URL" ]; then
    echo "[-] Error: Failed to obtain TryCloudflare URL. Check logs/cloudflared.log."
    kill $SERVER_PID
    kill $TUNNEL_PID
    exit 1
fi

echo -e "\n=========================================================================="
echo -e "[+++] CLOUDFLARE TUNNEL ESTABLISHED SUCCESSFULLY! [+++]"
echo -e "=========================================================================="
echo -e "Server Endpoint URL:   ${URL}${MCP_PATH}"
echo -e "Logs Location:          logs/server.log, logs/cloudflared.log"
echo -e "=========================================================================="
echo -e "Use the following URL in ChatGPT Connector Settings:"
echo -e "\033[1;32m${URL}${MCP_PATH}\033[0m"
echo -e "=========================================================================="
echo -e "Press [Ctrl+C] to stop both the MCP server and the Cloudflare Tunnel."
echo -e "=========================================================================="

# Keep script running to maintain processes
while true; do
    # Check if either process died unexpectedly
    if ! kill -0 $SERVER_PID 2>/dev/null; then
        echo "[-] MCP server process died unexpectedly."
        cleanup
    fi
    if ! kill -0 $TUNNEL_PID 2>/dev/null; then
        echo "[-] Cloudflare Tunnel process died unexpectedly."
        cleanup
    fi
    sleep 3
done

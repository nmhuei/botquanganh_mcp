#!/bin/bash
# Script to automate starting the MCP server in HTTP mode and launching Cloudflare Tunnel.

cd "$(dirname "$0")/.."

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

echo "[*] Starting Fallback Runner MCP server on port 8000..."
# Start server using the HTTP transport
fastmcp run app/main.py --transport http --port 8000 --host 127.0.0.1 > logs/server.log 2>&1 &
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

# Settle server boot
sleep 2

# Check if server process is still running
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "[-] Error: MCP server failed to start. Check logs/server.log for details."
    exit 1
fi
echo "[+] MCP server started successfully (PID: $SERVER_PID)."

echo "[*] Initiating Cloudflare Tunnel..."
# Start cloudflared to forward port 8000
cloudflared tunnel --url http://127.0.0.1:8000 > logs/cloudflared.log 2>&1 &
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
echo -e "Server Endpoint URL:   ${URL}/mcp"
echo -e "Logs Location:          logs/server.log, logs/cloudflared.log"
echo -e "=========================================================================="
echo -e "Use the following URL in ChatGPT Connector Settings:"
echo -e "👉 \033[1;32m${URL}/mcp\033[0m"
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

#!/bin/bash
# Find server PID on port 8000
SERVER_PID=$(lsof -t -i :8000)
if [ ! -z "$SERVER_PID" ]; then
    echo "[*] Stopping current server process (PID: $SERVER_PID)..."
    kill $SERVER_PID
    sleep 1
else
    echo "[*] No server process found listening on port 8000."
fi

echo "[*] Starting new server process..."
source .venv/bin/activate
export PYTHONPATH=.
export FASTMCP_MESSAGE_PATH=/mcp
fastmcp run app/main.py --transport sse --port 8000 --host 127.0.0.1 --path /mcp > logs/server.log 2>&1 &
NEW_PID=$!
echo "[+] Server restarted successfully (PID: $NEW_PID)."
echo "[+] Cloudflare Tunnel remains untouched and will automatically route requests to the new server."

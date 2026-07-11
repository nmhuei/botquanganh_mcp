#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

SERVER_PID_FILE="logs/server.pid"
TUNNEL_PID_FILE="logs/tunnel.pid"
WATCHDOG_PID_FILE="logs/watchdog.pid"

stop_pid_file() {
    local file="$1" pid="" name="$2"
    pid=$(cat "$file" 2>/dev/null || true)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "[*] Stopping $name (PID $pid)..."
        kill "$pid" 2>/dev/null || true
        for _ in $(seq 1 10); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.1
        done
        kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$file"
}

# Stop watchdog first
stop_pid_file "$WATCHDOG_PID_FILE" "Watchdog"
stop_pid_file "$TUNNEL_PID_FILE" "Cloudflare Tunnel"
stop_pid_file "$SERVER_PID_FILE" "MCP Server"

# Port cleanup just in case
MCP_PORT=8000
if [ -f .env ]; then
    MCP_PORT=$(grep -o -E 'MCP_PORT=[0-9]+' .env | cut -d= -f2 || echo "8000")
fi

if command -v lsof >/dev/null 2>&1; then
    port_pids=$(lsof -t -i :"$MCP_PORT" 2>/dev/null || true)
    if [ -n "$port_pids" ]; then
        echo "[*] Cleaning up lingering processes on port $MCP_PORT..."
        kill $port_pids 2>/dev/null || true
        sleep 0.5
        kill -9 $port_pids 2>/dev/null || true
    fi
fi

pkill -9 -f "cloudflared tunnel --url" 2>/dev/null || true

echo "[+] All MCP server and tunnel processes stopped."

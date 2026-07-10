#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

./scripts/install_basic.sh >/dev/null
command -v cloudflared >/dev/null 2>&1 || {
    echo "[-] cloudflared is not installed or not in PATH."
    exit 1
}

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
SERVER_PID_FILE="logs/server.pid"
TUNNEL_PID_FILE="logs/tunnel.pid"

SERVER_PID=""
TUNNEL_PID=""
URL=""

wait_for_socket() {
    for _ in $(seq 1 40); do
        if .venv/bin/python - "$MCP_CONNECT_HOST" "$MCP_PORT" <<'PY' >/dev/null 2>&1
import socket, sys
with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=0.3):
    pass
PY
        then
            return 0
        fi
        sleep 0.5
    done
    return 1
}

wait_for_tunnel_url() {
    for _ in $(seq 1 30); do
        URL=$(grep -o -E 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' logs/cloudflared.log 2>/dev/null | head -n 1 || true)
        [ -z "$URL" ] || return 0
        sleep 1
    done
    return 1
}

stop_pid_file() {
    local file="$1" pid=""
    pid=$(cat "$file" 2>/dev/null || true)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        sleep 0.5
        kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$file"
}

start_server() {
    export PYTHONPATH="$ROOT_DIR"
    export FASTMCP_MESSAGE_PATH="$MCP_PATH"
    .venv/bin/fastmcp run app/main.py \
        --transport streamable-http \
        --host "$MCP_BIND_HOST" \
        --port "$MCP_PORT" \
        --path "$MCP_PATH" \
        > logs/server.log 2>&1 &
    SERVER_PID=$!
    echo "$SERVER_PID" > "$SERVER_PID_FILE"
    wait_for_socket || {
        echo "[-] MCP server failed to start. Check logs/server.log."
        return 1
    }
}

start_tunnel() {
    : > logs/cloudflared.log
    cloudflared tunnel --url "http://${MCP_CONNECT_HOST}:${MCP_PORT}" \
        > logs/cloudflared.log 2>&1 &
    TUNNEL_PID=$!
    echo "$TUNNEL_PID" > "$TUNNEL_PID_FILE"
    wait_for_tunnel_url || {
        echo "[-] Cloudflare Tunnel did not return a URL. Check logs/cloudflared.log."
        return 1
    }
}

cleanup() {
    stop_pid_file "$TUNNEL_PID_FILE"
    stop_pid_file "$SERVER_PID_FILE"
}
trap cleanup EXIT INT TERM

stop_pid_file "$TUNNEL_PID_FILE"
stop_pid_file "$SERVER_PID_FILE"

start_server
start_tunnel

echo "[+] Host MCP server: http://${MCP_CONNECT_HOST}:${MCP_PORT}${MCP_PATH}"
echo "[+] ChatGPT connector: ${URL}${MCP_PATH}"
echo "[+] Watchdog active. Press Ctrl+C to stop."

health_failures=0
while true; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "[!] MCP server stopped; restarting..."
        start_server
        health_failures=0
    fi

    if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
        echo "[!] Cloudflare Tunnel stopped; restarting..."
        start_tunnel
        echo "[+] New connector URL: ${URL}${MCP_PATH}"
    fi

    if curl -fsS --max-time 3 "http://${MCP_CONNECT_HOST}:${MCP_PORT}/healthz" >/dev/null 2>&1; then
        health_failures=0
    else
        health_failures=$((health_failures + 1))
        if [ "$health_failures" -ge 3 ]; then
            echo "[!] Health check failed three times; restarting MCP server..."
            stop_pid_file "$SERVER_PID_FILE"
            start_server
            health_failures=0
        fi
    fi

    sleep 5
done

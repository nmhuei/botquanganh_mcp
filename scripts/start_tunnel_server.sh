#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

[ -x .venv/bin/fastmcp ] || ./scripts/install_basic.sh >/dev/null
# shellcheck source=scripts/process_helpers.sh
source ./scripts/process_helpers.sh
command -v cloudflared >/dev/null 2>&1 || {
    echo "[-] cloudflared is not installed or not in PATH."
    exit 1
}

mkdir -p logs

read_env() {
    local key="$1" default_value="$2"
    .venv/bin/python - "$key" "$default_value" <<'PY'
import os
import sys
from dotenv import dotenv_values

key, default = sys.argv[1], sys.argv[2]
values = dotenv_values('.env')
print(os.environ.get(key) or values.get(key) or default)
PY
}

MCP_BIND_HOST="${MCP_BIND_HOST:-$(read_env MCP_BIND_HOST 127.0.0.1)}"
MCP_CONNECT_HOST="${MCP_CONNECT_HOST:-127.0.0.1}"
MCP_PORT="${MCP_PORT:-$(read_env MCP_PORT 8000)}"
MCP_PATH="${MCP_PATH:-$(read_env MCP_PATH /mcp)}"
SERVER_PID_FILE="logs/server.pid"
TUNNEL_PID_FILE="logs/tunnel.pid"
SUPERVISOR_PID_FILE="logs/watchdog.pid"
LAUNCHER_PID_FILE="logs/launcher.pid"
TUNNEL_URL_FILE="logs/tunnel_url.txt"
SERVER_LOG="logs/server.log"
CLOUDFLARED_LOG="logs/cloudflared.log"

SERVER_STARTED_AT=0
PUBLISHED_TUNNEL_PID=""
SHUTTING_DOWN=0

read_pid() {
    read_pid_file "$1"
}

atomic_write() {
    atomic_write_runtime_file "$1" "$2"
}

stop_pid_file() {
    stop_managed_pid_file "$1" "$2" "$3"
}

remove_own_pid_file() {
    local file="$1" pid=""
    pid=$(read_pid "$file")
    [ "$pid" != "$$" ] || rm -f "$file"
}

shutdown() {
    [ "$SHUTTING_DOWN" -eq 0 ] || exit 0
    SHUTTING_DOWN=1
    trap - TERM INT

    # Child processes must stop only after the supervisor is no longer able to recreate them.
    stop_pid_file "$TUNNEL_PID_FILE" tunnel "Cloudflare Tunnel"
    stop_pid_file "$SERVER_PID_FILE" server "MCP Server"
    rm -f "$TUNNEL_URL_FILE"
    remove_own_pid_file "$SUPERVISOR_PID_FILE"
    remove_own_pid_file "$LAUNCHER_PID_FILE"
    exit 0
}

trap shutdown TERM INT

socket_ready() {
    .venv/bin/python - "$MCP_CONNECT_HOST" "$MCP_PORT" <<'PY' >/dev/null 2>&1
import socket
import sys

with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=0.25):
    pass
PY
}

start_server() {
    local existing=""
    existing=$(read_pid "$SERVER_PID_FILE")
    if pid_matches_kind "$existing" server; then
        [ "$SERVER_STARTED_AT" -gt 0 ] || SERVER_STARTED_AT=$(date +%s)
        return 0
    fi

    rm -f "$SERVER_PID_FILE"
    export PYTHONPATH="$ROOT_DIR"
    export FASTMCP_MESSAGE_PATH="$MCP_PATH"
    nohup .venv/bin/fastmcp run app/main.py \
        --transport streamable-http \
        --host "$MCP_BIND_HOST" \
        --port "$MCP_PORT" \
        --path "$MCP_PATH" \
        > "$SERVER_LOG" 2>&1 &
    local pid=$!
    atomic_write "$SERVER_PID_FILE" "$pid"
    SERVER_STARTED_AT=$(date +%s)
    echo "[+] MCP server process started (PID $pid)."
}

start_tunnel() {
    local existing=""
    existing=$(read_pid "$TUNNEL_PID_FILE")
    if pid_matches_kind "$existing" tunnel; then
        return 0
    fi

    rm -f "$TUNNEL_PID_FILE" "$TUNNEL_URL_FILE"
    : > "$CLOUDFLARED_LOG"
    nohup cloudflared tunnel --url "http://${MCP_CONNECT_HOST}:${MCP_PORT}" \
        > "$CLOUDFLARED_LOG" 2>&1 &
    local pid=$!
    atomic_write "$TUNNEL_PID_FILE" "$pid"
    PUBLISHED_TUNNEL_PID=""
    echo "[+] Cloudflare Tunnel process started (PID $pid)."
}

publish_tunnel_url() {
    local pid="" url=""
    pid=$(read_pid "$TUNNEL_PID_FILE")
    pid_matches_kind "$pid" tunnel || return 1

    if [ "$PUBLISHED_TUNNEL_PID" = "$pid" ] && [ -s "$TUNNEL_URL_FILE" ]; then
        return 0
    fi

    url=$(grep -o -E 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$CLOUDFLARED_LOG" 2>/dev/null | head -n 1 || true)
    [ -n "$url" ] || return 1

    atomic_write "$TUNNEL_URL_FILE" "$url"
    PUBLISHED_TUNNEL_PID="$pid"
    echo "[+] Connector URL published: ${url}${MCP_PATH}"
}

existing_supervisor=$(read_pid "$SUPERVISOR_PID_FILE")
if pid_matches_kind "$existing_supervisor" supervisor && [ "$existing_supervisor" != "$$" ]; then
    echo "[i] Supervisor is already running (PID $existing_supervisor)."
    exit 0
fi
atomic_write "$SUPERVISOR_PID_FILE" "$$"

# These functions only spawn processes; neither waits for bridge readiness.
# Therefore the server and tunnel begin startup in parallel from the user's perspective.
start_server
start_tunnel

health_failures=0
last_health_check=0

while true; do
    server_pid=$(read_pid "$SERVER_PID_FILE")
    if ! pid_matches_kind "$server_pid" server; then
        start_server
        health_failures=0
    fi

    tunnel_pid=$(read_pid "$TUNNEL_PID_FILE")
    if ! pid_matches_kind "$tunnel_pid" tunnel; then
        rm -f "$TUNNEL_URL_FILE"
        start_tunnel
    fi

    publish_tunnel_url || true

    now=$(date +%s)
    if [ "$now" -ne "$last_health_check" ]; then
        last_health_check=$now
        if socket_ready; then
            health_failures=0
        elif [ $((now - SERVER_STARTED_AT)) -ge 20 ]; then
            health_failures=$((health_failures + 1))
            if [ "$health_failures" -ge 3 ]; then
                echo "[!] MCP bridge stayed unhealthy; restarting only the server process."
                stop_pid_file "$SERVER_PID_FILE" server "MCP Server"
                start_server
                health_failures=0
            fi
        fi
    fi

    sleep 0.1
done

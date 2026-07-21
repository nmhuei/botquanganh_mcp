#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

mkdir -p logs
# shellcheck source=scripts/process_helpers.sh
source ./scripts/process_helpers.sh
LAUNCHER_PID_FILE="logs/launcher.pid"
SUPERVISOR_PID_FILE="logs/watchdog.pid"
SERVER_PID_FILE="logs/server.pid"
TUNNEL_PID_FILE="logs/tunnel.pid"
TUNNEL_URL_FILE="logs/tunnel_url.txt"
LAUNCHER_LOG="logs/launcher.log"
CLOUDFLARED_LOG="logs/cloudflared.log"

read_pid() {
    read_pid_file "$1"
}

runtime_value() {
    local key="$1" default_value="$2"
    if [ -x .venv/bin/python ]; then
        .venv/bin/python - "$key" "$default_value" <<'PY' 2>/dev/null || printf '%s\n' "$default_value"
import os
import sys

key, default = sys.argv[1], sys.argv[2]
value = os.environ.get(key)
if not value:
    try:
        from dotenv import dotenv_values
        value = dotenv_values('.env').get(key)
    except Exception:
        value = None
print(value or default)
PY
    else
        printf '%s\n' "$default_value"
    fi
}

atomic_write_pid() {
    atomic_write_runtime_file "$1" "$2"
}

connector_url() {
    local base_url="" mcp_path=""
    [ -s "$TUNNEL_URL_FILE" ] || return 1
    base_url=$(head -n 1 "$TUNNEL_URL_FILE" 2>/dev/null || true)
    [[ "$base_url" =~ ^https://[a-zA-Z0-9-]+\.trycloudflare\.com/?$ ]] || return 1
    base_url="${base_url%/}"
    mcp_path=$(runtime_value MCP_PATH /mcp)
    [[ "$mcp_path" == /* ]] || mcp_path="/$mcp_path"
    printf '%s%s\n' "$base_url" "$mcp_path"
}

bridge_ready() {
    local host port
    host=$(runtime_value MCP_CONNECT_HOST 127.0.0.1)
    port=$(runtime_value MCP_PORT 8000)
    [ -x .venv/bin/python ] || return 1
    .venv/bin/python - "$host" "$port" <<'PY' >/dev/null 2>&1
import socket
import sys

with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=0.25):
    pass
PY
}

stop_pid_file() {
    stop_managed_pid_file "$1" "$2" "$3"
}

stop_all() {
    local launcher supervisor
    launcher=$(read_pid "$LAUNCHER_PID_FILE")
    supervisor=$(read_pid "$SUPERVISOR_PID_FILE")

    # Stop the supervisor first so it cannot recreate child processes.
    stop_pid_file "$SUPERVISOR_PID_FILE" supervisor "Supervisor"
    if [ -n "$launcher" ] && [ "$launcher" != "$supervisor" ]; then
        stop_pid_file "$LAUNCHER_PID_FILE" launcher "Launcher"
    else
        rm -f "$LAUNCHER_PID_FILE"
    fi

    stop_pid_file "$TUNNEL_PID_FILE" tunnel "Cloudflare Tunnel"
    stop_pid_file "$SERVER_PID_FILE" server "MCP Server"
    rm -f "$TUNNEL_URL_FILE"
    echo "[+] Host MCP tunnel stopped."
}

supervisor_pid() {
    local pid
    pid=$(read_pid "$SUPERVISOR_PID_FILE")
    if pid_matches_kind "$pid" supervisor; then
        printf '%s\n' "$pid"
        return 0
    fi
    pid=$(read_pid "$LAUNCHER_PID_FILE")
    if pid_matches_kind "$pid" launcher; then
        printf '%s\n' "$pid"
        return 0
    fi
    return 1
}

show_status() {
    local supervisor server tunnel url
    supervisor=$(supervisor_pid || true)
    server=$(read_pid "$SERVER_PID_FILE")
    tunnel=$(read_pid "$TUNNEL_PID_FILE")
    url=$(connector_url || true)

    pid_matches_kind "$supervisor" supervisor && echo "Supervisor: running ($supervisor)" || echo "Supervisor: stopped"
    pid_matches_kind "$server" server && echo "Server:     running ($server)" || echo "Server:     stopped"
    pid_matches_kind "$tunnel" tunnel && echo "Tunnel:     running ($tunnel)" || echo "Tunnel:     stopped"

    if pid_matches_kind "$server" server && bridge_ready; then
        echo "Bridge:     ready"
    elif pid_matches_kind "$server" server; then
        echo "Bridge:     starting"
    else
        echo "Bridge:     stopped"
    fi

    if pid_matches_kind "$tunnel" tunnel && [ -n "$url" ]; then
        echo "URL:        $url"
    elif pid_matches_kind "$tunnel" tunnel; then
        echo "URL:        pending"
    else
        echo "URL:        unavailable"
    fi
    echo "Logs:       logs/launcher.log, logs/server.log, logs/cloudflared.log"
}

action="${1:-start}"
case "$action" in
    start)
        ;;
    --stop|stop)
        stop_all
        exit 0
        ;;
    --restart|restart)
        stop_all
        sleep 0.2
        ;;
    --status|status)
        show_status
        exit 0
        ;;
    --url|url)
        connector_url
        exit $?
        ;;
    --help|-h|help)
        echo "Usage: $0 [start|stop|restart|status|url]"
        exit 0
        ;;
    *)
        echo "Unknown command: $action" >&2
        exit 2
        ;;
esac

existing_supervisor=$(supervisor_pid || true)
if pid_matches_kind "$existing_supervisor" supervisor; then
    echo "[i] Host MCP tunnel is already supervised (PID $existing_supervisor)."
    connector_url || true
    exit 0
fi

# Remove only stale PID files. Preserve the canonical URL when adopting a live tunnel.
rm -f "$LAUNCHER_PID_FILE" "$SUPERVISOR_PID_FILE"
existing_tunnel=$(read_pid "$TUNNEL_PID_FILE")
if ! pid_matches_kind "$existing_tunnel" tunnel; then
    rm -f "$TUNNEL_PID_FILE" "$TUNNEL_URL_FILE"
    : > "$CLOUDFLARED_LOG"
fi

nohup ./scripts/start_tunnel_server.sh > "$LAUNCHER_LOG" 2>&1 &
launcher_pid=$!
atomic_write_pid "$LAUNCHER_PID_FILE" "$launcher_pid"

echo "[*] Starting Host MCP supervisor (PID $launcher_pid)..."
for _ in $(seq 1 600); do
    url=$(connector_url || true)
    if [ -n "$url" ]; then
        echo "[+] Connector URL: $url"
        echo "[+] Status: ./run_mcp_tunnel.sh status"
        echo "[+] Stop:   ./run_mcp_tunnel.sh stop"
        exit 0
    fi

    current_supervisor=$(supervisor_pid || true)
    if ! pid_matches_kind "$current_supervisor" supervisor; then
        echo "[-] Supervisor exited before publishing a connector URL. Check $LAUNCHER_LOG." >&2
        exit 1
    fi
    sleep 0.1
done

echo "[!] Supervisor is running, but the connector URL is not ready yet."
echo "[i] Check: ./run_mcp_tunnel.sh status"

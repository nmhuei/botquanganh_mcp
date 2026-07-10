#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

mkdir -p logs
LAUNCHER_PID_FILE="logs/launcher.pid"
SERVER_PID_FILE="logs/server.pid"
TUNNEL_PID_FILE="logs/tunnel.pid"
LAUNCHER_LOG="logs/launcher.log"

read_pid() {
    cat "$1" 2>/dev/null || true
}

is_running() {
    local pid="$1"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

connector_url() {
    local url
    url=$(grep -o -E 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' logs/cloudflared.log 2>/dev/null | head -n 1 || true)
    if [ -z "$url" ]; then
        return 1
    fi
    printf '%s/mcp\n' "$url"
}

stop_all() {
    local launcher server tunnel
    launcher=$(read_pid "$LAUNCHER_PID_FILE")
    server=$(read_pid "$SERVER_PID_FILE")
    tunnel=$(read_pid "$TUNNEL_PID_FILE")

    if is_running "$launcher"; then
        kill "$launcher" 2>/dev/null || true
        for _ in $(seq 1 20); do
            kill -0 "$launcher" 2>/dev/null || break
            sleep 0.2
        done
        kill -9 "$launcher" 2>/dev/null || true
    fi
    is_running "$server" && kill "$server" 2>/dev/null || true
    is_running "$tunnel" && kill "$tunnel" 2>/dev/null || true
    rm -f "$LAUNCHER_PID_FILE" "$SERVER_PID_FILE" "$TUNNEL_PID_FILE"
    echo "[+] Host MCP tunnel stopped."
}

show_status() {
    local launcher server tunnel url
    launcher=$(read_pid "$LAUNCHER_PID_FILE")
    server=$(read_pid "$SERVER_PID_FILE")
    tunnel=$(read_pid "$TUNNEL_PID_FILE")
    url=$(connector_url || true)

    is_running "$launcher" && echo "Launcher: running ($launcher)" || echo "Launcher: stopped"
    is_running "$server" && echo "Server:   running ($server)" || echo "Server:   stopped"
    is_running "$tunnel" && echo "Tunnel:   running ($tunnel)" || echo "Tunnel:   stopped"
    [ -z "$url" ] || echo "URL:      $url"
    echo "Logs:     logs/launcher.log, logs/server.log, logs/cloudflared.log"
}

case "${1:-start}" in
    start)
        ;;
    --stop|stop)
        stop_all
        exit 0
        ;;
    --restart|restart)
        stop_all
        sleep 1
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
        echo "Unknown command: $1" >&2
        exit 2
        ;;
esac

existing=$(read_pid "$LAUNCHER_PID_FILE")
if is_running "$existing"; then
    echo "[i] Host MCP tunnel is already running (PID $existing)."
    connector_url || true
    exit 0
fi

rm -f "$LAUNCHER_PID_FILE"
nohup ./scripts/start_tunnel_server.sh > "$LAUNCHER_LOG" 2>&1 &
launcher_pid=$!
echo "$launcher_pid" > "$LAUNCHER_PID_FILE"

echo "[*] Starting Host MCP tunnel (PID $launcher_pid)..."
for _ in $(seq 1 40); do
    if ! kill -0 "$launcher_pid" 2>/dev/null; then
        echo "[-] Launcher exited. Check $LAUNCHER_LOG."
        exit 1
    fi
    url=$(connector_url || true)
    if [ -n "$url" ]; then
        echo "[+] Connector URL: $url"
        echo "[+] Status: ./run_mcp_tunnel.sh status"
        echo "[+] Stop:   ./run_mcp_tunnel.sh stop"
        exit 0
    fi
    sleep 1
done

echo "[!] Launcher is running, but the connector URL is not ready yet."
echo "[i] Check: ./run_mcp_tunnel.sh status"

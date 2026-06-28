#!/bin/bash
# Daemon launcher for MCP tunnel server.
# Runs start_tunnel_server.sh in background so the terminal can be closed safely.
# Usage: ./run_mcp_tunnel.sh [--stop|--restart|--status]

set -euo pipefail

cd "$(dirname "$0")"

LAUNCHER_PID_FILE="logs/launcher.pid"
SERVER_PID_FILE="logs/server.pid"
TUNNEL_PID_FILE="logs/tunnel.pid"
RESTART_COUNTER="logs/restart_counter"
STDOUT_LOG="logs/launcher.log"

mkdir -p logs

# ---- Functions ----

stop_daemon() {
    local pid
    if [ -f "$LAUNCHER_PID_FILE" ]; then
        pid=$(cat "$LAUNCHER_PID_FILE")
        echo "[*] Stopping daemon (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 1
        kill -9 "$pid" 2>/dev/null || true
        rm -f "$LAUNCHER_PID_FILE"
    else
        echo "[*] No daemon PID file found. Cleaning up child processes..."
    fi
    # Also clean up server/tunnel directly in case launcher is gone
    local server_pid tunnel_pid
    server_pid=$(cat "$SERVER_PID_FILE" 2>/dev/null || echo "")
    tunnel_pid=$(cat "$TUNNEL_PID_FILE" 2>/dev/null || echo "")
    [ -n "$server_pid" ] && kill "$server_pid" 2>/dev/null || true
    [ -n "$tunnel_pid" ] && kill "$tunnel_pid" 2>/dev/null || true
    rm -f "$SERVER_PID_FILE" "$TUNNEL_PID_FILE"
    rm -f "$RESTART_COUNTER"
    echo "[+] Daemon stopped."
}

show_status() {
    local launcher_pid server_pid tunnel_pid url=""
    launcher_pid=$(cat "$LAUNCHER_PID_FILE" 2>/dev/null || echo "")
    server_pid=$(cat "$SERVER_PID_FILE" 2>/dev/null || echo "")
    tunnel_pid=$(cat "$TUNNEL_PID_FILE" 2>/dev/null || echo "")

    echo ""
    echo "╔══════════════════════════════════════╗"
    echo "║        MCP DAEMON STATUS             ║"
    echo "╚══════════════════════════════════════╝"
    if [ -n "$launcher_pid" ] && kill -0 "$launcher_pid" 2>/dev/null; then
        echo "  Launcher:   ● RUNNING (PID $launcher_pid)"
    else
        echo "  Launcher:   ○ STOPPED"
    fi
    if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
        echo "  MCP Server: ● RUNNING (PID $server_pid)"
    else
        echo "  MCP Server: ○ STOPPED"
    fi
    if [ -n "$tunnel_pid" ] && kill -0 "$tunnel_pid" 2>/dev/null; then
        echo "  Tunnel:     ● RUNNING (PID $tunnel_pid)"
        if [ -f logs/cloudflared.log ]; then
            url=$(grep -o -E "https://[a-zA-Z0-9-]+\.trycloudflare\.com" logs/cloudflared.log | head -n 1)
            if [ -n "$url" ]; then
                echo ""
                echo -e "  \033[1;32m${url}/mcp\033[0m"
                echo ""
                echo "  ↑ Use the above URL in ChatGPT Connector Settings."
            fi
        fi
    else
        echo "  Tunnel:     ○ STOPPED"
    fi
    echo "  Logs:       logs/server.log | logs/cloudflared.log | logs/gateway.log"
    echo ""
}

# ---- CLI dispatch ----
case "${1:-}" in
    --stop|-s)
        stop_daemon
        exit 0
        ;;
    --restart|-r)
        stop_daemon
        sleep 1
        # Fall through to start below
        ;;
    --status|-st)
        show_status
        exit 0
        ;;
    --url|-u)
        u=$(grep -o -E 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' logs/cloudflared.log 2>/dev/null | head -n 1)
        if [ -n "$u" ]; then
            echo "${u}/mcp"
        else
            echo "URL not available yet. Use --status for details."
            exit 1
        fi
        exit 0
        ;;
    --help|-h)
        echo "Usage: $0 [--stop|--restart|--status|--url]"
        echo "  (no args)  Start daemon in background"
        echo "  --stop     Stop running daemon"
        echo "  --restart  Restart daemon"
        echo "  --status   Show daemon status + endpoint URL"
        echo "  --url      Print endpoint URL only (for scripts)"
        exit 0
        ;;
esac

# ---- Start daemon ----

# Check if already running
if [ -f "$LAUNCHER_PID_FILE" ]; then
    existing=$(cat "$LAUNCHER_PID_FILE")
    if kill -0 "$existing" 2>/dev/null; then
        echo "[!] Daemon already running (PID $existing)."
        existing_url=$(grep -o -E 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' logs/cloudflared.log 2>/dev/null | head -n 1)
        if [ -n "$existing_url" ]; then
            echo ""
            echo -e "    \033[1;32m${existing_url}/mcp\033[0m"
            echo ""
        fi
        echo "    Use --status for details, --restart to replace."
        exit 0
    fi
    echo "[*] Stale PID file found. Cleaning up..."
    rm -f "$LAUNCHER_PID_FILE"
fi

# Rotate previous launcher logs
if [ -f "$STDOUT_LOG" ] && [ "$(stat -c%s "$STDOUT_LOG" 2>/dev/null || echo 0)" -gt 10485760 ]; then
    mv "$STDOUT_LOG" "${STDOUT_LOG}.$(date +%Y%m%d-%H%M%S)"
    gzip "${STDOUT_LOG}.$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
fi

echo "[*] Starting MCP tunnel daemon..."

# Launch with nohup so it survives terminal closure.
# We wrap in a subshell so the PID file is written atomically.
nohup bash -c '
    cd "$(dirname "$0")"
    echo $$ > "'"$LAUNCHER_PID_FILE"'"
    exec ./scripts/start_tunnel_server.sh
' "$0" > "$STDOUT_LOG" 2>&1 &

# Wait briefly for the launcher PID to appear
DAEMON_PID=$!
sleep 1

# If launcher PID file was written, use that PID for more reliable tracking
if [ -f "$LAUNCHER_PID_FILE" ]; then
    DAEMON_PID=$(cat "$LAUNCHER_PID_FILE")
fi

# Verify it started
sleep 2
if kill -0 "$DAEMON_PID" 2>/dev/null; then
    echo "[+] Daemon started (PID: $DAEMON_PID)."
    echo -n "[*] Waiting for tunnel URL "

    # Poll for the tunnel URL (up to 40s with progress dots)
    URL=""
    for i in $(seq 1 40); do
        if [ -f logs/cloudflared.log ]; then
            URL=$(grep -o -E "https://[a-zA-Z0-9-]+\.trycloudflare\.com" logs/cloudflared.log | head -n 1)
            if [ -n "$URL" ]; then
                echo ""
                break
            fi
        fi
        echo -n "."
        sleep 1
    done

    echo ""
    echo ""
    echo "=========================================================================="
    echo "[+++] MCP TUNNEL RUNNING [+++]"
    echo "=========================================================================="
    if [ -n "$URL" ]; then
        echo ""
        echo -e "  \033[1;32m${URL}/mcp\033[0m"
        echo ""
        echo "  Use the above URL in ChatGPT Connector Settings."
    else
        echo ""
        echo "  ⚠️  Tunnel URL not yet available (daemon may still be starting)."
        echo ""
        echo "  Check progress with:  ./run_mcp_tunnel.sh --status"
        echo "  View tunnel log:      tail -20 logs/cloudflared.log"
        echo ""
    fi
    echo "  PID:        $DAEMON_PID"
    echo "  Logs:       tail -f logs/launcher.log"
    echo "  Stop:       ./run_mcp_tunnel.sh --stop"
    echo "  Status:     ./run_mcp_tunnel.sh --status"
    echo "=========================================================================="
    echo ""
    echo "[*] Daemonized. You may close this terminal — the server keeps running."
    echo "    (Use --status to check endpoint URL later.)"
else
    echo "[-] Daemon failed to start. Check logs/launcher.log."
    exit 1
fi

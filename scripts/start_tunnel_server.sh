#!/bin/bash
# Start the MCP server in ChatGPT-compatible Streamable HTTP mode and expose it
# through a Cloudflare quick tunnel.
#
# Improvements over v1:
#   - Auto-restart server when process dies or becomes unresponsive
#   - Health check via /healthz + local TCP probe
#   - Log rotation (rotate at 10MB)
#   - Restart count with backoff (max 5 rapid restarts before giving up)
#   - Tunnel auto-restart on failure

cd "$(dirname "$0")/.."

MCP_HOST="${MCP_HOST:-127.0.0.1}"
MCP_PORT="${MCP_PORT:-8000}"
MCP_PATH="${MCP_PATH:-/mcp}"

MAX_RESTART_COUNT=5
RESTART_COUNTER_FILE="logs/restart_counter"
SERVER_PID_FILE="logs/server.pid"
TUNNEL_PID_FILE="logs/tunnel.pid"

mkdir -p logs

# ------------------------------------------------------------------
# Log rotation: rotate files larger than 10 MB, keep 7 days of rotated
# ------------------------------------------------------------------
rotate_log() {
    local f="$1"
    if [ -f "$f" ] && [ "$(stat -c%s "$f" 2>/dev/null || echo 0)" -gt 10485760 ]; then
        mv "$f" "${f}.$(date +%Y%m%d-%H%M%S)"
        gzip "${f}.$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
    fi
}
find logs/ -name "*.log.*" -mtime +7 -delete 2>/dev/null || true
rotate_log logs/server.log
rotate_log logs/gateway.log
rotate_log logs/cloudflared.log

# Clean up any existing instances of the server port or quick tunnel.
echo "[*] Detecting and stopping existing server/tunnel instances..."
PORT_PIDS=""
if command -v lsof >/dev/null 2>&1; then
    PORT_PIDS=$(lsof -t -i :"$MCP_PORT" 2>/dev/null | tr '\n' ' ')
fi
if [ ! -z "$PORT_PIDS" ]; then
    echo "[*] Stopping existing server process(es) on port $MCP_PORT (PID: $PORT_PIDS)..."
    kill -15 $PORT_PIDS 2>/dev/null
    sleep 1
    kill -9 $PORT_PIDS 2>/dev/null
fi

TUNNEL_PIDS=$(ps -eo pid=,comm=,args= | awk \
    -v target1="http://${MCP_HOST}:${MCP_PORT}" \
    -v target2="http://localhost:${MCP_PORT}" \
    '$2 == "cloudflared" && index($0, " tunnel ") && (index($0, target1) || index($0, target2)) { print $1 }' \
    | tr '\n' ' ')
if [ ! -z "$TUNNEL_PIDS" ]; then
    echo "[*] Stopping existing cloudflared tunnel process(es) for port $MCP_PORT (PID: $TUNNEL_PIDS)..."
    kill -15 $TUNNEL_PIDS 2>/dev/null
    sleep 1
    kill -9 $TUNNEL_PIDS 2>/dev/null
fi

# Ensure only the basic Python environment is ready.
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

# Clean previous cloudflared log
rm -f logs/cloudflared.log

echo "[*] Starting Fallback Runner MCP server on ${MCP_HOST}:${MCP_PORT}${MCP_PATH}..."
export FASTMCP_MESSAGE_PATH="$MCP_PATH"
export MCP_DISABLE_DNS_REBINDING=1
.venv/bin/fastmcp run app/main.py --transport streamable-http --port "$MCP_PORT" --host "$MCP_HOST" --path "$MCP_PATH" > logs/server.log 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$SERVER_PID_FILE"

# ------------------------------------------------------------------
# cleanup — kill both processes and remove PID files
# ------------------------------------------------------------------
cleanup() {
    echo -e "\n[*] Shutting down tunnel and MCP server..."
    CURRENT_SERVER_PID=$(cat "$SERVER_PID_FILE" 2>/dev/null || echo "$SERVER_PID")
    CURRENT_TUNNEL_PID=$(cat "$TUNNEL_PID_FILE" 2>/dev/null || echo "${TUNNEL_PID:-}")
    if [ -n "$CURRENT_TUNNEL_PID" ]; then
        kill "$CURRENT_TUNNEL_PID" 2>/dev/null || true
        wait "$CURRENT_TUNNEL_PID" 2>/dev/null || true
    fi
    if [ -n "$CURRENT_SERVER_PID" ]; then
        kill "$CURRENT_SERVER_PID" 2>/dev/null || true
        wait "$CURRENT_SERVER_PID" 2>/dev/null || true
    fi
    rm -f "$SERVER_PID_FILE" "$TUNNEL_PID_FILE" "$RESTART_COUNTER_FILE"
    echo "[+] Shutdown complete."
    exit 0
}
trap cleanup SIGINT SIGTERM

# ------------------------------------------------------------------
# wait_for_socket — poll TCP socket until ready or timeout
# ------------------------------------------------------------------
wait_for_socket() {
    local host="$1" port="$2" max_tries="${3:-30}"
    for _ in $(seq 1 "$max_tries"); do
        if .venv/bin/python - "$host" "$port" <<'PY' >/dev/null 2>&1
import socket, sys
s = socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=0.3)
s.close()
PY
        then
            return 0
        fi
        sleep 0.5
    done
    return 1
}

# ------------------------------------------------------------------
# start_server — launch a fresh server process
# ------------------------------------------------------------------
start_server() {
    .venv/bin/fastmcp run app/main.py --transport streamable-http --port "$MCP_PORT" --host "$MCP_HOST" --path "$MCP_PATH" > logs/server.log 2>&1 &
    local pid=$!
    echo "$pid" > "$SERVER_PID_FILE"
    echo "$pid"
}

# ------------------------------------------------------------------
# restart_server — kill old server, start new, verify readiness
# ------------------------------------------------------------------
restart_server() {
    local reason="$1"
    local count=0
    if [ -f "$RESTART_COUNTER_FILE" ]; then
        count=$(cat "$RESTART_COUNTER_FILE")
    fi
    count=$((count + 1))
    echo "$count" > "$RESTART_COUNTER_FILE"

    if [ "$count" -gt "$MAX_RESTART_COUNT" ]; then
        echo "[-] Too many rapid restarts ($count). Full shutdown."
        cleanup
    fi

    echo "[!] Restarting server (attempt #$count, reason: $reason)..."

    # Kill old server
    local old_pid
    old_pid=$(cat "$SERVER_PID_FILE" 2>/dev/null || echo "")
    if [ -n "$old_pid" ]; then
        kill "$old_pid" 2>/dev/null || true
        sleep 1
        kill -9 "$old_pid" 2>/dev/null || true
    fi

    # Start new
    local new_pid
    new_pid=$(start_server)

    # Verify readiness
    if wait_for_socket "$MCP_HOST" "$MCP_PORT" 15; then
        echo "[+] Server restarted successfully (PID: $new_pid). Reason: $reason"
        # Decrement counter on success
        local dec=$((count - 1))
        [ "$dec" -lt 0 ] && dec=0
        echo "$dec" > "$RESTART_COUNTER_FILE"
        return 0
    else
        echo "[-] Server restart failed (PID $new_pid did not become ready)"
        return 1
    fi
}

# ------------------------------------------------------------------
# start_tunnel — launch cloudflared tunnel
# ------------------------------------------------------------------
start_tunnel() {
    cloudflared tunnel --url "http://${MCP_HOST}:${MCP_PORT}" > logs/cloudflared.log 2>&1 &
    local pid=$!
    echo "$pid" > "$TUNNEL_PID_FILE"
    echo "$pid"
}

# ------------------------------------------------------------------
# wait_for_tunnel_url — extract trycloudflare URL from log
# ------------------------------------------------------------------
wait_for_tunnel_url() {
    local retries="${1:-15}"
    local url=""
    for ((i=1; i<=retries; i++)); do
        if [ -f logs/cloudflared.log ]; then
            url=$(grep -o -E "https://[a-zA-Z0-9-]+\.trycloudflare\.com" logs/cloudflared.log | head -n 1)
            if [ ! -z "$url" ]; then
                echo "$url"
                return 0
            fi
        fi
        sleep 1
    done
    return 1
}

# ------------------------------------------------------------------
# restart_tunnel — kill old tunnel, start new, extract URL
# ------------------------------------------------------------------
restart_tunnel() {
    local reason="$1"
    echo "[!] Restarting tunnel (reason: $reason)..."

    local old_pid
    old_pid=$(cat "$TUNNEL_PID_FILE" 2>/dev/null || echo "")
    if [ -n "$old_pid" ]; then
        kill "$old_pid" 2>/dev/null || true
        sleep 1
        # Also kill any lingering cloudflared for this port
        TUNNEL_PIDS=$(ps -eo pid=,comm=,args= | awk \
            -v target1="http://${MCP_HOST}:${MCP_PORT}" \
            -v target2="http://localhost:${MCP_PORT}" \
            '$2 == "cloudflared" && index($0, " tunnel ") && (index($0, target1) || index($0, target2)) { print $1 }' \
            | tr '\n' ' ')
        if [ ! -z "$TUNNEL_PIDS" ]; then
            kill -9 $TUNNEL_PIDS 2>/dev/null || true
        fi
    fi

    rm -f logs/cloudflared.log
    local new_pid
    new_pid=$(start_tunnel)
    local new_url
    new_url=$(wait_for_tunnel_url 15)

    if [ -z "$new_url" ]; then
        echo "[-] Tunnel restart failed — cannot obtain URL"
        return 1
    fi

    URL="$new_url"
    echo "[+] Tunnel restarted (PID: $new_pid). New URL: ${URL}${MCP_PATH}"
    return 0
}

# ------------------------------------------------------------------
# Phase 1: Wait for server socket readiness
# ------------------------------------------------------------------
echo "[*] Waiting for server socket readiness..."
if ! wait_for_socket "$MCP_HOST" "$MCP_PORT" 30; then
    if ! kill -0 $SERVER_PID 2>/dev/null; then
        echo "[-] Error: MCP server failed to start. Check logs/server.log for details."
        exit 1
    fi
fi

if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "[-] Error: MCP server failed to start. Check logs/server.log for details."
    exit 1
fi
echo "[+] MCP server started successfully (PID: $SERVER_PID)."

# ------------------------------------------------------------------
# Phase 2: Start Cloudflare Tunnel
# ------------------------------------------------------------------
echo "[*] Initiating Cloudflare Tunnel..."
TUNNEL_PID=$(start_tunnel)
echo "[+] Tunnel process launched (PID: $TUNNEL_PID)."

echo "[*] Waiting for TryCloudflare URL generation (approx 5-10s)..."
URL=$(wait_for_tunnel_url 15)

if [ -z "$URL" ]; then
    echo "[-] Error: Failed to obtain TryCloudflare URL. Check logs/cloudflared.log."
    kill $SERVER_PID 2>/dev/null || true
    kill $TUNNEL_PID 2>/dev/null || true
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

# Reset restart counter on clean startup
echo 0 > "$RESTART_COUNTER_FILE"

# ------------------------------------------------------------------
# Watchdog loop: health-check each process and restart on failure
# ------------------------------------------------------------------
HEALTH_FAILS=0
MAX_HEALTH_FAILS=6     # ~18s of local health failures before restart

while true; do
    # ---- 1. Check server PID ----
    CURRENT_SERVER_PID=$(cat "$SERVER_PID_FILE" 2>/dev/null || echo "")
    if [ -z "$CURRENT_SERVER_PID" ] || ! kill -0 "$CURRENT_SERVER_PID" 2>/dev/null; then
        echo "[-] MCP server process died."
        restart_server "process_died" || cleanup
        sleep 1
    fi

    # ---- 2. Check tunnel PID ----
    CURRENT_TUNNEL_PID=$(cat "$TUNNEL_PID_FILE" 2>/dev/null || echo "")
    if [ -z "$CURRENT_TUNNEL_PID" ] || ! kill -0 "$CURRENT_TUNNEL_PID" 2>/dev/null; then
        echo "[-] Cloudflare Tunnel process died."
        restart_tunnel "process_died" || cleanup
        sleep 1
    fi

    # ---- 3. Local health check (via TCP + /healthz) ----
    LOCAL_OK=false
    if .venv/bin/python -c "
import socket
try:
    socket.create_connection(('$MCP_HOST', $MCP_PORT), timeout=1).close()
    print('ok')
except Exception:
    exit(1)
" >/dev/null 2>&1; then
        # TCP socket is up — quick HTTP GET /healthz to confirm app-level health
        if command -v curl >/dev/null 2>&1; then
            HTTP_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 2 "http://${MCP_HOST}:${MCP_PORT}/healthz" 2>/dev/null || echo "000")
            if [ "$HTTP_STATUS" = "200" ]; then
                LOCAL_OK=true
            fi
        else
            LOCAL_OK=true  # no curl, trust TCP socket
        fi
    fi

    if [ "$LOCAL_OK" = false ]; then
        HEALTH_FAILS=$((HEALTH_FAILS + 1))
        echo "[!] Local health check failed ($HEALTH_FAILS/$MAX_HEALTH_FAILS)"
        if [ "$HEALTH_FAILS" -ge "$MAX_HEALTH_FAILS" ]; then
            echo "[-] $MAX_HEALTH_FAILS consecutive health failures. Restarting server..."
            restart_server "health_check_failed" || cleanup
            HEALTH_FAILS=0
        fi
    else
        HEALTH_FAILS=0
    fi

    # ---- 4. Tunnel health check (optional, depends on curl) ----
    if [ "$LOCAL_OK" = true ] && [ -n "$URL" ] && command -v curl >/dev/null 2>&1; then
        TUNNEL_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 3 "${URL}/healthz" 2>/dev/null || echo "000")
        if [ "$TUNNEL_STATUS" = "000" ] || [ "$TUNNEL_STATUS" -ge 502 ]; then
            # Tunnel unreachable → restart tunnel (server is fine locally)
            echo "[!] Tunnel unreachable (HTTP $TUNNEL_STATUS). Restarting tunnel..."
            restart_tunnel "unreachable" || cleanup
        elif [ "$TUNNEL_STATUS" = "429" ]; then
            # Rate-limited by Cloudflare → restart both
            echo "[!] Rate limited (429) through tunnel. Restarting server + tunnel..."
            restart_server "rate_limited" || cleanup
            sleep 1
            restart_tunnel "rate_limited" || cleanup
        fi
    fi

    sleep 3
done

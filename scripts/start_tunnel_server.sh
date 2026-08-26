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
    local env_var="${!key:-}"
    if [ -n "$env_var" ]; then
        printf '%s\n' "$env_var"
        return 0
    fi
    if [ -f .env ]; then
        local file_var
        file_var=$(grep -E "^[[:space:]]*${key}=" .env 2>/dev/null | tail -n 1 | sed -E "s/^[[:space:]]*${key}=[[:space:]]*//; s/[\x27\"]//g; s/[[:space:]]*$//" || true)
        if [ -n "$file_var" ]; then
            printf '%s\n' "$file_var"
            return 0
        fi
    fi
    printf '%s\n' "$default_value"
}

MCP_BIND_HOST="${MCP_BIND_HOST:-$(read_env MCP_BIND_HOST 127.0.0.1)}"
MCP_CONNECT_HOST="${MCP_CONNECT_HOST:-127.0.0.1}"
MCP_PORT="${MCP_PORT:-$(read_env MCP_PORT 18427)}"
MCP_PATH="${MCP_PATH:-$(read_env MCP_PATH /mcp)}"
SERVER_PID_FILE="logs/server.pid"
TUNNEL_PID_FILE="logs/tunnel.pid"
SUPERVISOR_PID_FILE="logs/watchdog.pid"
LAUNCHER_PID_FILE="logs/launcher.pid"
TUNNEL_URL_FILE="logs/tunnel_url.txt"
SERVER_LOG="logs/server.log"
CLOUDFLARED_LOG="logs/cloudflared.log"
# Chat workspace lifecycle sweep (scripts/sweep_chat_workspaces.sh). Gated on
# HOST_CHAT_WORKSPACES=true; scheduled sweeps stay dry-run unless
# HOST_CHAT_SWEEP_APPLY=true opts into real archiving/deletion. Reports land
# in logs/sweeper.log.
CHAT_SWEEP_ENABLED="$(read_env HOST_CHAT_WORKSPACES false)"
CHAT_SWEEP_INTERVAL_MINUTES="$(read_env HOST_CHAT_SWEEP_INTERVAL_MINUTES 60)"
case "$CHAT_SWEEP_INTERVAL_MINUTES" in
    ''|*[!0-9]*) CHAT_SWEEP_INTERVAL_MINUTES=60 ;;
esac
CHAT_SWEEP_APPLY="$(read_env HOST_CHAT_SWEEP_APPLY false)"
SWEEPER_LOG="logs/sweeper.log"

SERVER_STARTED_AT=0
MANAGED_SERVER_PID=""
MANAGED_TUNNEL_PID=""
PUBLISHED_TUNNEL_PID=""
TUNNEL_LOG_OFFSET=0
TUNNEL_LOST_REPORTED=0
SHUTTING_DOWN=0
LAST_CHAT_SWEEP=0

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
    # Keep the PIDs in memory as well as in runtime files: an interrupted or
    # external cleanup can remove a PID file before this trap gets to run.
    stop_managed_pid "$MANAGED_TUNNEL_PID" tunnel "Cloudflare Tunnel"
    stop_managed_pid "$MANAGED_SERVER_PID" server "MCP Server"
    rm -f "$TUNNEL_PID_FILE" "$SERVER_PID_FILE"
    rm -f "$TUNNEL_URL_FILE"
    remove_own_pid_file "$SUPERVISOR_PID_FILE"
    remove_own_pid_file "$LAUNCHER_PID_FILE"
    exit 0
}

trap shutdown TERM INT

local_health_ready() {
    curl --fail --silent --show-error --max-time 1 \
        "http://${MCP_CONNECT_HOST}:${MCP_PORT}/healthz" >/dev/null 2>&1
}

public_health_ready() {
    local url="$1" host="" ip=""
    curl --fail --silent --show-error --max-time 1 \
        "${url%/}/healthz" >/dev/null 2>&1 && return 0
    host=${url#https://}
    host=${host%%/*}

    # Extract edge IP from cloudflared registration log if available
    ip=$(tail -n 50 "$CLOUDFLARED_LOG" 2>/dev/null | grep -o -E 'ip=[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | tail -n 1 | cut -d= -f2 || true)

    # Fallback to public DNS or resolving trycloudflare.com
    if [ -z "$ip" ] && command -v dig >/dev/null 2>&1; then
        ip=$(dig +short +time=1 +tries=1 @1.1.1.1 "$host" A 2>/dev/null | head -n 1 || true)
        [ -n "$ip" ] || ip=$(dig +short +time=1 +tries=1 @1.1.1.1 trycloudflare.com A 2>/dev/null | head -n 1 || true)
    fi

    # Fallback to getent for trycloudflare.com
    if [ -z "$ip" ]; then
        ip=$(getent ahostsv4 trycloudflare.com 2>/dev/null | awk '{print $1}' | head -n 1 || true)
    fi

    # Known Cloudflare Anycast fallback
    [ -n "$ip" ] || ip="104.16.230.132"

    curl --fail --silent --show-error --max-time 2 \
        --resolve "${host}:443:${ip}" "${url%/}/healthz" >/dev/null 2>&1
}

start_server() {
    local existing=""
    existing=$(read_pid "$SERVER_PID_FILE")
    if pid_matches_kind "$existing" server; then
        MANAGED_SERVER_PID="$existing"
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
    MANAGED_SERVER_PID="$pid"
    atomic_write "$SERVER_PID_FILE" "$pid"
    SERVER_STARTED_AT=$(date +%s)
    echo "[+] MCP server process started (PID $pid)."
}

start_tunnel() {
    local existing=""
    existing=$(read_pid "$TUNNEL_PID_FILE")
    if pid_matches_kind "$existing" tunnel; then
        MANAGED_TUNNEL_PID="$existing"
        return 0
    fi

    rm -f "$TUNNEL_PID_FILE" "$TUNNEL_URL_FILE"
    # A fresh installation may not have created cloudflared.log yet. Create the
    # file without truncating an existing log so the launch offset is quiet and
    # still excludes stale URLs from earlier tunnel processes.
    touch "$CLOUDFLARED_LOG"
    TUNNEL_LOG_OFFSET=$(wc -c < "$CLOUDFLARED_LOG")
    nohup cloudflared tunnel --url "http://${MCP_CONNECT_HOST}:${MCP_PORT}" \
        >> "$CLOUDFLARED_LOG" 2>&1 &
    local pid=$!
    MANAGED_TUNNEL_PID="$pid"
    atomic_write "$TUNNEL_PID_FILE" "$pid"
    PUBLISHED_TUNNEL_PID=""
    TUNNEL_LOST_REPORTED=0
    echo "[+] Cloudflare Tunnel process started (PID $pid)."
}

publish_tunnel_url() {
    local pid="" url=""
    pid=$(read_pid "$TUNNEL_PID_FILE")
    pid_matches_kind "$pid" tunnel || return 1

    if [ "$PUBLISHED_TUNNEL_PID" = "$pid" ] && [ -s "$TUNNEL_URL_FILE" ]; then
        return 0
    fi

    url=$(quick_tunnel_url_from_log_since "$CLOUDFLARED_LOG" "$TUNNEL_LOG_OFFSET" || true)
    [ -n "$url" ] || return 1
    cloudflared_registered_since "$CLOUDFLARED_LOG" "$TUNNEL_LOG_OFFSET" || return 1
    local_health_ready || return 1
    public_health_ready "$url" || return 1

    atomic_write "$TUNNEL_URL_FILE" "$url"
    PUBLISHED_TUNNEL_PID="$pid"
    echo "[+] Connector URL published: ${url}${MCP_PATH}"
}

existing_supervisor=$(read_pid "$SUPERVISOR_PID_FILE")
if pid_matches_kind "$existing_supervisor" supervisor && [ "$existing_supervisor" != "$$" ]; then
    echo "[i] Supervisor is already running (PID $existing_supervisor)."
    exit 0
fi

# mkdir is the atomic primitive here: two concurrent supervisors cannot both
# create the lock directory, closing the PID-file check/write race window.
SUPERVISOR_LOCK_DIR="logs/.supervisor_lock"
if ! mkdir "$SUPERVISOR_LOCK_DIR" 2>/dev/null; then
    # The lock holder may not have published its PID yet; give it a beat and
    # re-check before declaring the lock stale, closing the takeover race.
    if pid_matches_kind "$existing_supervisor" supervisor && kill -0 "$existing_supervisor" 2>/dev/null; then
        echo "[i] Supervisor is already running (PID $existing_supervisor)."
        exit 0
    fi
    sleep 0.2
    existing_supervisor=$(read_pid "$SUPERVISOR_PID_FILE")
    if pid_matches_kind "$existing_supervisor" supervisor && kill -0 "$existing_supervisor" 2>/dev/null; then
        echo "[i] Supervisor is already running (PID $existing_supervisor)."
        exit 0
    fi
    rm -rf "$SUPERVISOR_LOCK_DIR"
    mkdir "$SUPERVISOR_LOCK_DIR"
fi
trap 'rm -rf "$SUPERVISOR_LOCK_DIR" 2>/dev/null || true' EXIT
atomic_write "$SUPERVISOR_PID_FILE" "$$"

# These functions only spawn processes; neither waits for bridge readiness.
# Therefore the server and tunnel begin startup in parallel from the user's perspective.
start_server
initial_tunnel_pid=$(read_pid "$TUNNEL_PID_FILE")
if pid_matches_kind "$initial_tunnel_pid" tunnel; then
    PUBLISHED_TUNNEL_PID="$initial_tunnel_pid"
else
    start_tunnel
fi

health_failures=0
last_health_check=0

while true; do
    server_pid=$(read_pid "$SERVER_PID_FILE")
    if ! pid_matches_kind "$server_pid" server; then
        now=$(date +%s)
        if pid_matches_kind "$MANAGED_SERVER_PID" server || { pid_is_alive "$MANAGED_SERVER_PID" && [ $((now - SERVER_STARTED_AT)) -lt 20 ]; }; then
            atomic_write "$SERVER_PID_FILE" "$MANAGED_SERVER_PID"
        else
            # A freshly spawned script/interpreter may not have exec'd FastMCP yet.
            # Treat its owned PID as starting during the grace period instead of
            # overwriting server.pid and creating a duplicate-spawn storm.
            if ! pid_is_alive "$server_pid" || [ $((now - SERVER_STARTED_AT)) -ge 20 ]; then
                start_server
                health_failures=0
            fi
        fi
    fi

    tunnel_pid=$(read_pid "$TUNNEL_PID_FILE")
    if ! pid_matches_kind "$tunnel_pid" tunnel; then
        if pid_matches_kind "$MANAGED_TUNNEL_PID" tunnel; then
            atomic_write "$TUNNEL_PID_FILE" "$MANAGED_TUNNEL_PID"
        elif [ "$TUNNEL_LOST_REPORTED" -eq 0 ]; then
            echo "[!] QUICK_TUNNEL_LOST: automatic recreation disabled; existing connector URL is no longer recoverable; manual reprovisioning required."
            TUNNEL_LOST_REPORTED=1
        fi
    else
        TUNNEL_LOST_REPORTED=0
        publish_tunnel_url || true
    fi

    now=$(date +%s)
    if [ "$now" -ne "$last_health_check" ]; then
        last_health_check=$now
        if local_health_ready; then
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

    # Hourly chat-workspace sweep gate; mirrors the health-check second-compare
    # idiom above. The wrapper appends its own JSON report to $SWEEPER_LOG and
    # a failure here must never take the supervisor down.
    if [ "$CHAT_SWEEP_ENABLED" = "true" ] && [ $((now - LAST_CHAT_SWEEP)) -ge $((CHAT_SWEEP_INTERVAL_MINUTES * 60)) ]; then
        LAST_CHAT_SWEEP=$now
        sweep_args=()
        if [ "$CHAT_SWEEP_APPLY" = "true" ]; then
            sweep_args+=(--apply)
        fi
        echo "[+] Chat workspace sweep starting (apply=$CHAT_SWEEP_APPLY)."
        ./scripts/sweep_chat_workspaces.sh "${sweep_args[@]}" >/dev/null 2>&1 ||
            echo "[!] Chat workspace sweep failed; see $SWEEPER_LOG."
    fi

    sleep 0.1
done

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck source=scripts/process_helpers.sh
source ./scripts/process_helpers.sh
[ -x .venv/bin/fastmcp ] || ./scripts/install_basic.sh
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
PID_FILE="logs/server.pid"
SUPERVISOR_PID_FILE="logs/watchdog.pid"
LAUNCHER_PID_FILE="logs/launcher.pid"

socket_ready() {
    if (echo > "/dev/tcp/${MCP_CONNECT_HOST}/${MCP_PORT}") >/dev/null 2>&1; then
        return 0
    fi
    if command -v nc >/dev/null 2>&1; then
        nc -z -w 1 "$MCP_CONNECT_HOST" "$MCP_PORT" >/dev/null 2>&1 && return 0
    fi
    if [ -x .venv/bin/python ]; then
        .venv/bin/python - "$MCP_CONNECT_HOST" "$MCP_PORT" <<'PY' >/dev/null 2>&1
import socket
import sys

with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=0.3):
    pass
PY
        return $?
    fi
    return 1
}

active_supervisor_pid() {
    local pid=""
    pid=$(read_pid_file "$SUPERVISOR_PID_FILE")
    if pid_matches_kind "$pid" supervisor; then
        printf '%s\n' "$pid"
        return 0
    fi
    pid=$(read_pid_file "$LAUNCHER_PID_FILE")
    if pid_matches_kind "$pid" launcher; then
        printf '%s\n' "$pid"
        return 0
    fi
    return 1
}

start_server_standalone() {
    export PYTHONPATH="$ROOT_DIR"
    export FASTMCP_MESSAGE_PATH="$MCP_PATH"

    nohup .venv/bin/fastmcp run app/main.py \
        --transport streamable-http \
        --host "$MCP_BIND_HOST" \
        --port "$MCP_PORT" \
        --path "$MCP_PATH" \
        > logs/server.log 2>&1 &
    local pid=$!
    atomic_write_runtime_file "$PID_FILE" "$pid"
    printf '%s\n' "$pid"
}

wait_for_replacement() {
    local previous_pid="$1" expected_pid="${2:-}" current_pid="" listener_pid=""
    for _ in $(seq 1 60); do
        current_pid=$(read_pid_file "$PID_FILE")
        for listener_pid in $(listening_pids_on_port "$MCP_PORT"); do
            if pid_matches_kind "$listener_pid" server \
                && [ "$listener_pid" != "$previous_pid" ] \
                && { [ -z "$expected_pid" ] || [ "$listener_pid" = "$expected_pid" ]; } \
                && socket_ready; then
                # The supervisor can briefly overwrite server.pid while a new
                # interpreter is still starting. Canonicalize it to the process
                # that actually owns the listening socket before reporting success.
                [ "$current_pid" = "$listener_pid" ] \
                    || atomic_write_runtime_file "$PID_FILE" "$listener_pid"
                echo "[+] Host MCP restarted: http://${MCP_CONNECT_HOST}:${MCP_PORT}${MCP_PATH} (PID $listener_pid)"
                return 0
            fi
        done
        sleep 0.25
    done
    echo "[-] Server socket did not become ready. Check logs/server.log." >&2
    return 1
}

previous_pid=$(read_pid_file "$PID_FILE")
supervisor_pid=$(active_supervisor_pid || true)
stop_managed_pid_file "$PID_FILE" server "MCP Server"

if [ -n "$supervisor_pid" ]; then
    echo "[*] Supervisor PID $supervisor_pid will recreate the MCP server."
    wait_for_replacement "$previous_pid"
    exit 0
fi

for port_pid in $(listening_pids_on_port "$MCP_PORT"); do
    if pid_matches_kind "$port_pid" server; then
        echo "[*] Stopping managed MCP listener on port $MCP_PORT (PID $port_pid)..."
        kill "$port_pid" 2>/dev/null || true
        for _ in $(seq 1 30); do
            kill -0 "$port_pid" 2>/dev/null || break
            sleep 0.1
        done
        kill -9 "$port_pid" 2>/dev/null || true
    else
        echo "[-] Port $MCP_PORT is occupied by an unrelated listening process (PID $port_pid); refusing to stop it." >&2
        exit 1
    fi
done

server_pid=$(start_server_standalone)
wait_for_replacement "$previous_pid" "$server_pid"

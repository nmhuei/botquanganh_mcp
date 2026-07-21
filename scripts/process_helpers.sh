#!/usr/bin/env bash

# Shared Linux process ownership checks for lifecycle scripts.
# A live PID is not considered managed unless its /proc command line matches
# the process type expected by this repository.

read_pid_file() {
    cat "$1" 2>/dev/null || true
}

pid_is_alive() {
    local pid="${1:-}"
    case "$pid" in
        ''|*[!0-9]*) return 1 ;;
    esac
    kill -0 "$pid" 2>/dev/null
}

pid_command_line() {
    local pid="${1:-}"
    pid_is_alive "$pid" || return 1
    [ -r "/proc/$pid/cmdline" ] || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline"
}

pid_matches_kind() {
    local pid="${1:-}" kind="${2:-}" command_line=""
    command_line=$(pid_command_line "$pid") || return 1
    case "$kind" in
        supervisor|launcher)
            [[ "$command_line" == *"start_tunnel_server.sh"* ]]
            ;;
        server)
            [[ "$command_line" == *"fastmcp"* && "$command_line" == *"app/main.py"* ]]
            ;;
        tunnel)
            [[ "$command_line" == *"cloudflared"* && "$command_line" == *"tunnel"* && "$command_line" == *"--url"* ]]
            ;;
        *)
            return 1
            ;;
    esac
}

atomic_write_runtime_file() {
    local file="$1" value="$2" tmp="${1}.tmp.$$"
    printf '%s\n' "$value" > "$tmp"
    mv -f "$tmp" "$file"
}

listening_pids_on_port() {
    local port="${1:-}"
    case "$port" in
        ''|*[!0-9]*) return 2 ;;
    esac

    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true
        return 0
    fi
    if command -v ss >/dev/null 2>&1; then
        ss -ltnp "sport = :$port" 2>/dev/null \
            | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' \
            | sort -u || true
        return 0
    fi

    echo "[-] Neither lsof nor ss is available to inspect listening ports." >&2
    return 127
}

stop_managed_pid_file() {
    local file="$1" kind="$2" label="$3" pid=""
    pid=$(read_pid_file "$file")
    if pid_matches_kind "$pid" "$kind"; then
        echo "[*] Stopping $label (PID $pid)..."
        kill "$pid" 2>/dev/null || true
        for _ in $(seq 1 30); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.1
        done
        kill -9 "$pid" 2>/dev/null || true
    elif pid_is_alive "$pid"; then
        echo "[!] Refusing to stop unrelated process referenced by $file (PID $pid)." >&2
    fi
    rm -f "$file"
}

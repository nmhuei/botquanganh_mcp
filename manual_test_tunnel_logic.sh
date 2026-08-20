#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "$0")" && pwd)"
TEST_ROOT=$(mktemp -d "$SOURCE_ROOT/.manual_tunnel_test.XXXXXX")

cleanup() {
    set +e
    for file in \
        "$TEST_ROOT/logs/watchdog.pid" \
        "$TEST_ROOT/logs/launcher.pid" \
        "$TEST_ROOT/logs/tunnel.pid" \
        "$TEST_ROOT/logs/server.pid"; do
        pid=$(cat "$file" 2>/dev/null || true)
        [ -z "$pid" ] || kill "$pid" 2>/dev/null || true
    done
    sleep 0.2
    for file in \
        "$TEST_ROOT/logs/watchdog.pid" \
        "$TEST_ROOT/logs/launcher.pid" \
        "$TEST_ROOT/logs/tunnel.pid" \
        "$TEST_ROOT/logs/server.pid"; do
        pid=$(cat "$file" 2>/dev/null || true)
        [ -z "$pid" ] || kill -9 "$pid" 2>/dev/null || true
    done
    rm -rf "$TEST_ROOT"
}
trap cleanup EXIT

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

assert_contains() {
    local haystack="$1" needle="$2" label="$3"
    [[ "$haystack" == *"$needle"* ]] || fail "$label (missing: $needle)"
}

mkdir -p "$TEST_ROOT/scripts" "$TEST_ROOT/logs" "$TEST_ROOT/.venv/bin" "$TEST_ROOT/bin" "$TEST_ROOT/fake_py" "$TEST_ROOT/app"
cp "$SOURCE_ROOT/run_mcp_tunnel.sh" "$TEST_ROOT/run_mcp_tunnel.sh"
cp "$SOURCE_ROOT/scripts/start_tunnel_server.sh" "$TEST_ROOT/scripts/start_tunnel_server.sh"
cp "$SOURCE_ROOT/scripts/restart_server_only.sh" "$TEST_ROOT/scripts/restart_server_only.sh"
cp "$SOURCE_ROOT/scripts/stop_tunnel_server.sh" "$TEST_ROOT/scripts/stop_tunnel_server.sh"
cp "$SOURCE_ROOT/scripts/process_helpers.sh" "$TEST_ROOT/scripts/process_helpers.sh"
chmod +x "$TEST_ROOT/run_mcp_tunnel.sh" "$TEST_ROOT/scripts/start_tunnel_server.sh" "$TEST_ROOT/scripts/restart_server_only.sh" "$TEST_ROOT/scripts/stop_tunnel_server.sh" "$TEST_ROOT/scripts/process_helpers.sh"

cat > "$TEST_ROOT/scripts/install_basic.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "$TEST_ROOT/scripts/install_basic.sh"

cat > "$TEST_ROOT/fake_py/dotenv.py" <<'PY'
def dotenv_values(path):
    values = {}
    try:
        with open(path, encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return values
PY

cat > "$TEST_ROOT/.venv/bin/python" <<'SH'
#!/usr/bin/env bash
export PYTHONPATH="$PWD/fake_py${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "$@"
SH
chmod +x "$TEST_ROOT/.venv/bin/python"

cat > "$TEST_ROOT/.venv/bin/fastmcp" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
host=127.0.0.1
port=8000
while [ "$#" -gt 0 ]; do
    case "$1" in
        --host)
            host="$2"
            shift 2
            ;;
        --port)
            port="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done
sleep 4
exec -a "fastmcp run app/main.py" python3 - "$host" "$port" <<'PY'
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
sock = socket.socket()
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind((host, port))
sock.listen()
while True:
    conn, _ = sock.accept()
    conn.close()
PY
SH
chmod +x "$TEST_ROOT/.venv/bin/fastmcp"

cat > "$TEST_ROOT/bin/cloudflared" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
counter_file="logs/fake_cloudflared_count"
count=$(cat "$counter_file" 2>/dev/null || echo 0)
count=$((count + 1))
printf '%s\n' "$count" > "$counter_file"
sleep 0.2
echo "INF Your quick Tunnel has been created! Visit it at https://fresh-${count}.trycloudflare.com"
echo "INF Registered tunnel connection connIndex=0"
while true; do sleep 1; done
SH
chmod +x "$TEST_ROOT/bin/cloudflared"

cat > "$TEST_ROOT/bin/curl" <<'SH'
#!/usr/bin/env bash
if [[ "$*" == *"trycloudflare.com/healthz"* ]]; then
    counter_file="logs/fake_public_health_count"
    count=$(cat "$counter_file" 2>/dev/null || echo 0)
    count=$((count + 1))
    printf '%s\n' "$count" > "$counter_file"
    [ "$count" -ge 4 ] || exit 22
fi
exit 0
SH
chmod +x "$TEST_ROOT/bin/curl"

PORT=$(python3 - <<'PY'
import socket
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
print(sock.getsockname()[1])
sock.close()
PY
)
cat > "$TEST_ROOT/.env" <<EOF
MCP_BIND_HOST=127.0.0.1
MCP_CONNECT_HOST=127.0.0.1
MCP_PORT=$PORT
MCP_PATH=/mcp
EOF

printf '%s\n' 'https://stale-old.trycloudflare.com' > "$TEST_ROOT/logs/tunnel_url.txt"
printf '%s\n' 'INF https://stale-log.trycloudflare.com' > "$TEST_ROOT/logs/cloudflared.log"

cd "$TEST_ROOT"
export PATH="$TEST_ROOT/bin:$PATH"
unset MCP_BIND_HOST MCP_CONNECT_HOST MCP_PORT MCP_PATH

bash -n run_mcp_tunnel.sh scripts/start_tunnel_server.sh
echo "PASS: bash syntax"

started_ms=$(date +%s%3N)
start_output=$(./run_mcp_tunnel.sh start)
elapsed_ms=$(( $(date +%s%3N) - started_ms ))
assert_contains "$start_output" "https://fresh-1.trycloudflare.com/mcp" "fresh URL was not printed"
[[ "$(cat logs/fake_public_health_count)" -ge 4 ]] || fail "URL published before public health retry succeeded"
[[ "$start_output" != *"stale-old"* ]] || fail "old canonical URL leaked"
[[ "$start_output" != *"stale-log"* ]] || fail "old log URL leaked"
[ "$elapsed_ms" -lt 3000 ] || fail "URL publication took ${elapsed_ms}ms"
echo "PASS: fresh URL published after isolated readiness probes"

status_output=$(./run_mcp_tunnel.sh status)
assert_contains "$status_output" "Supervisor: running" "supervisor status"
assert_contains "$status_output" "Server:     running" "server status"
assert_contains "$status_output" "Tunnel:     running" "tunnel status"
assert_contains "$status_output" "Bridge:     starting" "isolated fake bridge state"
assert_contains "$status_output" "URL:        https://fresh-1.trycloudflare.com/mcp" "status URL"
echo "PASS: immediate status"

url_output=$(./run_mcp_tunnel.sh url)
[ "$url_output" = "https://fresh-1.trycloudflare.com/mcp" ] || fail "url command returned: $url_output"
echo "PASS: url command"

first_tunnel_pid=$(cat logs/tunnel.pid)
second_start_output=$(./run_mcp_tunnel.sh start)
second_tunnel_pid=$(cat logs/tunnel.pid)
[ "$first_tunnel_pid" = "$second_tunnel_pid" ] || fail "idempotent start created another tunnel"
assert_contains "$second_start_output" "already supervised" "idempotent start response"
echo "PASS: idempotent start"

first_url=$(cat logs/tunnel_url.txt)
./run_mcp_tunnel.sh restart >/dev/null
[ "$(cat logs/tunnel.pid)" = "$first_tunnel_pid" ] || fail "server restart changed tunnel PID"
[ "$(cat logs/tunnel_url.txt)" = "$first_url" ] || fail "server restart changed tunnel URL"
echo "PASS: restart is server-only"

kill "$first_tunnel_pid"
sleep 0.5
[ "$(cat logs/fake_cloudflared_count)" = "1" ] || fail "watchdog recreated dead tunnel"
[ "$(cat logs/tunnel_url.txt)" = "$first_url" ] || fail "watchdog removed last-known URL"
! ./run_mcp_tunnel.sh url >/dev/null 2>&1 || fail "url advertised stale tunnel"
grep -q 'QUICK_TUNNEL_LOST' logs/launcher.log || fail "tunnel loss diagnostic missing"
echo "PASS: tunnel loss is monitor-only and URL becomes stale"

! grep -q 'stale-log' logs/tunnel_url.txt || fail "canonical URL came from stale cloudflared log"
echo "PASS: no cloudflared.log fallback"

supervisor_pid=$(cat logs/watchdog.pid)
server_pid=$(cat logs/server.pid)
tunnel_pid=""
./run_mcp_tunnel.sh stop >/dev/null
sleep 0.3
for pid in "$supervisor_pid" "$server_pid" "$tunnel_pid"; do
    ! kill -0 "$pid" 2>/dev/null || fail "PID $pid survived stop"
done
echo "PASS: stop terminates supervisor/server without resurrection"

echo "ALL_MANUAL_TESTS=PASS"

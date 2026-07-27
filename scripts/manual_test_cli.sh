#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

BQA="$ROOT_DIR/bin/bqa"
PYTHON="$ROOT_DIR/.venv/bin/python"
RESULT_FILE="$ROOT_DIR/logs/cli_manual_test_results.txt"
mkdir -p logs
: > "$RESULT_FILE"

PASS_COUNT=0
CURRENT_TEST="initialization"
TMP_DIR="$(mktemp -d -t bqa-cli-test-XXXXXX)"
ISO_DIR=""
TEST_LOCAL=""

log() {
    printf '%s\n' "$*" | tee -a "$RESULT_FILE"
}

pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    log "PASS: $1"
}

fail() {
    local line="${1:-unknown}" command="${2:-unknown}"
    log "FAIL: $CURRENT_TEST"
    log "FAIL_LINE=$line"
    log "FAIL_COMMAND=$command"
    exit 1
}

trap 'fail "$LINENO" "$BASH_COMMAND"' ERR
cleanup() {
    set +e
    if [ -n "$ISO_DIR" ] && [ -x "$ISO_DIR/run_mcp_tunnel.sh" ]; then
        "$ISO_DIR/run_mcp_tunnel.sh" stop >/dev/null 2>&1 || true
    fi
    [ -z "$TEST_LOCAL" ] || rm -rf "$TEST_LOCAL"
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

json_assert() {
    local file="$1" expression="$2"
    "$PYTHON" - "$file" "$expression" <<'PY'
import json, sys
path, expression = sys.argv[1], sys.argv[2]
with open(path, encoding='utf-8') as handle:
    data = json.load(handle)
safe = {'data': data, 'len': len, 'any': any, 'all': all, 'str': str, 'int': int}
if not eval(expression, {'__builtins__': {}}, safe):
    raise SystemExit(f'assertion failed: {expression}')
PY
}

expect_exit() {
    local expected="$1" actual=0
    shift
    if "$@" >"$TMP_DIR/expect.out" 2>"$TMP_DIR/expect.err"; then
        actual=0
    else
        actual=$?
    fi
    if [ "$actual" -ne "$expected" ]; then
        log "Expected exit $expected, got $actual: $*"
        cat "$TMP_DIR/expect.out" >> "$RESULT_FILE" 2>/dev/null || true
        cat "$TMP_DIR/expect.err" >> "$RESULT_FILE" 2>/dev/null || true
        return 1
    fi
}

CURRENT_TEST="syntax and packaging"
"$PYTHON" -m compileall -q app/cli
bash -n bin/bqa scripts/manual_test_cli.sh
"$PYTHON" -m pip install -e . --no-deps >/dev/null
"$BQA" --help > "$TMP_DIR/help.txt"
grep -q "{start,stop,restart,status,url,server,health,capabilities,fs,cmd,knowledge,logs,config,doctor,completion,version}" "$TMP_DIR/help.txt"
[ "$("$BQA" version)" = "bqa 1.0.0" ]
[ "$(.venv/bin/bqa version)" = "bqa 1.0.0" ]
pass "build, executable, packaging, help, version"

CURRENT_TEST="completion"
for shell in bash zsh fish; do
    "$BQA" completion "$shell" > "$TMP_DIR/completion-$shell"
    [ -s "$TMP_DIR/completion-$shell" ]
done
pass "bash, zsh, fish completion"

CURRENT_TEST="status and global options"
"$BQA" status --json > "$TMP_DIR/status.json"
json_assert "$TMP_DIR/status.json" "data['server']['running'] and data['tunnel']['running'] and data['bridge'] == 'ready'"
"$BQA" --json status > "$TMP_DIR/status-prefix.json"
json_assert "$TMP_DIR/status-prefix.json" "data['ok'] is True"
"$BQA" server status --json > "$TMP_DIR/server-status.json"
json_assert "$TMP_DIR/server-status.json" "data['server']['running'] and data['bridge'] == 'ready'"
URL="$($BQA url --quiet)"
[[ "$URL" == https://*.trycloudflare.com/mcp ]]
pass "status human/json, global option placement, url, server status"

CURRENT_TEST="local and public health"
"$BQA" health > "$TMP_DIR/health.txt"
"$BQA" health --json > "$TMP_DIR/health.json"
json_assert "$TMP_DIR/health.json" "data['ok'] is True and data['service'] == 'botquanganh-host-mcp'"
"$BQA" --public health --json > "$TMP_DIR/public-health.json"
json_assert "$TMP_DIR/public-health.json" "data['ok'] is True"
pass "local and public REST health"

CURRENT_TEST="capabilities"
"$BQA" capabilities --json > "$TMP_DIR/capabilities.json"
json_assert "$TMP_DIR/capabilities.json" "len(data['tools']) == 12"
"$BQA" capabilities --tools > /dev/null
"$BQA" capabilities --limits > /dev/null
"$BQA" capabilities --host > /dev/null
pass "capabilities full and filters"

CURRENT_TEST="filesystem setup"
readarray -t PATHS < <("$PYTHON" - <<'PY'
from pathlib import Path
from dotenv import dotenv_values
root = Path.cwd().resolve()
workspace = Path(dotenv_values('.env').get('HOST_WORKSPACE_DIR') or Path.home()).expanduser().resolve()
print(root.relative_to(workspace).as_posix())
print(workspace)
PY
)
REPO_REL="${PATHS[0]}"
TEST_REMOTE="$REPO_REL/.cli_manual_test_$$"
TEST_LOCAL="$ROOT_DIR/.cli_manual_test_$$"
LOCAL_SOURCE="$TMP_DIR/source.txt"
OLD_SOURCE="$TMP_DIR/old.txt"
NEW_SOURCE="$TMP_DIR/new.txt"
printf 'from-file\n' > "$LOCAL_SOURCE"
printf 'beta' > "$OLD_SOURCE"
printf 'gamma' > "$NEW_SOURCE"
"$BQA" fs mkdir "$TEST_REMOTE/nested"
"$BQA" fs write "$TEST_REMOTE/note.txt" --text $'alpha\nbeta\ncharlie\n'
"$BQA" fs write "$TEST_REMOTE/from.txt" --from "$LOCAL_SOURCE"
printf 'from-stdin\n' | "$BQA" fs write "$TEST_REMOTE/stdin.txt" --stdin
pass "fs mkdir and write sources"

CURRENT_TEST="filesystem read ranges"
[ "$("$BQA" fs cat "$TEST_REMOTE/note.txt" --lines 2)" = "beta" ]
[ "$("$BQA" fs cat "$TEST_REMOTE/note.txt" --lines 1:2)" = $'alpha\nbeta' ]
[ "$("$BQA" fs cat "$TEST_REMOTE/note.txt" --lines 2:)" = $'beta\ncharlie' ]
[ "$("$BQA" fs cat "$TEST_REMOTE/note.txt" --lines :2)" = $'alpha\nbeta' ]
"$BQA" fs cat "$TEST_REMOTE/note.txt" --json > "$TMP_DIR/cat.json"
json_assert "$TMP_DIR/cat.json" "data['content'].startswith('alpha')"
pass "fs cat and all line range forms"

CURRENT_TEST="filesystem append replace search list conflict"
"$BQA" fs append "$TEST_REMOTE/note.txt" --text $'delta\n'
printf 'epsilon\n' | "$BQA" fs append "$TEST_REMOTE/note.txt" --stdin
"$BQA" fs replace "$TEST_REMOTE/note.txt" --old alpha --new omega
"$BQA" fs replace "$TEST_REMOTE/note.txt" --old-file "$OLD_SOURCE" --new-file "$NEW_SOURCE"
"$BQA" fs search gamma --path "$TEST_REMOTE" --json > "$TMP_DIR/search.json"
json_assert "$TMP_DIR/search.json" "len(data['results']) >= 1"
"$BQA" fs ls "$TEST_REMOTE" --json > "$TMP_DIR/ls.json"
json_assert "$TMP_DIR/ls.json" "len(data['items']) >= 4"
expect_exit 8 "$BQA" fs write "$TEST_REMOTE/note.txt" --text blocked --no-overwrite
pass "fs append, replace, search, list, conflict exit code"

CURRENT_TEST="command policy"
"$BQA" cmd check 'git status --short' --json > "$TMP_DIR/check-ok.json"
json_assert "$TMP_DIR/check-ok.json" "data['allowed'] is True"
expect_exit 5 "$BQA" cmd check 'sudo id'
pass "cmd policy allowed and blocked"

CURRENT_TEST="command execution semantics"
[ "$("$BQA" cmd run 'printf cli-ok')" = "cli-ok" ]
[ "$("$BQA" cmd run 'printf checked' --check-first)" = "checked" ]
expect_exit 9 "$BQA" cmd run 'printf command-error >&2; exit 9'
grep -q "command-error" "$TMP_DIR/expect.err"
expect_exit 7 "$BQA" cmd run 'python3 -c "import time; time.sleep(2)"' --timeout 1
"$BQA" cmd run 'printf json-ok' --json > "$TMP_DIR/cmd.json"
json_assert "$TMP_DIR/cmd.json" "data['exit_code'] == 0 and data['stdout'] == 'json-ok'"
pass "cmd success, check-first, stderr, nonzero preservation, timeout, JSON"

CURRENT_TEST="knowledge"
"$BQA" knowledge overview --json > "$TMP_DIR/knowledge-overview.json"
json_assert "$TMP_DIR/knowledge-overview.json" "data['section'] == 'overview'"
"$BQA" knowledge guide --query host > /dev/null
"$BQA" knowledge tools --query python > /dev/null
"$BQA" knowledge tools --query python --versions --json > "$TMP_DIR/tools.json"
json_assert "$TMP_DIR/tools.json" "data['section'] == 'tools'"
"$BQA" knowledge tools --all > /dev/null
"$BQA" knowledge search docker > /dev/null
"$BQA" knowledge all --query host > /dev/null
pass "knowledge overview, guide, tools, versions, unavailable, search, all"

CURRENT_TEST="logs"
for target in server tunnel launcher audit; do
    "$BQA" logs "$target" -n 2 > /dev/null
    "$BQA" logs "$target" -n 2 --json > "$TMP_DIR/log-$target.json"
    json_assert "$TMP_DIR/log-$target.json" "data['ok'] is True and len(data['logs']) == 1"
done
"$BQA" logs server -n 10 --grep INFO > /dev/null
"$BQA" logs audit -n 10 --since 1d > /dev/null
if timeout 1 "$BQA" logs follow server -n 1 > /dev/null 2>&1; then
    FOLLOW_EXIT=0
else
    FOLLOW_EXIT=$?
fi
[ "$FOLLOW_EXIT" -eq 124 ] || [ "$FOLLOW_EXIT" -eq 0 ]
pass "log targets, JSON, grep, since, follow startup"

CURRENT_TEST="config"
"$BQA" config show > "$TMP_DIR/config-show.txt"
if grep -F "$("$PYTHON" - <<'PY'
from dotenv import dotenv_values
print(dotenv_values('.env').get('GATEWAY_TOKEN') or '__EMPTY_TOKEN__')
PY
)" "$TMP_DIR/config-show.txt"; then
    log "Config output exposed the gateway token."
    exit 1
fi
[ "$("$BQA" config get GATEWAY_TOKEN --quiet)" = "configured" ]
[ "$("$BQA" config path --quiet)" = "$ROOT_DIR/.env" ]
"$BQA" config validate --json > "$TMP_DIR/config-validate.json"
json_assert "$TMP_DIR/config-validate.json" "data['ok'] is True"
pass "config show/get/path/validate and token redaction"

CURRENT_TEST="doctor"
"$BQA" doctor --json > "$TMP_DIR/doctor.json"
json_assert "$TMP_DIR/doctor.json" "data['ok'] is True and any(x['name'] == 'public_mcp' and x['status'] == 'pass' for x in data['checks'])"
pass "doctor local/public REST and MCP initialize"

CURRENT_TEST="isolated lifecycle"
ISO_DIR="$TMP_DIR/isolated-repo"
mkdir -p "$ISO_DIR/scripts" "$ISO_DIR/logs"
cp -a app "$ISO_DIR/app"
cp -a bin "$ISO_DIR/bin"
ln -s "$ROOT_DIR/.venv" "$ISO_DIR/.venv"
ISO_PORT="$($PYTHON - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    print(sock.getsockname()[1])
PY
)"
cat > "$ISO_DIR/.env" <<EOF
MCP_BIND_HOST=127.0.0.1
MCP_CONNECT_HOST=127.0.0.1
MCP_PORT=$ISO_PORT
MCP_PATH=/mcp
REQUIRE_AUTH=false
GATEWAY_TOKEN=
HOST_WORKSPACE_DIR=$ISO_DIR
HOST_RESTRICT_TO_WORKSPACE=true
HOST_COMMAND_POLICY=guarded
HOST_KNOWLEDGE_DIR=$ISO_DIR/knowledge
EOF
mkdir -p "$ISO_DIR/knowledge"
cat > "$ISO_DIR/run_mcp_tunnel.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
mkdir -p logs
PORT=$(grep '^MCP_PORT=' .env | cut -d= -f2)
running() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }
pid() { cat "logs/$1.pid" 2>/dev/null || true; }
stop_one() { local p; p=$(pid "$1"); if running "$p"; then kill "$p" 2>/dev/null || true; for _ in $(seq 1 20); do running "$p" || break; sleep 0.05; done; running "$p" && kill -9 "$p" 2>/dev/null || true; fi; rm -f "logs/$1.pid"; }
start_all() {
  local current; current=$(pid watchdog)
  if running "$current"; then echo "already running"; exit 0; fi
  nohup bash -c "exec -a 'fastmcp run app/main.py' '$ROOT/.venv/bin/python' -m http.server '$PORT' --bind 127.0.0.1" >logs/server.log 2>&1 & echo $! > logs/server.pid
  nohup bash -c "exec -a 'cloudflared tunnel --url http://127.0.0.1:$PORT' sleep 300" >logs/cloudflared.log 2>&1 & echo $! > logs/tunnel.pid
  nohup bash -c "exec -a 'start_tunnel_server.sh --supervisor' sleep 300" >logs/launcher.log 2>&1 & echo $! > logs/watchdog.pid
  count=$(cat logs/url_counter 2>/dev/null || echo 0); count=$((count+1)); echo "$count" > logs/url_counter
  echo "https://isolated-$count.trycloudflare.com" > logs/tunnel_url.txt
  echo "started"
}
stop_all() { stop_one watchdog; stop_one tunnel; stop_one server; rm -f logs/tunnel_url.txt; echo stopped; }
case "${1:-start}" in
  start) start_all ;;
  stop) stop_all ;;
  restart) stop_all >/dev/null; start_all ;;
  *) exit 2 ;;
esac
SH
cat > "$ISO_DIR/scripts/restart_server_only.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT=$(grep '^MCP_PORT=' .env | cut -d= -f2)
pid=$(cat logs/server.pid 2>/dev/null || true)
if [ -n "$pid" ]; then
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.05; done
  kill -9 "$pid" 2>/dev/null || true
fi
nohup bash -c "exec -a 'fastmcp run app/main.py' '$ROOT/.venv/bin/python' -m http.server '$PORT' --bind 127.0.0.1" >logs/server.log 2>&1 &
echo $! > logs/server.pid
sleep 0.2
echo restarted
SH
chmod +x "$ISO_DIR/run_mcp_tunnel.sh" "$ISO_DIR/scripts/restart_server_only.sh" "$ISO_DIR/bin/bqa"
iso_bqa() {
    (cd "$ISO_DIR" && env -i HOME="$HOME" PATH="$PATH" LANG="${LANG:-C.UTF-8}" ./bin/bqa "$@")
}
iso_bqa start > /dev/null
sleep 0.3
iso_bqa status --json > "$TMP_DIR/iso-status.json" || true
log "ISOLATED_STATUS=$(tr '\n' ' ' < "$TMP_DIR/iso-status.json")"
json_assert "$TMP_DIR/iso-status.json" "data['ok'] is True and data['url'].startswith('https://isolated-1.')"
ISO_TUNNEL_BEFORE=$(cat "$ISO_DIR/logs/tunnel.pid")
ISO_URL_BEFORE=$(cat "$ISO_DIR/logs/tunnel_url.txt")
iso_bqa start > /dev/null
[ "$(cat "$ISO_DIR/logs/tunnel.pid")" = "$ISO_TUNNEL_BEFORE" ]
iso_bqa server restart --json > "$TMP_DIR/iso-server-restart.json"
json_assert "$TMP_DIR/iso-server-restart.json" "data['ok'] is True and data['tunnel_preserved'] is True"
[ "$(cat "$ISO_DIR/logs/tunnel.pid")" = "$ISO_TUNNEL_BEFORE" ]
[ "$(cat "$ISO_DIR/logs/tunnel_url.txt")" = "$ISO_URL_BEFORE" ]
iso_bqa stop > /dev/null
expect_exit 1 iso_bqa status --json
expect_exit 2 iso_bqa restart
iso_bqa restart --yes > /dev/null
sleep 0.3
ISO_URL_AFTER=$(cat "$ISO_DIR/logs/tunnel_url.txt")
[ "$ISO_URL_AFTER" != "$ISO_URL_BEFORE" ]
iso_bqa stop > /dev/null
pass "isolated start/idempotency/status/server-restart/stop/restart confirmation/full restart"

CURRENT_TEST="live idempotent start"
LIVE_TUNNEL_BEFORE=$(cat logs/tunnel.pid)
LIVE_URL_BEFORE=$(cat logs/tunnel_url.txt)
"$BQA" start > "$TMP_DIR/live-start.txt"
[ "$(cat logs/tunnel.pid)" = "$LIVE_TUNNEL_BEFORE" ]
[ "$(cat logs/tunnel_url.txt)" = "$LIVE_URL_BEFORE" ]
pass "live start is idempotent and preserves tunnel"

CURRENT_TEST="live server-only restart"
LIVE_SERVER_BEFORE=$(cat logs/server.pid)
"$BQA" server restart --json > "$TMP_DIR/live-server-restart.json"
json_assert "$TMP_DIR/live-server-restart.json" "data['ok'] is True and data['tunnel_preserved'] is True"
LIVE_SERVER_AFTER=$(cat logs/server.pid)
[ "$LIVE_SERVER_AFTER" != "$LIVE_SERVER_BEFORE" ]
[ "$(cat logs/tunnel.pid)" = "$LIVE_TUNNEL_BEFORE" ]
[ "$(cat logs/tunnel_url.txt)" = "$LIVE_URL_BEFORE" ]
"$BQA" health --json > "$TMP_DIR/post-restart-health.json"
"$BQA" --public health --json > "$TMP_DIR/post-restart-public.json"
"$BQA" doctor --json > "$TMP_DIR/post-restart-doctor.json"
json_assert "$TMP_DIR/post-restart-doctor.json" "data['ok'] is True"
pass "live server restart changes only server PID and preserves public flow"

CURRENT_TEST="final source checks"
"$PYTHON" -m pytest -q > "$TMP_DIR/pytest.txt"
"$PYTHON" -m compileall -q app tests
bash -n run_mcp_tunnel.sh scripts/start_tunnel_server.sh scripts/restart_server_only.sh scripts/install_basic.sh scripts/manual_test_cli.sh bin/bqa
git diff --check
pass "pytest, compileall, bash syntax, git diff check"

log "TOTAL_PASS=$PASS_COUNT"
log "ALL_CLI_MANUAL_TESTS=PASS"

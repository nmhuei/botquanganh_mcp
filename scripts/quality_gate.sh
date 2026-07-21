#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

RUN_RUNTIME=0
RUN_FULL=0
for argument in "$@"; do
    case "$argument" in
        --runtime) RUN_RUNTIME=1 ;;
        --full) RUN_RUNTIME=1; RUN_FULL=1 ;;
        --help|-h)
            cat <<'EOF'
Usage: ./scripts/quality_gate.sh [--runtime] [--full]

Default   Source, tests, packaging, config, and dependency consistency.
--runtime Also run non-destructive local doctor checks.
--full    Also run public doctor checks and isolated tunnel lifecycle regression.
EOF
            exit 0
            ;;
        *)
            echo "Unknown argument: $argument" >&2
            exit 2
            ;;
    esac
done

[ -x .venv/bin/python ] || ./scripts/install_basic.sh
mkdir -p logs
RESULT_FILE="logs/quality_gate_results.txt"
: > "$RESULT_FILE"

run_gate() {
    local label="$1"
    shift
    printf '[*] %s\n' "$label" | tee -a "$RESULT_FILE"
    "$@" 2>&1 | tee -a "$RESULT_FILE"
    printf 'PASS: %s\n' "$label" | tee -a "$RESULT_FILE"
}

export PYTHONPATH="$ROOT_DIR"
run_gate "pytest" .venv/bin/python -m pytest -q
run_gate "compileall" .venv/bin/python -m compileall -q app tests scripts/benchmark_resilience.py
run_gate "bash syntax" bash -n \
    run_mcp_tunnel.sh \
    bin/bqa \
    manual_test_tunnel_logic.sh \
    scripts/collect_diagnostics.sh \
    scripts/install_basic.sh \
    scripts/install_cli.sh \
    scripts/manual_test_installer.sh \
    scripts/process_helpers.sh \
    scripts/quality_gate.sh \
    scripts/restart_server_only.sh \
    scripts/start_tunnel_server.sh \
    scripts/stop_tunnel_server.sh \
    scripts/uninstall_cli.sh
run_gate "git diff check" git diff --check
run_gate "project dependency closure" .venv/bin/python -m app.dependency_check
run_gate "CLI version" .venv/bin/bqa version
run_gate "configuration validation" .venv/bin/bqa config validate --json

if [ "$RUN_RUNTIME" -eq 1 ]; then
    run_gate "local runtime doctor" .venv/bin/bqa doctor --local-only --json
fi
if [ "$RUN_FULL" -eq 1 ]; then
    run_gate "public runtime doctor" .venv/bin/bqa doctor --json
    run_gate "isolated tunnel lifecycle" ./manual_test_tunnel_logic.sh
fi

printf 'ALL_QUALITY_GATES=PASS\n' | tee -a "$RESULT_FILE"

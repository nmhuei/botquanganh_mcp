#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

OUTPUT="${1:-artifacts/diagnostics-$(date -u +%Y%m%dT%H%M%SZ)}"
case "$OUTPUT" in
    /*) OUTPUT_DIR="$OUTPUT" ;;
    *) OUTPUT_DIR="$ROOT_DIR/$OUTPUT" ;;
esac
mkdir -p "$OUTPUT_DIR"

[ -x .venv/bin/bqa ] || {
    echo "[-] CLI is not installed in .venv. Run ./scripts/install_basic.sh." >&2
    exit 1
}

.venv/bin/bqa version > "$OUTPUT_DIR/version.txt"
.venv/bin/bqa status --json > "$OUTPUT_DIR/status.json" || true
.venv/bin/bqa config show --json > "$OUTPUT_DIR/config-redacted.json"
.venv/bin/bqa config validate --json > "$OUTPUT_DIR/config-validation.json" || true
.venv/bin/bqa doctor --local-only --json > "$OUTPUT_DIR/doctor-local.json" || true
.venv/bin/python -m app.dependency_check --json > "$OUTPUT_DIR/project-dependencies.json" || true
.venv/bin/python -m pip check > "$OUTPUT_DIR/pip-check-all-environment.txt" 2>&1 || true
.venv/bin/python -m pip list --format=json > "$OUTPUT_DIR/packages.json"
git branch --show-current > "$OUTPUT_DIR/git-branch.txt"
git rev-parse HEAD > "$OUTPUT_DIR/git-commit.txt"
git status --short > "$OUTPUT_DIR/git-status.txt"
./run_mcp_tunnel.sh status > "$OUTPUT_DIR/runtime-status.txt" || true

cat > "$OUTPUT_DIR/README.txt" <<'EOF'
This diagnostics bundle intentionally excludes:
- .env contents
- gateway tokens and credentials
- file and command payloads
- audit/server/tunnel log bodies

Configuration output is generated through `bqa config show` and is redacted.
EOF

printf '[+] Diagnostics collected at %s\n' "$OUTPUT_DIR"

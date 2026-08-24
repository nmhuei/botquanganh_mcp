#!/usr/bin/env bash
# Capture a point-in-time 502 evidence bundle. This script never starts,
# stops, restarts, upgrades, or reconfigures the MCP server or tunnel.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

OUTPUT="${1:-artifacts/live-forensics/$(date -u +%Y%m%dT%H%M%SZ)}"
case "$OUTPUT" in
    /*) OUTPUT_DIR="$OUTPUT" ;;
    *) OUTPUT_DIR="$ROOT_DIR/$OUTPUT" ;;
esac
mkdir -p "$OUTPUT_DIR"

date -u --iso-8601=seconds > "$OUTPUT_DIR/captured-at.txt"
git status --short > "$OUTPUT_DIR/git-status.txt"
git diff > "$OUTPUT_DIR/git-diff.patch"

./bin/bqa status > "$OUTPUT_DIR/bqa-status.txt" 2>&1 || true
./bin/bqa doctor --local-only > "$OUTPUT_DIR/bqa-doctor-local.txt" 2>&1 || true
curl -sS -D "$OUTPUT_DIR/local-healthz-headers.txt" \
    -o "$OUTPUT_DIR/local-healthz-body.txt" \
    --connect-timeout 2 --max-time 5 http://127.0.0.1:18427/healthz || true
curl -sS -D "$OUTPUT_DIR/local-rest-health-headers.txt" \
    -o "$OUTPUT_DIR/local-rest-health-body.json" \
    --connect-timeout 2 --max-time 5 http://127.0.0.1:18427/api/v1/health || true
ss -lntp | grep ':18427' > "$OUTPUT_DIR/listener.txt" || true
ps aux | grep -E 'fastmcp|botquanganh|18427' | grep -v grep \
    > "$OUTPUT_DIR/server-processes.txt" || true
ps aux | grep cloudflared | grep -v grep > "$OUTPUT_DIR/cloudflared-processes.txt" || true

cat > "$OUTPUT_DIR/README.txt" <<'EOF'
This evidence bundle contains local status and health checks only.

It intentionally does not include .env content, credentials, audit log bodies,
server log bodies, tunnel log bodies, tool arguments, or tool output.
No MCP server or Cloudflare tunnel process was restarted by this collection.
EOF

printf '[+] MCP forensic snapshot: %s\n' "$OUTPUT_DIR"

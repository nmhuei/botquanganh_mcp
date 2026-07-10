#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

[ -x .venv/bin/fastmcp ] || ./scripts/install_basic.sh
export PYTHONPATH="$ROOT_DIR"
exec .venv/bin/fastmcp dev app/main.py

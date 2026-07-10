#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d .venv ]; then
    echo "[*] Creating .venv..."
    python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

if [ ! -f .env ]; then
    cp .env.example .env
    echo "[*] Created .env from .env.example"
fi

mkdir -p logs

echo "[+] Host MCP dependencies installed."
echo "[+] Configure GATEWAY_TOKEN and HOST_WORKSPACE_DIR in .env before public use."

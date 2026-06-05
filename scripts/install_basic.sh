#!/bin/bash
set -e

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
    echo "[*] Creating Python virtual environment (.venv)..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "[*] Checking basic MCP server dependencies with uv..."
if [ ! -x ".venv/bin/uv" ]; then
    python3 -m pip install --upgrade pip uv
fi
uv pip install -r requirements.txt

if [ ! -f ".env" ]; then
    echo "[*] Creating .env from .env.example..."
    cp .env.example .env
fi

echo "[+] Basic install complete."
echo "[+] Server can run with core MCP tools. Advanced runner tools remain disabled until:"
echo "    ./scripts/install_advanced_tools.sh"

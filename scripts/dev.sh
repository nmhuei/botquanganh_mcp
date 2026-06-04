#!/bin/bash
cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "[*] Activating virtual environment..."
    source .venv/bin/activate
fi

export PYTHONPATH=.

# Start FastMCP in development mode (launches the local dashboard)
echo "[*] Launching FastMCP development server for app/main.py..."
fastmcp dev app/main.py

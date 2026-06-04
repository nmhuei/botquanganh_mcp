#!/bin/bash
cd "$(dirname "$0")/.."

# Activate virtual environment if present
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

export PYTHONPATH=.

echo "[*] Running all unit tests..."
python3 -m unittest discover -s tests -p "test_*.py"

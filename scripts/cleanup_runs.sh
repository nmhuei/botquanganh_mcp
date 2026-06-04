#!/bin/bash
# Script to clean up run directories older than X days.
# Read DAYS from configuration or default to 7.
cd "$(dirname "$0")/.."

# Load .env variables
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

DAYS=${DELETE_RUN_FILES_AFTER_DAYS:-7}
RUNS_PATH=${RUNS_DIR:-"./logs/runs"}

if [ ! -d "$RUNS_PATH" ]; then
    echo "[*] Runs directory '$RUNS_PATH' does not exist. Nothing to clean."
    exit 0
fi

echo "[*] Cleaning up run files older than $DAYS days in $RUNS_PATH..."

# Find subfolders under logs/runs and delete if modified more than $DAYS days ago
find "$RUNS_PATH" -mindepth 1 -maxdepth 1 -type d -mtime +"$DAYS" -exec rm -rf {} \;

echo "[+] Cleanup complete."

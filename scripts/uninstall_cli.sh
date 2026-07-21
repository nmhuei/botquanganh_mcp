#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="${BQA_BIN_DIR:-$HOME/.local/bin}"
TARGET="$TARGET_DIR/bqa"
SOURCE="$ROOT_DIR/bin/bqa"

if [ ! -e "$TARGET" ] && [ ! -L "$TARGET" ]; then
    echo "[i] bqa is not installed at $TARGET"
    exit 0
fi

resolved="$(readlink -f "$TARGET" 2>/dev/null || true)"
if [ "$resolved" != "$SOURCE" ]; then
    echo "[-] Refusing to remove unrelated executable: $TARGET -> ${resolved:-unknown}" >&2
    exit 1
fi

rm -f "$TARGET"
echo "[+] Removed bqa symlink: $TARGET"

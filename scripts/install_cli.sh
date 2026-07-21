#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="${BQA_BIN_DIR:-$HOME/.local/bin}"
TARGET="$TARGET_DIR/bqa"
SOURCE="$ROOT_DIR/bin/bqa"

[ -x "$SOURCE" ] || {
    echo "[-] CLI wrapper is missing or not executable: $SOURCE" >&2
    exit 1
}
[ -x "$ROOT_DIR/.venv/bin/python" ] || {
    echo "[-] Project virtual environment is missing. Run ./scripts/install_basic.sh first." >&2
    exit 1
}

mkdir -p "$TARGET_DIR"
ln -sfn "$SOURCE" "$TARGET"

resolved="$(readlink -f "$TARGET")"
[ "$resolved" = "$SOURCE" ] || {
    echo "[-] Installed CLI target resolves unexpectedly: $resolved" >&2
    exit 1
}

"$TARGET" version >/dev/null

echo "[+] Installed bqa: $TARGET -> $SOURCE"
case ":${PATH:-}:" in
    *":$TARGET_DIR:"*) ;;
    *) echo "[!] $TARGET_DIR is not currently in PATH." ;;
esac

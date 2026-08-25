#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$ROOT_DIR/resources/bqa-control-center.desktop.in"
BQA_BIN="${BQA_BIN:-$HOME/.local/bin/bqa}"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
TARGET="$APPLICATIONS_DIR/bqa-control-center.desktop"

[ -f "$TEMPLATE" ] || {
    echo "[-] Desktop launcher template is missing: $TEMPLATE" >&2
    exit 1
}
[ -x "$BQA_BIN" ] || {
    echo "[-] bqa executable is missing or not executable: $BQA_BIN" >&2
    exit 1
}

case "$BQA_BIN" in
    *$'\n'*|*$'\r'*)
        echo "[-] BQA_BIN must not contain a newline." >&2
        exit 1
        ;;
esac

mkdir -p "$APPLICATIONS_DIR"
escaped_bin="$(printf '%s' "$BQA_BIN" | sed 's/[\\&|\"]/\\&/g')"
temporary="$(mktemp "$APPLICATIONS_DIR/.bqa-control-center.XXXXXX")"
trap 'rm -f "$temporary"' EXIT

sed "s|@BQA_BIN@|$escaped_bin|g" "$TEMPLATE" > "$temporary"
chmod 644 "$temporary"
mv -f "$temporary" "$TARGET"
trap - EXIT

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

echo "[+] Installed BQA desktop launcher: $TARGET"

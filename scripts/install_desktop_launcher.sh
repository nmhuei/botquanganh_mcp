#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$ROOT_DIR/resources/ucs-secretagent.desktop.in"
BQA_BIN="${BQA_BIN:-$HOME/.local/bin/bqa}"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/512x512/apps"
ICON_SOURCE="$ROOT_DIR/resources/ucs-secretagent.png"
TARGET="$APPLICATIONS_DIR/ucs-secretagent.desktop"

[ -f "$TEMPLATE" ] || {
    echo "[-] Desktop launcher template is missing: $TEMPLATE" >&2
    exit 1
}
[ -x "$BQA_BIN" ] || {
    echo "[-] bqa executable is missing or not executable: $BQA_BIN" >&2
    exit 1
}
[ -f "$ICON_SOURCE" ] || {
    echo "[-] Desktop icon is missing: $ICON_SOURCE" >&2
    exit 1
}

case "$BQA_BIN" in
    *$'\n'*|*$'\r'*)
        echo "[-] BQA_BIN must not contain a newline." >&2
        exit 1
        ;;
esac

mkdir -p "$APPLICATIONS_DIR" "$ICON_DIR"
escaped_bin="$(printf '%s' "$BQA_BIN" | sed 's/[\\&|\"]/\\&/g')"
temporary="$(mktemp "$APPLICATIONS_DIR/.ucs-secretagent.XXXXXX")"
trap 'rm -f "$temporary"' EXIT

sed "s|@BQA_BIN@|$escaped_bin|g" "$TEMPLATE" > "$temporary"
chmod 644 "$temporary"
mv -f "$temporary" "$TARGET"
trap - EXIT
cp "$ICON_SOURCE" "$ICON_DIR/ucs-secretagent.png"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

echo "[+] Installed UCS-SecretAgent desktop launcher: $TARGET"
